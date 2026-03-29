# type2 → type2-bsdiff: Change Summary

## Overview

The `opdiag-with-fjord-type2-bsdiff` branch reduces the final firmware image from **59.8MB → ~45.5MB**
by storing only one plugin in the image (`clish_plugin_mfg_stark.so`) plus a small binary delta
patch, and reconstructing the Fjord plugin at boot time on Fjord boards.

---

## 1. `Makefile` — Add host bsdiff build rule and `apply_bsdiff` target

**What changed:**
- Added `host_bsdiff` variable pointing to `$(build_dir)/host/bsdiff`.
- Added a Make rule that compiles `bsdiff.c` from `buildroot-fs/package/bsdiff/` into
  `$(build_dir)/host/bsdiff` using the Docker-available gcc and `libbz2.so.1`. Runs
  automatically as part of every `make all` (single C file, sub-second).
- Added `apply_bsdiff` target that depends on `$(host_bsdiff)` and computes the binary
  delta between `stark.so` and `fjord.so` in the staging rootfs, writes
  `stark_to_fjord.patch`, then deletes `fjord.so`.
- The CPIO creation target now depends on `apply_bsdiff`.

**Why:**
Both plugins are ~107MB each (~215MB total) but share >99% of the Broadcom SDK binary
content. `bsdiff` exploits this similarity to produce a patch of only ~5.8MB. Storing
`stark.so + patch` instead of both `.so` files saves ~100MB of uncompressed rootfs,
which translates to ~14MB savings in the final LZMA-compressed image.

---

## 2. `rootfs.overlay/etc/init.d/S01boardid` — Runtime plugin reconstruction

**What changed:**
- Added logic in the `start)` case to handle the bsdiff patch at boot time:
  - If `stark_to_fjord.patch` is present and the board family is **Fjord**: run
    `bspatch stark.so fjord.so patch`, then delete `stark.so` and the patch file so only
    `fjord.so` remains.
  - If the board family is **Stark** (or anything else): simply delete the patch file so only
    `stark.so` remains.

**Why:**
The image ships with only `clish_plugin_mfg_stark.so` and the patch. The correct plugin for the
running hardware must be present before the CLI starts. `S01boardid` is the earliest init script
(runs before the CLI), so it is the right place to perform this one-time reconstruction.
After the script runs, the filesystem contains exactly one plugin binary matching the board family.

---

## 3. `buildroot-fs/Config.in` — Register bsdiff package

**What changed:**
- Added `source "$BR2_EXTERNAL_ALPHADIAGS_PATH/package/bsdiff/Config.in"`.

---

## 4. `buildroot-fs/configs/stark_rootfs_defconfig` — Enable bsdiff package

**What changed:**
- Added `BR2_PACKAGE_BSDIFF=y`.

**Why (sections 3 & 4):**
The `buildroot-fs/package/bsdiff/` package cross-compiles `bspatch` for AArch64 and installs
it to `/alpha/bin/bspatch` inside `rootfs.tar.gz` via `make gen-rootfs`. This replaces the
previously manually cross-compiled binary that was committed to `rootfs.overlay/alpha/bin/bspatch`.

---

## New Package (Untracked — requires `git add`)

| File | Description |
|------|-------------|
| `buildroot-fs/package/bsdiff/Config.in` | Buildroot menuconfig entry |
| `buildroot-fs/package/bsdiff/bsdiff.mk` | Build rules: cross-compiles `bspatch` for target |
| `buildroot-fs/package/bsdiff/bsdiff-4.3.tar.gz` | Source tarball (bsdiff.c + bspatch.c + bzlib.h) |
| `buildroot-fs/package/bsdiff/bsdiff.c` | Source used directly by Makefile host build rule |
| `buildroot-fs/package/bsdiff/bzlib.h` | bzip2 header for host compilation (libbz2-dev not in Docker) |

---

## Image Size Summary

| Variant | Image Size |
|---------|-----------|
| type2 (both plugins) | 59.8 MB |
| type2-bsdiff (stark + patch) | **~45.5 MB** |
| type1 reference | ~43 MB |
