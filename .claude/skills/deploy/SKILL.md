---
name: deploy
description: Transfer files FROM the Host PC TO the DUT (AXN-2020 external device) using HTTP server + wget, then optionally execute them on the DUT. Use when the user needs to deploy binaries, configs, or scripts from the local PC to the AXN-2020 device.
---

# deploy

Transfers files from the host PC to an embedded Linux device via HTTP server + wget over the Ethernet interface. Uses the `/uart` skill to run commands on the device.

## Prerequisites

- Device must have `wget` available (verify with `/uart`: `which wget`)
- Device must have a configured IP address on a shared subnet with the PC
- The serial helper: `.claude/skills/uart/serial_helper.py`

## Environment Variables

```
HELPER   = .claude/skills/uart/serial_helper.py
HTTP_SRV = .claude/skills/deploy/http_server.py
PORT     = COM200
BAUD     = 115200
PROMPT   = alphadiags:~#
PC_IP    = 30.0.0.1      # Host PC on direct Ethernet link
DEV_IP   = 30.0.0.100    # Device IP on same subnet
DEV_MASK = 255.255.255.0 # /24 for direct link
```

## Step-by-Step Workflow

### 0. Configure Device Network (if no IP assigned)

After boot, check if the device has an IP:
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 5 --logfile ./tmp/deploy.log --command "ifconfig eth0"
```

If no `inet addr` is shown, assign one on the 30.0.0.x direct-link subnet:
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 5 --logfile ./tmp/deploy.log --command "ifconfig eth0 $DEV_IP netmask $DEV_MASK up && echo 'IP OK'"
```

Then confirm PC and device can reach each other:
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 5 --logfile ./tmp/deploy.log --command "ping -c 2 $PC_IP"
```

### 1. Verify PC IP

The Host PC should have `30.0.0.1` configured on the direct Ethernet link to the DUT. Verify with:
```bash
ipconfig | grep "IPv4"
```

### 2. Start HTTP Server on the PC

Use the shared HTTP server helper — it automatically kills any existing server on the port before starting:

```bash
"$PYTHON" .claude/skills/deploy/http_server.py --start --dir ./tmp --bind $PC_IP --port 8080
```

Run this **in the background** (`run_in_background: true`).

Other helper commands:
```bash
# Check if server is running
"$PYTHON" .claude/skills/deploy/http_server.py --status --port 8080

# Stop server when done
"$PYTHON" .claude/skills/deploy/http_server.py --stop --port 8080
```

### 3. Download File on the Device

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" --timeout 30 --logfile ./tmp/deploy.log \
  --command "wget -O /tmp/<filename> http://$PC_IP:8080/<filename> && echo 'DOWNLOAD OK'"
```

### 4. Make Executable (if binary)

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" --timeout 5 --logfile ./tmp/deploy.log \
  --command "chmod +x /tmp/<binary> && ls -lh /tmp/<binary>"
```

### 5. Execute

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" --timeout 15 --logfile ./tmp/deploy.log \
  --command "/tmp/<binary>"
```

### 6. Stop HTTP Server

Stop the HTTP server when done to free port 8080:
```bash
"$PYTHON" .claude/skills/deploy/http_server.py --stop --port 8080
```

## Complete Example (deploy picoclaw)

```bash
PYTHON="$PYTHON"
HELPER=".claude/skills/uart/serial_helper.py"
PORT=COM200
BAUD=115200
PROMPT="alphadiags:~#"
PC_IP=30.0.0.1
DEV_IP=30.0.0.100
DEV_MASK=255.255.255.0

# 0. Configure device IP if needed
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 5 --command "ifconfig eth0 $DEV_IP netmask $DEV_MASK up && echo OK"

# 1. Start HTTP server (background — auto-kills any existing server on port)
"$PYTHON" .claude/skills/deploy/http_server.py --start --dir ./material/picoclaw --bind $PC_IP --port 8080 &

# 2. Download files
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 30 --command "wget -O /tmp/picoclaw-linux-arm64 http://$PC_IP:8080/picoclaw-linux-arm64 && echo OK"

PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 30 --command "wget -O /tmp/config.json http://$PC_IP:8080/config.json && echo OK"

# 3. Make executable and run
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 5 --command "chmod +x /tmp/picoclaw-linux-arm64"

PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --timeout 15 --command "/tmp/picoclaw-linux-arm64"
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `wget: Connection refused` | HTTP server not started or wrong IP | Confirm server is running; verify PC IP with `ipconfig` |
| `HTTP/1.0 404 File not found` | File not in served directory | Run directory listing check (Step 2); verify exact filename |
| `ifconfig eth0` shows no `inet addr` | Device network not configured | Run Step 0 to assign static IP |
| `ping $PC_IP` fails from device | Subnet mismatch or interface down | Ensure PC IP and device IP are on the same /24 subnet |
| `Permission denied` running binary | Missing execute bit | `chmod +x /tmp/<binary>` |
| `UnicodeEncodeError` (cp950/cp936) | Binary outputs UTF-8/emoji | Prefix with `PYTHONIOENCODING=utf-8` |
| `Address already in use` on port 8080 | Previous server still running | Use `http_server.py --start` (auto-kills existing) or `--stop` first |

## Notes

- Files land in `/tmp/` by default — this is a RAM disk and is lost on reboot. Use `/alpha/` or another persistent path if needed.
- Always stop the HTTP server background task when done.
- The device network config set via `ifconfig` is also lost on reboot. For persistent config, use a `diagenv` script on USB/eMMC.
- **Line endings:** The Host PC is Windows (CRLF) but the DUT and build server are Linux (LF). Before deploying text files (scripts, configs), convert to LF to avoid polluted git diffs and potential runtime issues:
  ```bash
  sed -i 's/\r$//' ./tmp/<filename>
  ```
  Or when copying to the remote build server via `scp`, convert first to prevent every line showing as changed in `git diff`.
