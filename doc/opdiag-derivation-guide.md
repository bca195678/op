# Plan: Derive Operational Diagnostics (summit-stark) from Manufacturing Diagnostics (stark-diag)

## Context

The project has an established pattern for deriving operational (field) diagnostics from manufacturing diagnostics. This pattern is proven in two product families:
- **fjord-diag** (mfg) -> **summit-bcma55** (opdiag) — single-board
- **firefly-diag** (mfg) -> **summit-rz** (opdiag) — multi-board (2 boards)

Now we apply the same pattern to the Stark product family (4 boards):
- **stark-diag** (mfg) -> **summit-stark** (opdiag, to be created)

---

## Part 1: Derivation Guide — How to Derive Operational Diag from Manufacturing Diag

### 1.1 Overview

Manufacturing diagnostics (mfg-diag) are interactive, CLI-driven, and used by factory operators. Operational diagnostics (opdiag) are self-running, automated POST that run unattended in the field. The transformation involves:

- **Keeping** the entire diagnostics engine (diagk C module + diagpy Python package) unchanged
- **Keeping** all hardware configs (TOML files, BCM configs, LED firmware)
- **Adding** an automation layer that drives the Klish CLI via pexpect
- **Replacing** the manufacturing boot flow with an opdiag boot flow
- **Modifying** quickstart scripts, init, kernel/buildroot configs, and Python packages for opdiag mode

### 1.2 Files ADDED for Operational Diagnostics

| File | Purpose |
|------|---------|
| `rootfs.overlay/alpha/bin/opdiag` | **Core**: Python script that automates test execution via pexpect -> Klish CLI |
| `rootfs.overlay/alpha/toml/opdiag.toml` | Test item list, CLI/Linux prompt regex patterns, log paths |
| `rootfs.overlay/alpha/bin/diagpart` | Shell utility to mount/umount/check the diagnostics flash partition |
| `rootfs.overlay/alpha/bin/pldwdtd` | Watchdog kicker daemon (kicks MCU watchdog every 10s) |
| `rootfs.overlay/etc/profile.d/99-opdiag.sh` | Boot-time launcher: parses cmdline, inits console, runs opdiag, reboots |
| `rootfs.overlay/etc/init.d/S15pldwdt` | Init script to start watchdog daemon |

### 1.3 Files REMOVED (manufacturing-only)

| File | Purpose |
|------|---------|
| `rootfs.overlay/etc/init.d/S91diagenv` | Loads diagenv from USB/SSD (mfg networking/env setup) |
| `rootfs.overlay/etc/init.d/S99diagps` | Runs external diagps scripts from USB/SSD |
| `rootfs.overlay/etc/init.d/S80mount` | Manufacturing mount script (replaced by diagpart) |

### 1.4 Files MODIFIED

| File | Change |
|------|--------|
| `rootfs.overlay/alpha/toml/board.toml` | Add `opdiag_toml = "/alpha/toml/opdiag.toml"` to each board entry |
| `diagnostics/diagpy/diagpy/board_init.py` | Add `opdiag_toml()` property method to `Board_INFO` class (required for opdiag to read `opdiag_toml` from board.toml) |
| `rootfs.overlay/init` | Replace mfg init with opdiag init containing `prep_opdiag()` function (see 1.8) |
| `rootfs.overlay/alpha/script/quickstart_*` | Add VLAN deletion + MAC loopback; remove unused SerDes TBD comments (see 1.9) |
| `rootfs.overlay/etc/profile.d/prompt.sh` | Fix `nounset` safety: add `KLISH=${KLISH:-}` default, use proper quoting `[ -n "$KLISH" ]` |
| `rootfs.overlay/alpha/whl/requirements.txt` | Remove mfg-only packages: `pytest`, `pytest-loop`, `rpyc` |
| `rootfs.overlay/alpha/whl/*.whl` | Remove mfg-only wheel files (see 1.10) |
| `linux-*/arch/arm64/configs/*_defconfig` | Disable `MAGIC_SYSRQ`, add quiet console log levels (see 1.11) |
| `buildroot-fs/configs/*_defconfig` | Remove debug packages: GDB, strace, stress-ng, valgrind (see 1.12) |
| `env.mk` | Update `project_name` and optionally `project_version` |

