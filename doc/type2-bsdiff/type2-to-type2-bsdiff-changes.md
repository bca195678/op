# type2 → type2-bsdiff: Change Summary

## Overview

The `opdiag-with-fjord-type2-bsdiff` branch reduces the final firmware image from **59.8MB → ~45.5MB**
by storing only one plugin in the image (`clish_plugin_mfg_stark.so`) plus a small binary delta
patch, and reconstructing the Fjord plugin at boot time on Fjord boards.

---

## 1. `Makefile` — Add host bsdiff, target bspatch, and `apply_bsdiff` target

**What changed:**
- Added `host_bsdiff` variable pointing to `$(build_dir)/host/bsdiff`.
- Added `target_bspatch` variable pointing to `$(build_dir)/target/bspatch`.
- Added a Make rule that compiles `bsdiff.c` from `buildroot-fs/package/bsdiff/` into
  `$(build_dir)/host/bsdiff` using the Docker-available gcc and `libbz2.so.1`. Runs
  automatically as part of every `make all` (single C file, sub-second).
- Added a Make rule that cross-compiles `bspatch.c` for AArch64 into
  `$(build_dir)/target/bspatch` using `$(CROSS_COMPILE)gcc` (`aarch64-broadcom-linux-gnu-gcc`)
  and `-lbz2`. Runs automatically as part of every `make all` (single C file, sub-second).
- Added `apply_bsdiff` target that depends on both `$(host_bsdiff)` and `$(target_bspatch)`:
  installs `bspatch` into `/alpha/bin/` in the staging rootfs, computes the binary delta
  between `stark.so` and `fjord.so`, writes `stark_to_fjord.patch`, then deletes `fjord.so`.
- The CPIO creation target depends on `apply_bsdiff`.

**Why:**
Both plugins are ~107MB each (~215MB total) but share >99% of the Broadcom SDK binary
content. `bsdiff` exploits this similarity to produce a patch of only ~5.8MB. Storing
`stark.so + patch` instead of both `.so` files saves ~100MB of uncompressed rootfs,
which translates to ~14MB savings in the final LZMA-compressed image.

Building `bspatch` inline in `make all` (instead of via buildroot's `make gen-rootfs`)
means no separate build step is needed and no binary artifact needs to be committed to
`rootfs.tar.gz`.

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

## New Files (Untracked — requires `git add`)

| File | Description |
|------|-------------|
| `buildroot-fs/package/bsdiff/bsdiff.c` | Source used by Makefile host build rule |
| `buildroot-fs/package/bsdiff/bspatch.c` | Source used by Makefile target cross-compile rule |
| `buildroot-fs/package/bsdiff/bzlib.h` | bzip2 header (libbz2-dev not in Docker) |

---

## Image Size Summary

| Variant | Image Size |
|---------|-----------|
| type2 (both plugins) | 59.8 MB |
| type2-bsdiff (stark + patch) | **~45.5 MB** |
| type1 reference | ~43 MB |
