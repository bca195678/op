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
| `rootfs.overlay/` (configs, scripts, opdiag) | `rm -rf build/rootfs` — overlay is cached and NOT re-applied without this |
| `linux-*/` (kernel defconfig) | `rm -rf build/linux` — required for config changes |
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

These flags can be combined with any of the above:

| Flag | Effect |
|------|--------|
| `opdiag_no_reboot` | Drop to interactive CLI after POST completes instead of rebooting |
| `opdiag_stop_if_fail` | Pause at interactive CLI on first test failure |
| `opdiag_linuxsh` | Skip POST entirely, drop to Linux shell |

**These three flags are commented out by default** in `rootfs.overlay/etc/profile.d/99-opdiag.sh` (`parse_opdiag_opt()` function). To use them during development, uncomment the relevant `case` blocks in that file and rebuild. Remember to re-comment them before committing to production.

Example — debug with no reboot (inspect results interactively):
```
setenv bootargs 'console=ttyS0,115200 opdiag_mode=normal opdiag_debug_for_internal_use opdiag_no_reboot'
```

## Gotchas

1. **Silent crashes** — `prep_opdiag()` in the init script redirects stdout/stderr to `/dev/null` in normal mode. Always use `opdiag_debug_for_internal_use` during development.

2. **Build cache — ALL components are cached.** The build system caches aggressively. After editing source, you MUST clear the relevant `build/` subdirectory or your changes are silently ignored:
   - `rm -rf build/diagpy` — after editing `diagnostics/diagpy/` (Python wheel)
   - `rm -rf build/diagk` — after editing `diagnostics/diagk/` (C/Klish)
   - `rm -rf build/rootfs` — after editing `rootfs.overlay/` (opdiag script, init, configs, quickstart scripts)
   - `rm -rf build/linux` — after editing kernel defconfig
   - When in doubt, `rm -rf build/rootfs build/diagpy` covers the most common cases.

3. **TFTP server timeout** — The TFTP server auto-exits after its timeout. For large images (~43MB), the transfer takes ~30s. Set timeout to at least 180s to account for rebuild delays.

4. **Power cycle vs soft reboot** — If the device is hung (no serial response), use `/power` to hard cycle. If at U-Boot prompt, just netboot directly.

5. **bootdelay=-1 vs -2** — `-1` = stay at U-Boot forever (what we want). `-2` = autoboot immediately with no way to interrupt.

6. **Load address** — STARK DRAM is `0x60000000–0xdfffffff`. Always use `0x70000000`. The old AXN-2020 address `0x210000000` is out of range.

7. **FIT config** — `bootm 0x70000000` with no `#config` suffix. The default FIT configuration `stark` is selected automatically. **Exception: DIN-8T-8XE** (`4630R-8T-8XE-DN`, board ID 0x01) requires `bootm 0x70000000#pci` to enable PCIe for BCM56071 detection. Without `#pci`, PTP tests fail and unit 1 ports are invisible.

8. **rootfs.overlay cache is the sneakiest** — Unlike diagpy (which at least requires a missing directory), the rootfs overlay is silently stale. If you edit `rootfs.overlay/alpha/bin/opdiag` and rebuild without `rm -rf build/rootfs`, the old opdiag is packaged into the image. Always verify: `grep 'your_change' build/rootfs/alpha/bin/opdiag` after rebuilding.

9. **opdiag runtime file naming** — The boot script `99-opdiag.sh` runs `/alpha/bin/opdiag` (generic name), NOT `/alpha/bin/opdiag-stark`. When manually copying overlay files for incremental builds, you must copy to **both**:
   ```bash
   cp rootfs.overlay/alpha/bin/opdiag build/rootfs/alpha/bin/opdiag
   cp rootfs.overlay/alpha/bin/opdiag build/rootfs/alpha/bin/opdiag-stark
   ```
   The TOML config uses the `-stark` suffix (`opdiag-stark.toml`), but the script itself runs as `opdiag`.

10. **BCM script types: `.soc` vs `.cint`** — BCM SDK has two script formats with different interpreters:
    - `.soc` files → run with `bcmcmd "rcload /path/file.soc"` (BCM shell commands)
    - `.cint` files → run with `bcmcmd "cint /path/file.cint"` (C interpreter syntax)
    Using `rcload` on a `.cint` file causes `Unknown command` errors because C function calls (like `cint_reset()`) aren't valid shell commands.

11. **diagk XML syntax** — If `diagnostics/diagk/cli/xml/diag-cmd.xml` has malformed XML (e.g., missing attribute quotes), the CLI silently fails to load and opdiag crashes with `Unable to open file '/alpha/xml/diag-cmd.xml'`. Always validate XML after editing: `python3 -c "import xml.etree.ElementTree as ET; ET.parse('diagnostics/diagk/cli/xml/diag-cmd.xml'); print('OK')"`

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