### 1.5 Files UNCHANGED

- `diagnostics/diagk/` — entire C-based Klish CLI, PFE, diag tests, gearbox
- `diagnostics/diagpy/` — entire Python package (drivers, apps), **except** `diagpy/board_init.py` which needs an `opdiag_toml()` method added (see 1.4)
- `rootfs.overlay/alpha/toml/<board>/` — per-board TOML configs
- `rootfs.overlay/alpha/bcm/` — ASIC configs, LED firmware, ASIC test scripts
- `sdk/`, `packages/` — SDK and external packages
- `Makefile`, `bcmsdk_tool.mk` — build system

### 1.6 The `opdiag` Script Architecture

The opdiag Python script follows a consistent pattern across all product families:

**Class hierarchy:**
```
OpdiagHelper (base)          — generic automation framework
  └── OpdiagCustom (derived) — product-specific test implementations
```

**OpdiagHelper provides:**
- pexpect-based CLI automation (spawns `/alpha/bin/cli`)
- `send_command(cmd, pass_pattern, fail_pattern, timeout)` — core command executor
- `dut_init()` — runs quickstart, checks MAC/gearbox init
- `check_system_eeprom()` — reads product_name, part_number, serial_number
- Result collection, rolling log management (operational-results-0..9.txt)
- diagpart mount verification and log storage

**OpdiagCustom provides:**
- `trans_product_name()` — maps EEPROM product name to display name
- `@TestItemDecorator()` decorated test methods, one per test item
- Multi-board handling: branches on `self.product_name` for board-specific port ranges

**Multi-board pattern** (from summit-rz reference):
- `self.product_name` is read from system EEPROM at init
- Board-specific tests branch with `if self.product_name == '...':`
- MAC loopback uses `all` wildcard (board-independent)
- PHY copper/fiber loopback uses explicit port ranges per board
- Snake test uses `all` wildcard
- PoE test is board-agnostic (validates whatever ports exist)

### 1.7 The `99-opdiag.sh` Boot Launcher

- Parses kernel cmdline: `opdiag_mode=normal|extended`, `diagnostics_partition=<dev>`
- Development params: `opdiag_verbose`, `opdiag_linuxsh`, `opdiag_stop_if_fail`, `opdiag_no_reboot`
- Initializes console (stty, baud rate, echo disable)
- Sources `/etc/RELEASE.diag` for version info
- Calls `/alpha/bin/opdiag --mode=<mode> --release-version=<ver> --release-date=<date>`
- After completion: unmounts diagpart, stops RC services, resets board via MCU

**Console port varies by platform:**
- summit-bcma55 (Fjord/BCM): `/dev/ttyS0`
- summit-rz (Firefly/Renesas RZ): `/dev/ttySC0`
- summit-stark (Stark/BCM): `/dev/ttyS0` (confirmed from stark-diag uartcast.bash)

### 1.8 The `rootfs.overlay/init` — Console Redirection

The mfg init is minimal (mount filesystems, set hostname, enable mdev hotplug, register coredump handler, exec init). The opdiag init replaces it with a `prep_opdiag()` function that controls console output:

- **Normal mode** (default): Redirects stdin/stdout/stderr to `/dev/null` and disables console on ttyS0. This prevents any kernel or userspace output from appearing on the serial console during automated POST.
- **Debug mode** (`opdiag_debug_for_internal_use` kernel cmdline param): Redirects to the serial console, resets terminal, and sets printk level to verbose.

**Key differences from mfg init:**
- **Removed**: `echo "/sbin/mdev" > /proc/sys/kernel/hotplug` — opdiag uses devtmpfs (mounted as `/dev`) which provides automatic device node creation without needing mdev.
- **Removed**: `/alpha/bin/alphach --register` — coredump handler is moved to `99-opdiag.sh` and only runs conditionally in `OPDIAG_DEV` mode.
- **Added**: `prep_opdiag()` function, devpts mount, /dev/shm mount, /dev/fd symlink, /var/run and /var/lock directories.

