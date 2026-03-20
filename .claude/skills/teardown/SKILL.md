---
name: teardown
description: Clean up session state — kill stale HTTP servers, stop picoclaw gateway on DUT, optionally remove Windows NAT and power off. Use when ending a workbench session.
---

# teardown

Cleans up persistent session state on both the Host PC and DUT. Designed to be run when leaving the workbench or ending a Claude Code session.

## What Gets Cleaned Up

| # | Target | Location | Default | Flag to change |
|---|--------|----------|---------|----------------|
| 1 | Stale HTTP servers (port 808x) | Host | Killed | — |
| 2 | Picoclaw gateway | DUT | Killed via UART | — |
| 3 | Windows NAT + IP forwarding | Host | Removed | `--keep-nat` to skip |
| 4 | DUT power (outlet 2) | DUT | Left on | `--power-off` to turn off |

**Not cleaned** (by design):
- `./tmp/` files (logs, images, spec checkouts)
- VSPE, miniterm, SSH sessions (user's terminal panes)
- DUT network/clock/certs (lost on reboot anyway)

## Commands

### Full teardown (default)
```bash
"$PYTHON" .claude/skills/teardown/teardown.py
```

### Keep NAT active
```bash
"$PYTHON" .claude/skills/teardown/teardown.py --keep-nat
```

### Full teardown + power off DUT
```bash
"$PYTHON" .claude/skills/teardown/teardown.py --power-off
```

### Keep NAT, power off DUT
```bash
"$PYTHON" .claude/skills/teardown/teardown.py --keep-nat --power-off
```

### All flags
```
--keep-nat       Do not remove Windows NAT rule (keeps DUT-NAT and IP forwarding)
--power-off      Power off DUT outlet 2 after cleanup
--device COM200  DUT serial port (default: COM200)
--baud 115200    Baud rate (default: 115200)
```

## Example Output

```
Component              Result
--------------------------------------------
HTTP servers           2 killed
Picoclaw gateway       killed
Windows NAT            removed
DUT power              skipped (use --power-off)
```

## Skill Workflow

1. Determine user intent:
   - "teardown" / "clean up" → no flags
   - "keep NAT" / "don't remove NAT" → `--keep-nat`
   - "power off" / "shut down" / "turn off" → `--power-off`
2. Run `"$PYTHON" .claude/skills/teardown/teardown.py [flags]`
3. Report the summary table

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `serial error: could not open port` | Another process holds COM200 | Close miniterm or other serial client first |
| NAT shows `no result file` | Elevated PowerShell was cancelled by user | Re-run; accept the UAC prompt |
| Picoclaw shows `unknown` | DUT unresponsive or not booted | Power cycle via `/power`, or ignore |
| `ip_power.py not found` | Power skill not installed | Check `.claude/skills/power/` exists |
