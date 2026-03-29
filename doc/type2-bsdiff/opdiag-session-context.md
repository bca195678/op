# Opdiag type2-bsdiff: Session Context

## What This Is

This project develops an **operational diagnostics firmware image** for the STARK network switch
platform. The firmware is built in a separate repo (`stark-diag`) on a remote build server.

This document is a briefing for a fresh Claude Code session to pick up where a previous session
left off: implementing the `opdiag-with-fjord-type2-bsdiff` branch.

---

## Build Server

| Item | Value |
|------|-------|
| SSH | `chester@172.31.230.36` |
| Project directory | `~/project/opdiag/stark-diag/` |
| Build command | `bash docker.sh make all -j32` |
| Gen-rootfs command | `make gen-rootfs` (inside Docker, updates `rootfs.tar.gz`) |
| Image output | `~/project/opdiag/stark-diag/image/` |

Connect via the `/fabrick` skill or directly: `ssh chester@172.31.230.36`

---

## Branch Context

Two branches exist on the build server's **stark-diag** repo:

| Branch | Description | Status |
|--------|-------------|--------|
| `opdiag-with-fjord-type2` | Dual plugin image (stark.so + fjord.so both bundled) | **Committed, base branch** |
| `opdiag-with-fjord-type2-bsdiff` | Reduced image: stark.so + 5.8MB patch only | **Does NOT exist yet** — must be created |

### Goal

Create `opdiag-with-fjord-type2-bsdiff` by branching off `opdiag-with-fjord-type2` and applying
the changes documented in the three files below.

---

## The Three Reference Files (in `./doc/type2-bsdiff/`)

| File | Purpose |
|------|---------|
| `./doc/type2-bsdiff/type2-to-type2-bsdiff.diff` | Exact `git diff` of all changes vs type2 base |
| `./doc/type2-bsdiff/type2-to-type2-bsdiff-changes.md` | Human-readable change summary with rationale |
| `./doc/type2-bsdiff/type2-bsdiff-guide.md` | Full implementation guide including new package files |

These three files together fully describe what the new branch must contain.
**The diff covers changes to existing files. The guide covers new files that must be created.**

---

## What the Branch Does

The `type2` image ships both `clish_plugin_mfg_stark.so` (~107 MB) and
`clish_plugin_mfg_fjord.so` (~106 MB). They share >99% of their binary content.
A `bsdiff` between them is only ~5.8 MB.

`type2-bsdiff` ships only `stark.so + patch`:
- At boot on a **Fjord board**: `bspatch` reconstructs `fjord.so` from the patch
- At boot on a **Stark board**: the patch is simply deleted

**Result: image drops from 59.8 MB → ~45.5 MB**

---

## Changes Required (Summary)

### 1. New Source Directory: `buildroot-fs/package/bsdiff/`

Three source files to add (see `./doc/type2-bsdiff/type2-bsdiff-guide.md` Part 1):

```
buildroot-fs/package/bsdiff/
├── bsdiff.c    — compiled by Makefile for host (x86-64 bsdiff)
├── bspatch.c   — cross-compiled by Makefile for target (AArch64 bspatch)
└── bzlib.h     — bzip2 header (libbz2-dev not in Docker)
```

No buildroot `Config.in` or `bsdiff.mk` — the Makefile handles both tools directly.

#### Obtaining the source files

Run these commands **on the build server** (or any Linux host with internet access):

```bash
cd /tmp

# 1. Download bsdiff 4.3 source (BSD-2-Clause, Colin Percival)
wget https://distfiles.freebsd.org/distfiles/bsdiff-4.3.tar.gz
tar xzf bsdiff-4.3.tar.gz
cp bsdiff-4.3/bsdiff.c bsdiff-4.3/bspatch.c .

# 2. Get bzlib.h from bzip2 source (Docker has libbz2 runtime but not dev headers)
wget https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz
tar xzf bzip2-1.0.8.tar.gz
cp bzip2-1.0.8/bzlib.h .

cp bsdiff.c bspatch.c bzlib.h \
   ~/project/opdiag/stark-diag/buildroot-fs/package/bsdiff/
```

### 2. Modify Existing Files (apply the diff)

The diff at `./doc/type2-bsdiff/type2-to-type2-bsdiff.diff` covers:
- `Makefile` — add `host_bsdiff` + `target_bspatch` compile rules and `apply_bsdiff` target
- `rootfs.overlay/etc/init.d/S01boardid` — boot-time plugin reconstruction logic

---

## Build Workflow After Implementing

### Every build

```bash
bash docker.sh make all -j32
```

This compiles `bsdiff` (host x86-64) and `bspatch` (target AArch64) inline from source,
installs `bspatch` into the staging rootfs, generates the patch, and packs the image.
No `make gen-rootfs` step required.

Expected image size: ~45.5 MB (in `~/project/opdiag/stark-diag/image/`)

---

## Git Policy

- **Author on all commits:** `Chester Cheng <chester_cheng@alphanetworks.com>`
  ```bash
  git commit --author='Chester Cheng <chester_cheng@alphanetworks.com>' ...
  ```
- **Always ask for explicit permission before `git commit` or `git push`.**

---

## Test / Netboot

Use the `/netboot` skill. The DUT is a STARK board at U-Boot prompt (`u-boot>`).

For opdiag images, bootargs must include `opdiag_mode=normal`:
```
setenv bootargs 'console=ttyS0,115200 opdiag_mode=normal'
```

Expected result: full POST, 9/10 PASS (internal flash FAIL is expected in netboot mode),
`alphadiags:/#` prompt.

To see serial output, add `opdiag_debug_for_internal_use` to bootargs.

---

## Key Platform Notes

- **Serial port:** COM200, 115200 baud
- **Linux shell prompt:** `alphadiags:/#`
- **U-Boot prompt:** `u-boot>`
- **Board families:** `stark` and `fjord` — detected by `S01boardid` via `$FAMILY`
- **Plugin path on device:** `/alpha/lib/module/clish_plugin_mfg_<family>.so`
- **bspatch installed to:** `/alpha/bin/bspatch` (by buildroot package)