**Known cosmetic issue:** The line `mount -t tmpfs -o nodev,nosuid,noexec shm /dev/shm` may produce `mount: mounting shm on /dev/shm failed: Invalid argument` on some kernels. This is **non-fatal** and does not affect opdiag operation. It appears on the serial console between `Starting kernel ...` and `Initializing operational diagnostics...` as `[H[J` (ANSI clear screen) immediately follows it.

### 1.9 Quickstart Script Modifications

Mfg quickstart scripts initialize hardware for interactive use. Opdiag quickstart scripts add two critical lines to isolate ports for loopback testing:

```
! Delete all ports from VLAN ID 1.
config vlan member delete 1 all

! Set all ports to MAC loopback mode.
config interface loopback all mac
```

These are added before `config interface startup all`. The unused "Apply the default SerDes settings" TBD comments are removed.

**Why:** In opdiag, ports must be removed from VLAN 1 to prevent traffic forwarding during loopback tests. MAC loopback is the default starting state; individual test methods then reconfigure loopback mode as needed (e.g., PHY loopback for copper/fiber tests).

**Reference patterns:**
- summit-bcma55: `config vlan member delete 1 @fp,@u` + `config interface loopback @fp,@u phy`
- summit-rz: `config vlan member delete 1 all` + `config interface loopback all mac`

### 1.10 Python Packages Cleanup

Remove manufacturing-only Python packages that are not needed for opdiag:

**requirements.txt** — keep only: `diagpy`, `pyserial`, `pexpect`

**Wheel files to remove:**
- `pytest-*.whl`, `pytest_loop-*.whl`, `pytest_ordering-*.whl` — test framework (mfg only)
- `rpyc-*.whl`, `plumbum-*.whl` — remote procedure call (mfg only)
- `iniconfig-*.whl`, `packaging-*.whl`, `pluggy-*.whl` — pytest dependencies
- `pygments-*.whl` — syntax highlighting (mfg only)
- `tomli-*.whl` — TOML parser for Python <3.11 (not needed, `toml` package is used)

**Wheel files to keep:** `pexpect`, `ptyprocess`, `pyserial`, `smbus2`, `toml`

### 1.11 Linux Kernel Defconfig Changes

Opdiag needs a quieter console to prevent kernel messages from interfering with test output. The manufacturing defconfig typically has `LOGLEVEL_DEFAULT=7` (verbose) and `PRINTK_TIME=y` — these must be changed:

```
# Disable Magic SysRq (not needed in field, security risk)
# CONFIG_MAGIC_SYSRQ is not set

# Disable kernel message timestamps (noisy on console)
# CONFIG_PRINTK_TIME is not set

# Suppress kernel console messages (only emergencies)
CONFIG_CONSOLE_LOGLEVEL_DEFAULT=1
CONFIG_CONSOLE_LOGLEVEL_QUIET=1
```

**Why this matters:** Without these changes, every kernel message (including timestamped driver init lines) appears on the serial console between `Starting kernel ...` and `Initializing operational diagnostics...`. With `LOGLEVEL=1`, only emergency messages pass through. Combined with `prep_opdiag()` in the init script (which redirects stdout/stderr to `/dev/null` and disables the ttyS0 console), this produces a clean output identical to summit-bcma55.

**Note:** After changing the defconfig, the kernel must be rebuilt: `rm -rf build/linux` before `make all`.

### 1.12 Buildroot Defconfig Changes

Remove debug/development packages not needed in opdiag:

```
# Remove these lines:
BR2_PACKAGE_GDB=y
BR2_PACKAGE_GDB_SERVER=y
BR2_PACKAGE_GDB_DEBUGGER=y
BR2_PACKAGE_GDB_TUI=y
BR2_PACKAGE_STRACE=y
BR2_PACKAGE_STRESS_NG=y
BR2_PACKAGE_VALGRIND=y
```

