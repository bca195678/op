# Observing Serial Console Sessions

This guide explains how to monitor and observe what's happening on the serial console in real-time while the helper script is interacting with the device.

## Method 1: Built-in Logging (Easiest — RECOMMENDED)

**Terminal 1 — Run the helper script with logging:**
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 \
  --baud 115200 \
  --prompt "alphadiags:/#" \
  --logfile ./session.log \
  --interactive
```

**Terminal 2 — Watch the log in real-time:**
```bash
tail -f ./session.log
```

### What Gets Logged

- Session start/end timestamps
- All data sent to the device (commands)
- All data received from the device (responses, prompts, echoes)
- Raw I/O exactly as it appears on the wire

### Example Log Output

```
============================================================
Session started: 2025-10-19T23:20:27.384436
Device: COM200 @ 115200 baud
============================================================

alphadiags:/#
alphadiags:/# uname -a
Linux alphadiags 5.10.0 #1 SMP Mon Jan 1 00:00:00 UTC 2024 aarch64 GNU/Linux

alphadiags:/#
alphadiags:/# ifconfig
eth0  Link encap:Ethernet  HWaddr 00:11:22:33:44:55
      inet addr:10.0.0.2  Bcast:10.0.0.255  Mask:255.255.255.0
[...]

============================================================
Session ended: 2025-10-19T23:20:29.130706
============================================================
```

### Advantages

- No additional setup required
- Works with all modes (single command, interactive, batch)
- Doesn't interfere with the serial connection
- Can be tailed from another terminal
- Persistent record for later reference

### Limitations

- Not truly real-time (line-buffered, so minimal delay)
- Requires specifying `--logfile` when starting

---

## Method 2: Using socat for Port Mirroring (Advanced, Linux only)

For true real-time observation or when you need multiple simultaneous connections, use `socat` to create a virtual serial port that mirrors the real one.

**Terminal 1 — Create virtual ports:**
```bash
sudo socat -d -d \
  PTY,raw,echo=0,link=/tmp/vserial0 \
  PTY,raw,echo=0,link=/tmp/vserial1
```

**Terminal 2 — Bridge real device to virtual port:**
```bash
sudo socat /dev/ttyUSB0,raw,echo=0,b115200 /tmp/vserial0
```

**Terminal 3 — Run helper on bridge:**
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device /tmp/vserial1 \
  --prompt "alphadiags:/#" \
  --interactive
```

**Terminal 4 — Observe on second virtual port:**
```bash
picocom -b 115200 --nolock --echo --omap crlf /tmp/vserial0
```

### Advantages

- True real-time observation
- Multiple processes can monitor simultaneously
- Most flexible approach

### Limitations

- Complex multi-terminal setup
- Requires `socat` installed
- Requires root/sudo

---

## Method 3: Using screen with Logging

**Start screen with logging:**
```bash
screen -L -Logfile ./serial_screen.log /dev/ttyUSB0 115200
```

Monitor in another terminal:
```bash
tail -f ./serial_screen.log
```

### Advantages

- Built into screen, simple
- Good for manual interaction

### Limitations

- Not suitable for automated scripting
- Less control over output format

---

## Method 4: Direct Device File Monitoring (Read-Only, debugging only)

**Terminal 1 — Run helper normally:**
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device /dev/ttyUSB0 --interactive
```

**Terminal 2 — Read-only spy:**
```bash
cat /dev/ttyUSB0 | tee ./spy.log
```

> **Warning:** Unreliable — may miss data already read by the helper. Only use for debugging if other methods don't work.

---

## Comparison

| Method | Real-time | Easy Setup | Multi-Observer | Reliable | Recommended |
|--------|-----------|------------|----------------|----------|-------------|
| Built-in Logging | Near | Yes | Limited | Yes | **Best** |
| socat Mirror | Yes | Complex | Yes | Yes | Advanced |
| screen -L | Near | Yes | Limited | Yes | Manual use |
| cat spy | Yes | Yes | Yes | No | Last resort |

---

## Recommended Workflow

### Watching Claude interact with a device

1. **Before starting**, open a log watcher:
   ```bash
   touch ./device_session.log
   tail -f ./device_session.log
   ```

2. **Tell Claude to use logging:**
   ```
   Please use --logfile ./device_session.log so I can watch what's happening.
   ```

3. Watch the first terminal to see real-time I/O.

### Manual debugging

```bash
# Terminal 1 — interactive with debug output
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 \
  --prompt "alphadiags:/#" \
  --logfile ./debug.log \
  --debug \
  --interactive

# Terminal 2 — watch log
tail -f ./debug.log
```

---

## Troubleshooting

### Log file not updating
```bash
# Make sure the file exists
touch ./session.log
tail -f ./session.log

# Check file size is growing
ls -lh ./session.log
```

### Permission denied on serial port
```bash
# Check what process is using it
fuser /dev/ttyUSB0

# Add user to dialout group (Linux)
sudo usermod -a -G dialout $USER
```

### socat "device busy" error
```bash
sudo fuser -k /dev/ttyUSB0
sleep 1
# retry socat
```

---

## Best Practices

1. **Always log important sessions** — use descriptive filenames with timestamps:
   ```bash
   --logfile "./session-$(date +%Y%m%d_%H%M%S).log"
   ```

2. **Combine --debug with --logfile** to capture both debug info and I/O:
   ```bash
   PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
     --device COM200 --command "uname -a" \
     --logfile session.log --debug 2>&1 | tee debug.txt
   ```

3. **Compress old logs** to save space:
   ```bash
   gzip ./old_session.log
   ```

---

## Summary

**For most cases:** Use `--logfile` and `tail -f` in a second terminal — simple, reliable, works on Windows.

**For advanced needs:** Use socat for true real-time multi-process observation (Linux only).

**Quick reference:**
```bash
# Terminal 1 — run with logging
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 \
  --prompt "alphadiags:/#" \
  --logfile ./session.log \
  --interactive

# Terminal 2 — watch live
tail -f ./session.log
```
