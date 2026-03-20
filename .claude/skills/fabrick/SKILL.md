---
name: fabrick
description: SSH into the remote Linux server (chester@172.31.230.36) for any task — git operations, builds via docker.sh + make, script execution, file management, or log inspection. Use when the user needs to work on the remote source/build server.
---

# fabrick

SSHes into the remote source/build server to perform any task: git operations, Docker + make builds, script execution, file management, or log inspection.

## Environment Variables

```
BUILD_SERVER = chester@172.31.230.36
PROJECT_DIR  = project/opdiag/stark-diag
JOBS         = 16
```

## General Task Execution

The `fabrick` skill covers any SSH task on the build server, not just builds. Common patterns:

### Git Operations

```bash
# Clone or update repo
ssh chester@172.31.230.36 'cd project/opdiag/stark-diag && git pull && echo "PULL OK"'

# Check status / recent log
ssh chester@172.31.230.36 'cd project/opdiag/stark-diag && git status && git log --oneline -5'

# Create a branch
ssh chester@172.31.230.36 'cd project/opdiag/stark-diag && git checkout -b feature/my-branch && echo "BRANCH OK"'

# Fetch all remotes
ssh chester@172.31.230.36 'cd project/opdiag/stark-diag && git fetch --all && echo "FETCH OK"'
```

### Script Execution

```bash
# Run an arbitrary script on the server
ssh chester@172.31.230.36 'cd project/opdiag/stark-diag && bash ./scripts/my-script.sh 2>&1 | tee /tmp/script.log'
```

### File Management

```bash
# Check disk usage and build output
ssh chester@172.31.230.36 'df -h && ls -lh project/opdiag/stark-diag/build/'

# Copy a file to a specific location
ssh chester@172.31.230.36 'cp project/opdiag/stark-diag/build/output.bin /tmp/'
```

### Log Inspection

```bash
# Tail any log file
ssh chester@172.31.230.36 'tail -50 /tmp/fabrick-task.log'

# Search for errors
ssh chester@172.31.230.36 'grep -i error /tmp/fabrick-task.log | tail -20'
```

---

## Step-by-Step Workflow

### 1. Check SSH Connectivity

```bash
ssh -o ConnectTimeout=10 -o BatchMode=yes chester@172.31.230.36 echo "SSH OK"
```

If this fails, fall back to password auth (omit `-o BatchMode=yes`) or troubleshoot the server.

### 2. Clone or Update the Repository

Check if the repo already exists; pull if it does, clone fresh if it doesn't.

```bash
ssh chester@172.31.230.36 '
  if [ -d project/opdiag/stark-diag/.git ]; then
    echo "Repo exists — pulling latest..."
    cd project/opdiag/stark-diag && git pull && echo "PULL OK"
  else
    echo "Directory not found or not a git repo"
  fi
'
```

### 3. Run docker.sh + make (wrapper mode)

`docker.sh` is a **wrapper** — it accepts a command and runs it inside the Docker container using `docker run -it`. Use `ssh -tt` to force pseudo-TTY allocation from the SSH side, which satisfies `docker run -it` and lets the build run in the **foreground** with live streaming output.

Run the full build with live output (10–30 minutes). Set Bash tool `timeout: 1800000`:

```bash
mkdir -p ./tmp
ssh -tt -o ServerAliveInterval=60 chester@172.31.230.36 \
  'cd project/opdiag/stark-diag && bash docker.sh make all -j16 2>&1 | tee /tmp/build.log; echo "BUILD_EXIT:$?"' \
  | tee -a ./tmp/build.log
```

Output streams line-by-line as the build progresses. `tee /tmp/build.log` saves a copy on the remote server; `tee -a ./tmp/build.log` appends to the local log without overwriting previous runs. Check for `BUILD_EXIT:0` at the end to confirm success.