Note: `BR2_PACKAGE_MMC_UTILS` is platform-specific (not mfg vs opdiag) — keep it if present in the mfg base.

---

## Part 2: Implementation Plan for summit-stark

### Step 1: Copy stark-diag as Base

```bash
cp -r stark-diag summit-stark
```

### Step 2: Modify `board.toml` — Add opdiag_toml to Each Board

File: `summit-stark/rootfs.overlay/alpha/toml/board.toml`

Add `opdiag_toml = "/alpha/toml/opdiag.toml"` to all 4 board entries (board-0 through board-3).

### Step 2b: Modify `board_init.py` — Add opdiag_toml() Method

File: `summit-stark/diagnostics/diagpy/diagpy/board_init.py`

The `Board_INFO` class reads board.toml entries but does not expose `opdiag_toml` by default. Add the property method before `port_prefix_default()`:

```python
def opdiag_toml(self):
    return self._board_info[opdiag_toml]
```

> **Critical:** Without this method, opdiag crashes at boot with `AttributeError: Board_INFO object has no attribute opdiag_toml`. The error is hidden in normal mode because `prep_opdiag()` silences console output — use `opdiag_debug_for_internal_use` kernel cmdline param to see the traceback.

### Step 3: Create `opdiag.toml`

File: `summit-stark/rootfs.overlay/alpha/toml/opdiag.toml`

```toml
[opdiag]
linux_prompt = '(?:\(KLISH\)\s)?alphadiags:(?:\/\w+)*\/?#\s*'
cli_prompt = 'DIN-8W-4X>>\s*|DIN-8T-8XE>>\s*|RM-24W-8XE>>\s*|RM-4MW-12W-4XE>>\s*'
verbose_log_path = '/tmp/verbose.log'
flow_log_path = '/tmp/{item_name}_res.txt'

#
# NOTE: DO NOT CHANGE THE ITEM ORDER
#
[[opdiag.test_items]]
name = 'i2c environment'

[[opdiag.test_items]]
name = 'internal flash'

[[opdiag.test_items]]
name = 'memory'

[[opdiag.test_items]]
name = 'loopback mac interface'

[[opdiag.test_items]]
name = 'loopback phy copper'

[[opdiag.test_items]]
name = 'loopback phy fiber'

[[opdiag.test_items]]
name = 'snake interface'

[[opdiag.test_items]]
name = 'PoE'

[[opdiag.test_items]]
name = 'asic0 reg'

[[opdiag.test_items]]
name = 'asic0 mem'
```

### Step 4: Create `opdiag` Script

File: `summit-stark/rootfs.overlay/alpha/bin/opdiag`

Based on summit-rz/summit-bcma55 pattern. The OpdiagHelper base class is reused as-is.

**OpdiagCustom — Board-Specific Test Logic for 4 Stark Boards:**

The Stark boards and their port layouts (from PFE TOMLs):

| Board | Copper Ports | Fiber/SFP Ports | Uplink | Has PoE | Has Gearbox |
|-------|-------------|-----------------|--------|---------|-------------|
| DIN-8W-4X (0x00) | fp1-fp8 (1GbE) | ip1-ip4 (SFP+ 10G) | u1-u2 | Yes | No |
| DIN-8T-8XE (0x01) | fp1-fp8 (10GbE) | ip01-ip08 (SFP28 25G) | u1-u2 | **No** | No |
| RM-24W-8XE (0x02) | fp1-fp24 (1GbE) | ip01-ip08 (SFP28 25G) | u1-u2 | Yes | No |
| RM-4MW-12W-4XE (0x03) | fp1-fp12 (2.5GbE) + fp13-fp16 (gearbox) | ip1-ip4 (SFP28 25G) | u1-u2 | Yes | **Yes** (BCM54994E) |

**Test implementations per item:**

