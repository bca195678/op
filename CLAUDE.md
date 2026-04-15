# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python Executable

The bundled WinPython interpreter lives at `./wpy64/python/python.exe`. Set it as a shell variable at the start of any session that invokes Python:

```bash
PYTHON=./wpy64/python/python.exe
```

All skills reference `"$PYTHON"` — never redeclare `PYTHON` inside a skill. Pre-installed packages: `pyserial`, `pytest`, `psutil`, `requests`, `python-dotenv`, `opencv-python`, `tftpy`.

## Available Skills

This repo ships Claude Code skills invokable via slash commands:

| Skill | Command | Purpose |
|-------|---------|---------|
| UART | `/uart` | Serial console interaction with embedded devices |
| Deploy | `/deploy` | Transfer and execute files on embedded devices via HTTP+wget |
| Power | `/power` | Control Aviosys IP Power 9258W2 outlets (on/off/toggle/cycle/status) |
| Fabrick | `/fabrick` | SSH to the remote source/build server (172.31.230.36) for any task: git operations, builds (docker.sh + make), scripts, file management |
| Netboot | `/netboot` | TFTP-boot a firmware image from Host into STARK via U-Boot (device must be at u-boot> prompt) |
| Ledcam | `/ledcam` | USB camera LED color detection for STARK front panel — calibrate, live feed, ROI selection (with profiles), and detect (green/amber/off) |
| Standup | `/standup` | Set up WinPython environment — extract installer, install pip packages, verify (counterpart to /teardown) |
| Teardown | `/teardown` | Clean up session state — kill HTTP servers, optionally remove NAT and power off DUT |
| Devloop | `/devloop` | Iterative fix-build-netboot-verify cycle — edit source on build server, rebuild, netboot to DUT, check results, repeat until it works |

Detailed skill documentation is in `.claude/skills/<skill>/SKILL.md`.

## Host vs. DUT — Disambiguation Rule

Two machines are involved in this project:

| Nickname | What it is | How to run commands on it |
|----------|-----------|--------------------------|
| **Host** | Your Windows PC running Claude Code | Bash tool directly |
| **DUT** | STARK network switch (external device) | `/uart` skill via UART serial |

**When a command or task is ambiguous**, apply these rules in order:

1. If the user says "on the DUT", "on the device", "on the board", "on the STARK" → run via `/uart` skill on the DUT.
2. If the user says "locally", "on the host", "on my PC", "on Windows" → run via Bash on the Host.
3. If context makes it obvious (e.g. `ipconfig` = Host, `alphadiags` path = DUT) → use that.
4. If still ambiguous → **ask** before executing: "Did you mean to run this on the Host (PC) or the DUT (STARK)?"

## STARK Platform Defaults

Standard configuration for the STARK network switch platform:

- **Serial port:** COM200, 115200 baud
- **Linux shell prompt:** `alphadiags:/#`
- **U-Boot prompt:** `u-boot>`
- **Login required:** No (engineering sample)
- **Build server:** `chester@172.31.230.36` — project at `~/project/opdiag/summit-stark/` (same repo as `stark-diag/`, different local clone)
- **Enter CLI from Linux shell:** `cli` (starts diagk Klish CLI)
- **If device is at U-Boot:** type `boot` to boot into Linux

## DIN-8T-8XE PCIe Boot

Board `4630R-8T-8XE-DN` (board ID 0x01) has a BCM56071 ASIC on PCIe. It **must** boot with the `pci` FIT configuration:

```
bootm 0x70000000#pci
```

The default `stark` config uses `stark.dtb` (PCIe disabled). The `pci` config uses `stark-dual-mac.dtb` (PCIe enabled). Without `#pci`, BCM56071 is invisible — PTP, loopback on unit 1 ports, and snake tests all fail or skip.

Other boards (DIN-8W-4X, RM-24W-8XE, RM-4MW-12W-4XE) use the default: `bootm 0x70000000`.

## BCM Script Types

BCM SDK uses two script formats with **different interpreters**:

| Extension | Command | Syntax |
|-----------|---------|--------|
| `.soc` | `bcmcmd "rcload /path/file.soc"` | BCM shell commands (`mcsload`, `config`, etc.) |
| `.cint` | `bcmcmd "cint /path/file.cint"` | C interpreter (variables, functions, `printf`) |

**Never use `rcload` on `.cint` files** — it causes `Unknown command` errors because C function calls aren't valid BCM shell commands.

## Temporary Files

All host-side logs, downloaded images, spec checkouts, and other transient files go in **`./tmp/`**:

| Content | Path pattern |
|---------|-------------|
| Firmware images (build output, netboot) | `./tmp/<image>` |
| UART / serial session logs | `./tmp/uart-session.log` |
| Netboot log | `./tmp/netboot.log` |
| Deploy log | `./tmp/deploy.log` |
| Batch command scripts | `./tmp/cmds.txt` |

`./tmp/` is gitignored. Always `mkdir -p ./tmp` before writing to it.

## Git Policy

Always ask for explicit permission before running `git commit` or `git push`. Never bundle them into the end of an implementation step — completing a task does not imply approval to commit or push.

All commits (both local and on the remote build server) must use this author:

```
Chester Cheng <chester_cheng@alphanetworks.com>
```

Pass it explicitly on every commit: `git commit --author='Chester Cheng <chester_cheng@alphanetworks.com>' ...`

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