> **Why `ssh -tt`?** — `docker.sh` uses `docker run -it`, which requires a TTY. `ssh -tt` forces TTY allocation even when the local side (Claude's Bash tool) is non-interactive, satisfying docker without needing `script`.

> **Background fallback** — if you need to disconnect mid-build, use `nohup` instead and reconnect later with `tail -f`:
> ```bash
> ssh chester@172.31.230.36 'cd project/opdiag/stark-diag && nohup script -qfc "bash docker.sh make all -j16" /tmp/build.log > /dev/null 2>&1 &'
> # Later:
> ssh chester@172.31.230.36 'tail -f /tmp/build.log'
> ```

---

## Complete Examples

### Scenario A — docker.sh is a setup script (exits before make)

```bash
BUILD_SERVER="chester@172.31.230.36"

# 1. Verify SSH
ssh -o ConnectTimeout=10 "$BUILD_SERVER" echo "SSH OK"

# 2. Update
ssh "$BUILD_SERVER" 'cd project/opdiag/stark-diag && git pull'

# 3. Docker setup
ssh "$BUILD_SERVER" 'cd project/opdiag/stark-diag && bash docker.sh'

# 4. Build (long — run in background)
ssh "$BUILD_SERVER" 'cd project/opdiag/stark-diag && make all -j16 2>&1 | tee /tmp/build.log; echo "EXIT:$?"'
```

### Scenario B — docker.sh wraps the build command (live streaming)

```bash
BUILD_SERVER="chester@172.31.230.36"

# Update
ssh "$BUILD_SERVER" 'cd project/opdiag/stark-diag && git pull'

# Build inside Docker — foreground, live output (Bash tool timeout: 1800000)
mkdir -p ./tmp
ssh -tt -o ServerAliveInterval=60 "$BUILD_SERVER" \
  'cd project/opdiag/stark-diag && bash docker.sh make all -j16 2>&1 | tee /tmp/build.log; echo "BUILD_EXIT:$?"' \
  | tee -a ./tmp/build.log
```

### Reconnecting to a Background Build

If a build was started with `nohup` and you need to reconnect to watch progress:

```bash
ssh chester@172.31.230.36 'tail -f /tmp/build.log'
```

Or check if make is still running:

```bash
ssh chester@172.31.230.36 'pgrep -a make || echo "make not running"'
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ssh: Connection refused` | Server down or wrong IP | `ping 172.31.230.36` from Host to verify reachability |
| `Permission denied (publickey)` | SSH key not installed | `ssh-copy-id chester@172.31.230.36` from Host, or use password auth |
| `docker.sh: Permission denied` | Script not executable | `ssh chester@172.31.230.36 'chmod +x project/opdiag/stark-diag/docker.sh'` |
| `docker: command not found` | Docker not installed on build server | Contact server admin; verify with `ssh ... which docker` |
| `make: *** [...] Error 1` | Compile error | Check `/tmp/build.log`; `ssh ... 'tail -50 /tmp/build.log'` |
| Build stalls mid-way | Stale objects or partial clone | Force re-clone and rebuild |
| SSH drops on long build | Server idle timeout | Use `ssh -o ServerAliveInterval=60 ...` or run build via `nohup` |

## Tips

- Pipe build output to `/tmp/build.log` with `tee` so you can review errors even after the SSH session ends.
- Use `nohup` + `&` to survive SSH disconnects: `ssh ... 'cd project/opdiag/stark-diag && nohup make all -j16 > /tmp/build.log 2>&1 &'`
- To tail the log from a new SSH connection: `ssh chester@172.31.230.36 'tail -f /tmp/build.log'`
- To clean and rebuild: `ssh ... 'cd project/opdiag/stark-diag && make clean && make all -j16'`

---

## Parallel Worktree Builds

Use this workflow when you need to build several independent variants simultaneously (e.g. different LED patterns, feature branches). The main Claude agent creates git worktrees sequentially (fast), then spawns one `fabrick` background agent per worktree (slow — 10–30 min each), all launched in parallel.

> **Simple rebuild (no worktrees):** The `fabrick` agent works for any server-side directory — just pass `CMD=bash docker.sh make all -j16` and `WORK_DIR=project/opdiag/stark-diag` to build the base repo.

### Prerequisites

- The base `project/opdiag/stark-diag/` repo must already exist on the build server (run Steps 1–3 of this skill first if needed).
- The branches or commits to build must exist in the remote repo.

### Step 1 — Create Worktrees on the Server (Main Agent, Sequential)

Worktrees are lightweight checkouts sharing the `.git` object store. Place them under `~/worktrees/` so `docker.sh` resolves relative paths identically to the base repo.

```bash
ssh chester@172.31.230.36 '
  cd project/opdiag/stark-diag
  git fetch --all
  git worktree add ../worktrees/wt1 <branch-1>
  git worktree add ../worktrees/wt2 <branch-2>
  git worktree add ../worktrees/wt3 <branch-3>
  echo "WORKTREES OK"
'
```

Verify:
```bash
ssh chester@172.31.230.36 'git -C project/opdiag/stark-diag worktree list'
```

Stop if any worktree creation fails — do not spawn build agents against missing directories.

### Step 2 — Spawn Background Build Agents (Main Agent, All in One Message)

Issue all Agent tool calls in a **single response** so they launch simultaneously:

```
Agent — subagent_type: fabrick, run_in_background: true
prompt:
  WORK_DIR=project/opdiag/stark-diag/../worktrees/wt1
  CMD=bash docker.sh make all -j16

Agent — subagent_type: fabrick, run_in_background: true
prompt:
  WORK_DIR=project/opdiag/stark-diag/../worktrees/wt2
  CMD=bash docker.sh make all -j16

Agent — subagent_type: fabrick, run_in_background: true
prompt:
  WORK_DIR=project/opdiag/stark-diag/../worktrees/wt3
  CMD=bash docker.sh make all -j16
```

### Step 3 — Aggregate Results (Main Agent Waits for 3 Notifications)

Each agent returns a `FABRICK RESULT` block when done. Once all three arrive, present a summary:

| Worktree | Status | Notes |
|----------|--------|-------|
| wt1 | SUCCESS | — |
| wt2 | FAILED (exit 2) | log tail included below |
| wt3 | SUCCESS | — |

Include any failed build's log tail so the user can diagnose without connecting to the server.

### Step 4 — Clean Up Worktrees (Optional)

```bash
ssh chester@172.31.230.36 '
  git -C project/opdiag/stark-diag worktree remove ../worktrees/wt1 --force
  git -C project/opdiag/stark-diag worktree remove ../worktrees/wt2 --force
  git -C project/opdiag/stark-diag worktree remove ../worktrees/wt3 --force
  echo "CLEANUP OK"
'
```

### Notes

- Each agent writes to `/tmp/fabrick-task.log` on the server — for parallel runs use a unique CMD that includes a distinct log name (e.g. `tee /tmp/fabrick-wt1.log`) to avoid collision.
- The `fabrick` agent works for **any** server-side directory and **any** command, not just builds.
- Three concurrent Docker builds share the server's resources. If the server struggles, reduce jobs to `-j8` or `-j4` per agent.
- The agent uses `BatchMode=yes` (key-based auth only) — ensure your SSH key is installed on the build server before spawning agents.