**i2c_environment** — Follow summit-rz pattern (simple, board-agnostic checks):
- `sh "rtc --get"` → verify datetime pattern
- `sh "temp --get"` → verify all 6 TMP75 sensors report readings (all boards share same sensors)
- `sh "i2cget -y 1 0x64 0x05"` → verify LED controller accessible
- `sh "ctrlplane register --get BOARD_ID"` → verify board ID matches expected

**internal_flash** — Copy from summit-rz as-is (board-independent)

**memory** — Copy from summit-rz as-is (board-independent)

**loopback_mac_interface** — Use `all` wildcard (board-independent, like summit-rz):
```python
self.send_command('config interface loopback all mac', self.cli_prompt)
command = f'diag loopback test intf all time {10 if normal else 60}'
```

**loopback_phy_copper** — Branch by `self.product_name`:
```python
if self.product_name == '4630R-8W-4X-DN':        # 8 copper + 4 SFP
    config interface loopback @ip,@u phy
    diag loopback test intf @fp time <n>
elif self.product_name == '4630R-8T-8XE-DN':      # 8 copper(10G) + 8 SFP28
    config interface loopback @ip,@u phy
    diag loopback test intf @fp time <n>
elif self.product_name == '4630R-24W-8XE-RM':     # 24 copper + 8 SFP28
    config interface loopback @ip,@u phy
    diag loopback test intf @fp time <n>
elif self.product_name == '4630R-4MW-12W-4XE-RM': # 12 copper + 4 gearbox + 4 SFP28
    config interface loopback @ip,@u phy
    config gearbox loopback 13-16 system
    config interface loopback 13-16 none
    diag loopback test intf @fp time <n>
```

**loopback_phy_fiber** — Board-independent (all boards use same `@ip,@u` wildcard):
```python
config interface loopback @ip,@u phy
diag loopback test intf @ip,@u time <n>
```

**snake_interface** — Use `all` wildcard (like summit-rz):
```python
command = f'diag snake_loopback test intf all duration {10 if normal else 60}'
```

**PoE** — Excluded entirely for DIN-8T-8XE at init time:
```python
# In OpdiagCustom.__init__(), after super().__init__():
if self.product_name == '4630R-8T-8XE-DN':
    del self.test_functions['PoE']
    del self.result_dic['PoE']
```
For boards with PoE (8W-4X, 24W-8XE, 4MW-12W-4XE), use board-agnostic validation (same as summit-rz).

**asic0_reg** — Board-independent (same pattern as summit-rz/summit-bcma55):
```python
# Disable SDK background tasks, re-init
bcmcmd "counter off; l2mode off; linkscan off; memscan off; config add parity_enable=0"
bcmcmd "init; init misc; init mmu"
# Run register tests
bcmcmd "tc 3; tr 3; tl 3"
bcmcmd "tc 30; tr 30; tl 30"
bcmcmd "tc 31; tr 31; tl 31"
```

**asic0_mem** — Uses stark-specific ASIC test script:
```python
command = 'bcmcmd "tc 50; rcload /alpha/bcm/asic/stark_wh3p_asic_test.script; tl 50"'
```

**dut_init** — Uses `show gearbox interface status` (confirmed from stark-diag XML)

### Step 5: Copy Generic Utilities

| File | Source | Notes |
|------|--------|-------|
| `alpha/bin/diagpart` | summit-bcma55 or summit-rz | Identical across projects |
| `alpha/bin/pldwdtd` | summit-bcma55 or summit-rz | Identical across projects |

### Step 6: Create `99-opdiag.sh`

File: `summit-stark/rootfs.overlay/etc/profile.d/99-opdiag.sh`

Adapt from summit-bcma55's version (NOT summit-rz, since Stark uses same BCM/ttyS0 platform):
- Console: `/dev/ttyS0` at 115200 baud
- Reboot method: Use same `do_reboot` pattern as summit-bcma55
- Comment: "For summit-stark, the console is /dev/ttyS0,115200"

### Step 7: Create `S15pldwdt` Init Script

File: `summit-stark/rootfs.overlay/etc/init.d/S15pldwdt`

