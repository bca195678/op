# UART Console Examples

## Example 1: Basic Connection and Device Info

**Scenario**: Connect to an embedded device and collect system information.

```bash
PYTHON=$PYTHON  # set per CLAUDE.md
HELPER=.claude/skills/uart/serial_helper.py
PORT=COM200
BAUD=115200
PROMPT="alphadiags:~#"
LOG=./output-1234.log
```

**Single commands:**
```bash
# System info
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --command "uname -a"
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --command "cat /proc/cpuinfo | head -20"
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --command "cat /proc/meminfo"

# Network
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --command "ifconfig -a"

# Storage
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --command "df -h"
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --command "cat /proc/mtd"

# Processes
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --timeout 5 --command "ps"
```

**Batch mode (all at once):**
```bash
echo -e "uname -a\nifconfig -a\ndf -h\nps" > cmds.txt
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --script cmds.txt
```

**BusyBox check** (most embedded devices):
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --logfile "$LOG" --command "busybox --list"
```

---

## Example 2: U-Boot Bootloader Interaction

**Scenario**: Device is at U-Boot prompt. Explore environment and boot into Linux.

**Connect and observe:**
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "Marvell>>" --logfile "$LOG" --command "printenv"
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "Marvell>>" --logfile "$LOG" --command "version"
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "Marvell>>" --logfile "$LOG" --command "bdinfo"
```

**Boot into Linux:**
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "Marvell>>" --logfile "$LOG" --command "boot"
```

---

## Tips and Tricks

### Baud Rate Detection
If you see garbled output, try common rates in order:
```
115200  57600  38400  19200  9600  230400
```

### Session Logging
Always log for later reference:
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device $PORT --baud $BAUD --prompt "$PROMPT" \
  --logfile ./session-$(date +%Y%m%d_%H%M%S).log \
  --interactive
```

Monitor live in a second terminal:
```bash
tail -f ./session-*.log
```

### Recovering from an Unresponsive Console

If the device stops responding, try running the helper again with a short timeout — it will re-open the port and send Enter to probe for a prompt:
```bash
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" --device $PORT --baud $BAUD --prompt "$PROMPT" --timeout 3 --command ""
```

On Linux, you can also write control characters directly to the device:
```bash
echo -ne '\003' > /dev/ttyUSB0   # Ctrl-C
echo -ne '\004' > /dev/ttyUSB0   # Ctrl-D
```

### Finding UART Pins on a PCB
1. Look for 3–5 pin headers (GND, TX, RX, optionally VCC)
2. Use a multimeter in continuity mode to identify GND (connects to ground plane)
3. Power on the device — TX will show activity on a logic analyzer or oscilloscope
4. RX is usually adjacent to TX
5. Check voltage level: typically 3.3V or 5V (do not mix!)
