---
name: uart
description: Run commands ON the DUT (AXN-2020 external device) via UART serial console — NOT on the local Host PC. Use when the user needs to send commands to, read output from, or gather info from the AXN-2020 hardware over a serial COM port.
---

# uart

Interact with embedded devices over a UART serial connection using the Python serial helper. Supports single commands, batch scripts, and interactive sessions — with automatic prompt detection and session logging.

## Environment Variables (set at start of session)

```
HELPER  = .claude/skills/uart/serial_helper.py
PORT    = COM200
BAUD    = 115200
PROMPT  = alphadiags:/#        # adjust for your device
LOG     = ./tmp/uart-session.log
```

## Serial Helper — Core Commands

### Single command
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --logfile "$LOG" --command "uname -a"
```

### Batch commands from file
```bash
echo -e "uname -a\nifconfig\ndf -h" > ./tmp/cmds.txt
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --logfile "$LOG" --script ./tmp/cmds.txt
```

### Interactive mode
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" --interactive
```

### Monitor session in real-time (separate terminal)
```bash
tail -f ./tmp/uart-session.log
```

Always include `--logfile` so the user can monitor activity live.

## Serial Helper Options

```
Connection:
  --device, -d DEV       Serial port (e.g. COM200, /dev/ttyUSB0)
  --baud,   -b RATE      Baud rate (default: 115200)
  --timeout,-t SECONDS   Command timeout (default: 3.0)
  --prompt, -p PATTERN   Shell prompt regex

Mode (pick one):
  --command, -c CMD      Single command
  --interactive, -i      Interactive session
  --script, -s FILE      Batch commands from file

Output:
  --raw, -r              Raw output (include echoes and prompts)
  --json, -j             JSON output
  --logfile, -l FILE     Log all I/O to file
  --debug                Show debug info
```

## Common Prompt Patterns

```bash
--prompt "alphadiags:/#"          # AXN-2020 Linux shell
--prompt "Marvell>>"              # AXN-2020 U-Boot
--prompt "[#\$]\s*$"              # Generic root/user shell
--prompt "=>\s*$"                 # U-Boot (generic)
--prompt "MyDevice>"              # Custom prompt
```

## Waiting for Device to Boot

After powering on, use a long timeout with an empty command to wait for the Linux prompt:

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" --timeout 120 --command ""
```

The device boot sequence on AXN-2020 produces:
1. Kernel messages (`[  x.xxxxxx] ...`)
2. Python package installation (`Processing /alpha/whl/...`)
3. `Scanning devices...`
4. `alphadiags:/#` prompt ready

**AXN-2020 boots in ~120+ seconds** — the first 120s wait will often time out mid-boot. Simply run the same command again; it will catch the prompt as soon as it appears.

## Detecting Console State After Connect

Press Enter a few times after connecting. Identify which state the device is in:

| Output | State | Next step |
|--------|-------|-----------|
| `Marvell>>` / `=>` / `U-Boot>` | Bootloader | See U-Boot section below |
| `login:` / `Password:` | Login prompt | Enter credentials |
| `#` / `$` / device prompt | Shell ready | Run commands |
| Nothing / garbled | Wrong baud or disconnected | Try 57600, 38400, 9600 |

**If stuck at U-Boot on AXN-2020:** type `boot` to boot into Linux.

## Device Information Gathering

Once at a Linux shell, collect system info:

```bash
# System
uname -a
cat /proc/version
cat /proc/cpuinfo | head -20
cat /proc/meminfo

# Firmware / OS version
cat /etc/issue
cat /etc/*release* 2>/dev/null

# Network
ifconfig -a
ip addr show
cat /etc/resolv.conf

# Storage
df -h
mount
cat /proc/mtd        # Flash partitions (embedded devices)

# Processes
ps
top -b -n 1

# Hostname
hostname
```

## U-Boot Auto-Repeat Warning

U-Boot repeats the **last command** when it receives a bare Enter (newline). The serial helper sends an initial newline to detect the prompt — this triggers auto-repeat of whatever command ran before (e.g., `tftpboot` runs again unexpectedly).

**Workaround:** When you need to send a command after a long-running U-Boot command (like `tftpboot`), send **Ctrl+C first** to break the auto-repeat cycle, then send your actual command. Use a direct pyserial script:

```python
import serial, time, sys
port = serial.Serial('COM200', 115200, timeout=1)
port.reset_input_buffer()
port.write(b'\x03')          # Ctrl+C breaks auto-repeat
time.sleep(0.5)
port.reset_input_buffer()
port.write(b'bootm 0x70000000\r\n')  # now send real command
# ... read output until prompt ...
port.close()
```

**Or** combine `tftpboot` and `bootm` in a single serial_helper call using `&&` so there's no gap:

```bash
--command "tftpboot 0x70000000 $IMAGE && bootm 0x70000000"
```

This avoids the auto-repeat entirely because U-Boot processes both commands before returning to the prompt.

## U-Boot Common Commands

```bash
# Show environment
printenv

# Boot into Linux
boot

# Network info
printenv ipaddr serverip

# Board and version info
bdinfo
version

# Memory display
md <address>
```

## BusyBox Notes

Most embedded devices use BusyBox. Commands work but may have fewer flags than full Linux equivalents.

```bash
# Check available applets
busybox --list

# Commonly available
cat, ls, cd, pwd, cp, mv, rm, mkdir, chmod
ps, kill, df, mount, grep, find, sed, ifconfig, ping, wget
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Garbled output | Wrong baud rate | Try 57600, 38400, 19200, 9600 |
| No output at all | Cable, power, or wrong port | Check connections; press Enter a few times |
| `Permission denied` on port | Port in use or no access | Close other terminal tools using the port |
| Commands not appearing | No local echo | Add `--raw` to see full output |
| Timeout before prompt | Device is slow | Increase `--timeout 10` or more |
| `UnicodeEncodeError` | Windows code page issue | Prefix with `PYTHONIOENCODING=utf-8` |
