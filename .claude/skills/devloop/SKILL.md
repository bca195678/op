---
name: devloop
description: Iterative fix-build-netboot-verify cycle on the remote build server and STARK DUT. Use when you need to modify source code, rebuild the image, and test it on the device — repeating until it works.
---

# devloop

Iterative development loop: edit source on the remote build server, rebuild the firmware image, transfer it to the Host PC, netboot it onto the STARK DUT, and verify it boots successfully. Repeats until the image works or the user stops.

## Prerequisites

- Device serial console available on COM200 (`/uart` skill)
- Device is at `u-boot>` prompt (autoboot disabled with `bootdelay=-1`)
- SSH access to the build server (`/fabrick` skill)
- Host PC Ethernet connected to DUT on 30.0.0.x subnet (`/netboot` skill)
- Power control available (`/power` skill)

## Environment Variables

```
PYTHON      = ./wpy64/python/python.exe
HELPER      = .claude/skills/uart/serial_helper.py
TFTP_SRV    = .claude/skills/netboot/tftp_server.py
PORT        = COM200
BAUD        = 115200
PROMPT_UBT  = u-boot>
PROMPT_LNX  = alphadiags:/#
HOST_IP     = 30.0.0.1
DUT_IP      = 30.0.0.100
LOAD_ADDR   = 0x70000000
BUILD_SERVER = chester@172.31.230.36
PROJECT_DIR  = ~/project/opdiag/summit-stark
```

## The Loop

```
┌─────────────────────────────────────────┐
│  1. Diagnose  — read boot logs / errors │
│  2. Fix       — edit source on remote   │
│  3. Rebuild   — docker.sh make          │
│  4. Fetch     — scp image to ./tmp/     │
│  5. Boot      — power cycle + netboot   │
│  6. Verify    — check boot output       │
│       │                                 │
│       ├── PASS → done                   │
│       └── FAIL → go to step 1           │
└─────────────────────────────────────────┘
```

## Step-by-Step

### Step 1 — Diagnose the Problem

If the device crashed or rebooted back to U-Boot, check the last boot output:

```bash
# Check recent serial log
tail -100 ./tmp/netboot.log
```

If the console was silent during boot (no error visible), the opdiag init silences output in normal mode. Re-netboot with debug bootargs:

```
setenv bootargs 'console=ttyS0,115200 opdiag_mode=normal opdiag_debug_for_internal_use'
```

### Step 2 — Fix Source on Remote Server

Use `/fabrick` to SSH in and edit files:

```bash
ssh chester@172.31.230.36
cd ~/project/opdiag/summit-stark
# edit the file(s)...
```

### Step 3 — Rebuild

**Important build caveats:**

| Component modified | Extra step before rebuild |
|-------------------|--------------------------|
| `diagnostics/diagpy/` (Python) | `rm -rf build/diagpy` — Makefile skips rebuild if directory exists |
| `diagnostics/diagk/` (C/Klish) | `rm -rf build/diagk` — same caching behavior |
| `rootfs.overlay/` (configs, scripts) | No extra step needed |
| `linux-*/` (kernel defconfig) | May need `rm -rf build/linux` for config changes |
| `buildroot-fs/` (rootfs defconfig) | May need full `rm -rf build/buildroot` |

Build command:

```bash
ssh -tt chester@172.31.230.36 "cd ~/project/opdiag/summit-stark && bash docker.sh make all -j16"
```

> Use `ssh -tt` for TTY allocation — required by `docker.sh`.

### Step 4 — Fetch Image to Host

Discover the latest image and copy it:

```bash
IMAGE=$(ssh chester@172.31.230.36 "ls -t ~/project/opdiag/summit-stark/image/ | grep -v '\.md5$' | head -1")
echo "Image: $IMAGE"
mkdir -p ./tmp
scp chester@172.31.230.36:~/project/opdiag/summit-stark/image/$IMAGE ./tmp/
```

### Step 5 — Power Cycle + Netboot

