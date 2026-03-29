# type2 → type2-bsdiff: Change Summary

## Overview

The `opdiag-with-fjord-type2-bsdiff` branch reduces the final firmware image from **59.8MB → 44MB**
by storing only one plugin in the image (`clish_plugin_mfg_stark.so`) plus a small binary delta
patch, and reconstructing the Fjord plugin at boot time on Fjord boards.

---

## 1. `Makefile` — Add `apply_bsdiff` target

**What changed:**
- Added a new `apply_bsdiff` Make target that runs `bsdiff` to compute the binary delta between
  `clish_plugin_mfg_stark.so` and `clish_plugin_mfg_fjord.so` in the staging rootfs.
- The resulting patch file (`stark_to_fjord.patch`) is kept; `clish_plugin_mfg_fjord.so` is deleted.
- The CPIO creation target now depends on `apply_bsdiff`, so the patch is generated automatically
  as part of every image build.

**Why:**
Both plugins are ~107MB each (~215MB total) but share >99% of the Broadcom SDK binary content.
`bsdiff` exploits this similarity to produce a patch of only ~5.7MB. Storing `stark.so + patch`
instead of both `.so` files saves ~100MB of uncompressed rootfs, which translates to ~16MB savings
in the final LZMA-compressed image.

---

## 2. `diagnostics/diagk-stark/image/Makefile` — Strip `.eh_frame` from stark plugin

**What changed:**
- Added a second `objcopy` step after `--strip-all` to explicitly remove `.eh_frame`,
  `.eh_frame_hdr`, and `.comment` sections from `clish_plugin_mfg_stark.so`.

**Why:**
`--strip-all` removes debug symbols but leaves `.eh_frame` (C++ exception unwind tables) intact.
On AArch64, these sections are not needed for normal CLI operation and add several MB to the binary.
Removing them reduces the uncompressed `.so` size and improves LZMA compression of the final image.

---

## 3. `diagnostics/diagk-fjord/image/Makefile` — Strip `.eh_frame` from Fjord plugin

**What changed:**
- Same additional `objcopy --remove-section` step as above, applied to `clish_plugin_mfg_fjord.so`.

**Why:**
The Fjord plugin is the source for the bsdiff patch generation. A smaller Fjord binary means a
smaller patch file (the delta is computed on the stripped binaries), further reducing image size.

---

## 4. `docker.sh` — lld bind-mounts (ICF experiment leftover)

**What changed:**
- Two `-v` bind-mounts were added to `DOCKER_ARGS`:
  - `/usr/bin/ld.lld` → toolchain `ld.lld`
  - `/lib/x86_64-linux-gnu/libLLVM-14.so.1` → toolchain lib path

**Why (context):**
These mounts were added during an earlier experiment to test ICF (Identical Code Folding) via
the `lld` linker as an alternative size reduction technique. ICF was ultimately ineffective because
the two plugins have different relocation encodings for their shared SDK code. The ICF flags were
removed from the build, but these bind-mounts remained.

**Note:** These lines are not required for the bsdiff approach and can be safely removed before
merging.

---

## 5. `rootfs.overlay/etc/init.d/S01boardid` — Runtime plugin reconstruction

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

## 6. `rootfs.overlay/init` — Fix `OPDDIAG_DEV` variable typo

**What changed:**
- Renamed `local OPDDIAG_DEV=` → `local OPDIAG_DEV=` (removed the extra `D`).
- Changed `local OPDIAG_DEV=1` inside the case statement → `OPDIAG_DEV=1` (removed `local`
  so the assignment propagates to the outer function scope).

**Why:**
The original code had two bugs that caused the `opdiag_debug_for_internal_use` kernel parameter
to be silently ignored:
1. The outer variable was named `OPDDIAG_DEV` (typo) while the inner check used `OPDIAG_DEV`,
   so they were always different variables.
2. The `local` keyword inside the `case` block created a new local variable scoped only to that
   block; the outer `if [ -n "${OPDIAG_DEV}" ]` test always saw an empty value.

The combined effect: the `else` branch (redirect all I/O to `/dev/null`, disable console) was
always taken regardless of the kernel command line. This made console debugging impossible.
The fix restores the intended behaviour so that passing `opdiag_debug_for_internal_use` in
`bootargs` correctly enables serial console output during boot.

---

## Files Not in Diff (Untracked)

| File | Description |
|------|-------------|
| `rootfs.overlay/alpha/bin/bspatch` | Cross-compiled AArch64 binary (15KB). Required at runtime on the DUT to apply the patch in S01boardid. Must be `git add`-ed before committing. |

---

## Image Size Summary

| Variant | Image Size |
|---------|-----------|
| type2 (both plugins) | 59.8 MB |
| type2-bsdiff (stark + patch) | **44 MB** |
| type1 reference | ~43 MB |