Simple script to start pldwdtd in background (copy pattern from summit-rz/summit-bcma55).

### Step 8: Remove Manufacturing-Only Init Scripts

Delete from `summit-stark/rootfs.overlay/etc/init.d/`:
- `S91diagenv`
- `S99diagps`
- `S80mount`

### Step 9: Modify `rootfs.overlay/init`

Replace the mfg init with the opdiag version containing `prep_opdiag()`. See section 1.8 for details.

### Step 10: Modify Quickstart Scripts

Add VLAN deletion and MAC loopback to all quickstart scripts. See section 1.9 for details.

### Step 11: Fix `prompt.sh`

Fix `nounset` safety in `rootfs.overlay/etc/profile.d/prompt.sh`:
- Add `export KLISH=${KLISH:-}` default
- Change `[ ! -z $KLISH ]` to `[ -n "$KLISH" ]`

### Step 12: Clean Up Python Packages

- Edit `rootfs.overlay/alpha/whl/requirements.txt` — keep only `diagpy`, `pyserial`, `pexpect`
- Remove mfg-only `.whl` files (pytest, rpyc, plumbum, etc.) See section 1.10.

### Step 13: Modify Kernel Defconfig

Edit `linux-*/arch/arm64/configs/alphadiags_defconfig`:
- Disable `CONFIG_MAGIC_SYSRQ`
- Disable `CONFIG_PRINTK_TIME` (mfg default is `y` — adds noisy timestamps)
- Change `CONFIG_CONSOLE_LOGLEVEL_DEFAULT` from `7` to `1`
- Change `CONFIG_CONSOLE_LOGLEVEL_QUIET` from `4` to `1`
- Requires `rm -rf build/linux` before rebuild

### Step 14: Modify Buildroot Defconfig

Edit `buildroot-fs/configs/*_rootfs_defconfig`:
- Remove `BR2_PACKAGE_GDB*`, `BR2_PACKAGE_STRACE`, `BR2_PACKAGE_STRESS_NG`, `BR2_PACKAGE_VALGRIND`

### Step 15: Update `env.mk`

```makefile
project_name := summit-stark
```

### Step 16: Verify ASIC Test Script Exists

Confirm `rootfs.overlay/alpha/bcm/asic/stark_wh3p_asic_test.script` is present (already in stark-diag).

---

## Critical Files Summary

| Action | File | Source/Reference |
|--------|------|-----------------|
| COPY base | `stark-diag/` -> `summit-stark/` | Full copy |
| CREATE | `alpha/bin/opdiag` | Adapt from summit-bcma55 + summit-rz patterns |
| CREATE | `alpha/toml/opdiag.toml` | New |
| COPY | `alpha/bin/diagpart` | From summit-bcma55 |
| COPY | `alpha/bin/pldwdtd` | From summit-bcma55 |
| CREATE | `etc/profile.d/99-opdiag.sh` | Adapt from summit-bcma55 (ttyS0) |
| CREATE | `etc/init.d/S15pldwdt` | New |
| MODIFY | `alpha/toml/board.toml` | Add opdiag_toml field |
| MODIFY | `diagnostics/diagpy/diagpy/board_init.py` | Add `opdiag_toml()` method to `Board_INFO` class |
| MODIFY | `rootfs.overlay/init` | Replace with opdiag version (prep_opdiag) |
| MODIFY | `alpha/script/quickstart_*` | Add VLAN delete + MAC loopback |
| MODIFY | `etc/profile.d/prompt.sh` | Fix nounset safety for KLISH variable |
| MODIFY | `alpha/whl/requirements.txt` | Remove pytest, pytest-loop, rpyc |
| MODIFY | `linux-*/arch/arm64/configs/*_defconfig` | Disable MAGIC_SYSRQ, add quiet log levels |
| MODIFY | `buildroot-fs/configs/*_defconfig` | Remove debug packages |
| MODIFY | `env.mk` | Update project_name |
| DELETE | `etc/init.d/S91diagenv` | Mfg-only |
| DELETE | `etc/init.d/S99diagps` | Mfg-only |
| DELETE | `etc/init.d/S80mount` | Replaced by diagpart |
| DELETE | `alpha/whl/*.whl` (mfg-only) | Remove pytest, rpyc, plumbum, etc. wheel files |