```bash
# Power cycle the DUT
"$PYTHON" .claude/skills/power/ip_power.py --outlet 2 --action cycle --cycle-sec 5

# Wait for U-Boot prompt (device takes a few seconds to reach U-Boot)
sleep 8
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device COM200 --baud 115200 --prompt "u-boot>" --timeout 15 --command "" \
  --logfile ./tmp/netboot.log

# Start TFTP server (background, 180s timeout)
"$PYTHON" .claude/skills/netboot/tftp_server.py \
  --dir ./tmp --ip 30.0.0.1 --port 69 --timeout 180
# (run_in_background: true)

# Configure U-Boot networking + bootargs
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device COM200 --baud 115200 --prompt "u-boot>" --timeout 10 \
  --command "setenv bootargs 'console=ttyS0,115200 opdiag_mode=normal opdiag_debug_for_internal_use'; setenv ipaddr 30.0.0.100; setenv serverip 30.0.0.1" \
  --logfile ./tmp/netboot.log

# TFTP download + boot (300s timeout for full opdiag run)
PYTHONIOENCODING=utf-8 "$PYTHON" "$HELPER" \
  --device COM200 --baud 115200 --prompt "alphadiags:/#" --timeout 300 \
  --command "tftpboot 0x70000000 $IMAGE; bootm 0x70000000" \
  --raw --logfile ./tmp/netboot.log
```

### Step 6 — Verify

Check the boot output for:

| What to look for | Meaning |
|-----------------|---------|
| `alphadiags:/#` prompt | Linux booted successfully |
| `Diagnostics completed.` | Opdiag ran to completion |
| `Summary: Diagnostics Pass` | All tests passed |
| `Summary: Diagnostics Fail` | Some tests failed (check which ones) |
| `Waiting for reboot...` | Opdiag finished and is rebooting |
| Python traceback | Code error — go back to Step 1 |
| Device resets to `u-boot>` silently | Crash — re-run with debug bootargs |

If the image works → done. If not → go back to Step 1.

---

## Bootargs Reference

| Bootargs | When to use |
|----------|-------------|
| `console=ttyS0,115200 opdiag_mode=normal` | Production-like test (console silenced) |
| `console=ttyS0,115200 opdiag_mode=normal opdiag_debug_for_internal_use` | Development (full console output visible) |
| `console=ttyS0,115200 opdiag_mode=extended` | Extended test suite |
| `console=ttyS0,115200` | Boot to shell only (no opdiag — missing opdiag_mode) |

## Gotchas

1. **Silent crashes** — `prep_opdiag()` in the init script redirects stdout/stderr to `/dev/null` in normal mode. Always use `opdiag_debug_for_internal_use` during development.

2. **diagpy wheel caching** — The Makefile checks `if [ ! -d build/diagpy ]` before building. After editing any file under `diagnostics/diagpy/`, you MUST `rm -rf build/diagpy` or the old wheel is repackaged.

3. **TFTP server timeout** — The TFTP server auto-exits after its timeout. For large images (~43MB), the transfer takes ~30s. Set timeout to at least 180s to account for rebuild delays.

4. **Power cycle vs soft reboot** — If the device is hung (no serial response), use `/power` to hard cycle. If at U-Boot prompt, just netboot directly.

5. **bootdelay=-1 vs -2** — `-1` = stay at U-Boot forever (what we want). `-2` = autoboot immediately with no way to interrupt.

6. **Load address** — STARK DRAM is `0x60000000–0xdfffffff`. Always use `0x70000000`. The old AXN-2020 address `0x210000000` is out of range.

7. **FIT config** — `bootm 0x70000000` with no `#config` suffix. The default FIT configuration `stark` is selected automatically.

---

## Example Prompt

If you want to invoke this workflow conversationally instead of as a skill:

```
On the remote build server (172.31.230.36), project ~/project/opdiag/summit-stark:
1. [describe the fix needed]
2. Rebuild with: rm -rf build/diagpy && bash docker.sh make all -j16
3. Fetch the new image to ./tmp/
4. Power cycle the DUT and netboot the image with debug bootargs
5. Check if it boots and opdiag completes successfully
6. If it fails, diagnose and repeat until it works
```
