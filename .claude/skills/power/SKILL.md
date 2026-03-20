---
name: power
description: Control power to the DUT (AXN-2020) via the Aviosys IP Power 9258W2 network PDU — runs on the Host PC over HTTP, but affects the DUT's power. Use when the user wants to power on, off, toggle, or cycle the AXN-2020 device.
---

# power

Controls the **Aviosys IP Power 9258W2** network-attached PDU via its HTTP API. Outlets 1–4 can be turned on/off, toggled, or power-cycled independently.

## Configuration (hardcoded defaults in script)

| Setting | Value |
|---------|-------|
| IP Address | `10.56.17.6` |
| Username | `user` |
| Password | `user` |
| Script | `.claude/skills/power/ip_power.py` |
| Python | `$PYTHON` (from CLAUDE.md) |

**My device is connected to outlet 2.**

## Commands

### Check status of all outlets
```bash
"$PYTHON" .claude/skills/power/ip_power.py --status
```

Example output:
```
Outlet   State  Current
--------------------------
  1      OFF        0.0A
  2      ON         1.2A
  3      OFF        0.0A
  4      OFF        0.0A
```

### Turn outlet ON
```bash
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action on
```

### Turn outlet OFF
```bash
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action off
```

### Toggle outlet (ON→OFF or OFF→ON)
```bash
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action toggle
```

### Power cycle outlet (off → wait 5s → on)
```bash
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action cycle
```

Custom wait time (e.g. 10 seconds):
```bash
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action cycle --cycle-sec 10
```

## Skill Workflow

1. **Identify the action** from user intent: on / off / toggle / cycle / status
2. **Confirm the outlet number** — default is **2** unless user specifies otherwise
3. **Run the command** using the full Python path above
4. **Report the result** — print the current state after the action by running `--status`

### Example — "power off my device"
```bash
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action off
"$PYTHON" .claude/skills/power/ip_power.py --status
```

### Example — "reboot my device"
```bash
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action cycle --cycle-sec 5
"$PYTHON" .claude/skills/power/ip_power.py --status
```

## Override Host/Credentials (if needed)

```bash
"$PYTHON" .claude/skills/power/ip_power.py \
  --host 10.56.17.6 --user user --password user \
  --outlet 2 --action on
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| HTTP request times out (but ping works) | Aviosys web server only supports HTTP/1.0; previous keep-alive connection is stuck | Already handled in script via `Connection: close` header. If it persists, wait ~30s for the old connection to expire, then retry |
| `Connection refused` / timeout | Wrong IP or PDU offline | Verify `10.56.17.6` is reachable: `ping 10.56.17.6` |
| `401 Unauthorized` | Wrong credentials | Pass `--user` / `--password` with correct values |
| `ValueError: Outlet must be 1–4` | Invalid outlet number | Use `--outlet 1`, `2`, `3`, or `4` |
| Outlet shows ON but device unresponsive | Device still booting | Wait a few seconds and check device console |