Note: `rc.soc` is NOT needed — the build process handles it.

---

## Build & Test Notes

### Rebuilding diagpy After Source Changes

The Makefile only builds the diagpy wheel if the `build/diagpy` directory does not exist. After modifying `board_init.py` (or any diagpy source), force a rebuild:

```bash
cd ~/project/opdiag/summit-stark
rm -rf build/diagpy
bash docker.sh make all -j16
```

Without `rm -rf build/diagpy`, the old wheel is repackaged and the fix does not take effect.

### Rebuilding Kernel After Defconfig Changes

Similarly, kernel defconfig changes (e.g., log levels, MAGIC_SYSRQ) require cleaning the kernel build:

```bash
cd ~/project/opdiag/summit-stark
rm -rf build/linux
bash docker.sh make all -j16
```

### Testing via Netboot

To test without flashing, TFTP-boot the image into U-Boot:

**Required bootargs:**
```
setenv bootargs console=ttyS0,115200 opdiag_mode=normal
```

- `opdiag_mode=normal` or `opdiag_mode=extended` is **required** — without it, opdiag exits immediately with "diagnostics mode is invalid".
- Add `opdiag_debug_for_internal_use` to bootargs to see full console output during boot (otherwise `prep_opdiag()` silences stdout/stderr in normal mode).

**Debug bootargs (recommended for development):**
```
setenv bootargs console=ttyS0,115200 opdiag_mode=normal opdiag_debug_for_internal_use
```

---

## Verification

1. **Structure check**: Confirm no mfg-only init scripts remain; all opdiag files present
2. **opdiag.toml**: `cli_prompt` regex matches all 4 board names
3. **board.toml**: Each board has `opdiag_toml` field
4. **opdiag script**: All test functions handle all 4 board variants
5. **PoE exclusion**: DIN-8T-8XE (4630R-8T-8XE-DN) removes PoE from test_functions/result_dic at init
6. **Gearbox**: RM-4MW-12W-4XE loopback_phy_copper properly configures gearbox loopback
7. **ASIC test**: `stark_wh3p_asic_test.script` path correct in asic0_mem
8. **init**: `prep_opdiag()` present, mdev hotplug removed, alphach moved to 99-opdiag.sh
9. **Quickstart scripts**: All have `config vlan member delete 1 all` and `config interface loopback all mac`
10. **prompt.sh**: Uses `KLISH=${KLISH:-}` and quoted `[ -n "$KLISH" ]`
11. **requirements.txt**: Only `diagpy`, `pyserial`, `pexpect` remain
12. **Wheel files**: Only `pexpect`, `ptyprocess`, `pyserial`, `smbus2`, `toml` remain
13. **Kernel defconfig**: `MAGIC_SYSRQ` disabled, `PRINTK_TIME` disabled, `CONSOLE_LOGLEVEL_DEFAULT=1`, `CONSOLE_LOGLEVEL_QUIET=1`
14. **Buildroot defconfig**: No GDB, strace, stress-ng, valgrind

---

## Resolved Questions

1. **Product names** (from EEPROM):
   - DIN-8W-4X (board-0) → `4630R-8W-4X-DN`
   - DIN-8T-8XE (board-1) → `4630R-8T-8XE-DN`
   - RM-24W-8XE (board-2) → `4630R-24W-8XE-RM`
   - RM-4MW-12W-4XE (board-3) → `4630R-4MW-12W-4XE-RM`

2. **PoE on DIN-8T-8XE**: Exclude PoE from the test list entirely. Use a conditional approach — remove PoE from `test_functions` and `result_dic` at init time when product is `4630R-8T-8XE-DN`.

3. **rc.soc**: Not needed in rootfs.overlay — it was a mistake in summit-bcma55. The build process copies it to the correct location. Skip it.
