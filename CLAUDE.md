# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Executable

The bundled WinPython interpreter lives at `./wpy64/python/python.exe`. Set it as a shell variable at the start of any session that invokes Python:

```bash
PYTHON=./wpy64/python/python.exe
```

All skills reference `"$PYTHON"` — never redeclare `PYTHON` inside a skill. Pre-installed packages: `pyserial`, `pytest`, `psutil`, `requests`, `python-dotenv`, `opencv-python`, `tftpy`.

**Exception:** The `mfgtest` skill has its own isolated WinPython at `./tmp/mfgtest/wpy64/`. It uses `$MFGTEST_PYTHON` (not `$PYTHON`) to avoid clobbering the project-wide variable.

## Available Skills

This repo ships Claude Code skills invokable via slash commands:

| Skill | Command | Purpose |
|-------|---------|---------|
| UART | `/uart` | Serial console interaction with embedded devices |
| Deploy | `/deploy` | Transfer and execute files on embedded devices via HTTP+wget |
| Power | `/power` | Control Aviosys IP Power 9258W2 outlets (on/off/toggle/cycle/status) |
| Picoclaw | `/picoclaw` | Deploy and run the picoclaw LLM agent on the device (network setup, CA certs, clock fix, agent/gateway launch) |
| Fabrick | `/fabrick` | SSH to the remote source/build server for any task: git operations, builds (docker.sh + make), scripts, file management |
| Netboot | `/netboot` | TFTP-boot a firmware image from Host into AXN-2020 via U-Boot (device must be at Marvell>> prompt) |
| Checkspec | `/checkspec` | Sparse-checkout spec/CLI docs from Gitea, then answer questions or execute tasks on the DUT based on the spec — on demand, no full doc load |
| Ledcam | `/ledcam` | USB camera LED color detection for AXN-2020 front panel — calibrate, live feed, ROI selection (with profiles), and detect (green/amber/off) |
| Luascript | `/luascript` | Deploy, register, and run custom LuaCLI scripts on the AXN-2020 DUT |
| Mfgtest | `/mfgtest` | Clone mfgtest repo, set up WinPython, configure stage/SKU, override COM port, and run pytest manufacturing tests |
| Standup | `/standup` | Set up WinPython environment — extract installer, install pip packages, verify (counterpart to /teardown) |
| Teardown | `/teardown` | Clean up session state — kill HTTP servers, stop picoclaw, optionally remove NAT and power off DUT |

Detailed skill documentation is in `.claude/skills/<skill>/SKILL.md`.

## Host vs. DUT — Disambiguation Rule

Two machines are involved in this project:

| Nickname | What it is | How to run commands on it |
|----------|-----------|--------------------------|
| **Host** | Your Windows PC running Claude Code | Bash tool directly |
| **DUT** | AXN-2020 network switch (external device) | `/uart` skill via UART serial |

**When a command or task is ambiguous**, apply these rules in order:

1. If the user says "on the DUT", "on the device", "on the board", "on the AXN" → run via `/uart` skill on the DUT.
2. If the user says "locally", "on the host", "on my PC", "on Windows" → run via Bash on the Host.
3. If context makes it obvious (e.g. `ipconfig` = Host, `alphadiags` path = DUT) → use that.
4. If still ambiguous → **ask** before executing: "Did you mean to run this on the Host (PC) or the DUT (AXN-2020)?"

## AXN-2020 Platform Defaults

Standard configuration for the AXN-2020 network switch platform:

- **Serial port:** COM200, 115200 baud
- **Linux shell prompt:** `alphadiags:/#`
- **U-Boot prompt:** `Marvell>>`
- **Login required:** No (engineering sample)
- **Topology file:** `./axn-2020/i2c-topology.md`
- **If device is at U-Boot:** type `boot` to boot into Linux

## Temporary Files

All host-side logs, downloaded images, spec checkouts, and other transient files go in **`./tmp/`**:

| Content | Path pattern |
|---------|-------------|
| Firmware images (build output, netboot) | `./tmp/<image>` |
| UART / serial session logs | `./tmp/uart-session.log` |
| Netboot log | `./tmp/netboot.log` |
| Deploy log | `./tmp/deploy.log` |
| Picoclaw log | `./tmp/picoclaw.log` |
| Checkspec log | `./tmp/checkspec.log` |
| Spec documents (sparse checkout) | `./tmp/axn2000-cli/` |
| Lua scripts (host staging) | `./tmp/<script>.lua` |
| Batch command scripts | `./tmp/cmds.txt` |
| Mfgtest repo (working copy) | `./tmp/mfgtest/` |

`./tmp/` is gitignored. Always `mkdir -p ./tmp` before writing to it.

## Git Policy

Always ask for explicit permission before running `git commit` or `git push`. Never bundle them into the end of an implementation step — completing a task does not imply approval to commit or push.

## Architecture

### Serial Helper

`.claude/skills/uart/serial_helper.py` abstracts `pyserial` for all skills:
- Handles prompt detection (U-Boot, BusyBox, login prompts)
- Logs sessions to file for audit trails
- Cleans ANSI escape sequences from output
- Supports both interactive and batch command modes

### Windows Startup

1. Open `vspe_setup.vspe` to start virtual COM port (required for COM200)
2. Run `.\ps-setup.ps1` to open split terminal layout (4 panes: serial, build server SSH, etc.)

### Picoclaw Agent

`.claude/skills/picoclaw/` contains the picoclaw multi-channel LLM agent binary, `config.json`, and NAT helper scripts. Configured for Claude (`claude-sonnet-4.6`, max 32k tokens, up to 50 tool iterations). Used to relay Claude interactions across messaging channels (Telegram, Slack, etc.).
