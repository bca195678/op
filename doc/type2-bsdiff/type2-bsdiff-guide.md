# type2 → type2-bsdiff: Implementation Guide

## Background

The `opdiag-with-fjord-type2` branch stores **both** board-family plugins inside the firmware
image:

| File | Size (uncompressed) |
|------|---------------------|
| `clish_plugin_mfg_stark.so` | ~107 MB |
| `clish_plugin_mfg_fjord.so` | ~106 MB |

The two plugins share over 99% of their binary content (Broadcom SDK code). Only the
board-specific hardware register tables differ. Because of this near-identical content, a binary
diff (`bsdiff`) between them produces a patch of only ~5.8 MB.

The `opdiag-with-fjord-type2-bsdiff` branch exploits this by shipping only `stark.so` plus the
patch. At boot, the init script `S01boardid` reconstructs `fjord.so` on Fjord boards using
`bspatch`, or simply deletes the patch on Stark boards.

**Result:** image size drops from **59.8 MB → ~45.5 MB**.

---

## Overview of Changes

| # | File | What | When |
|---|------|------|------|
| 1 | `Makefile` | Host bsdiff build rule + `apply_bsdiff` target | Every `make all` |
| 2 | `rootfs.overlay/etc/init.d/S01boardid` | Reconstruct `fjord.so` from patch at boot | Runtime |
| 3 | `buildroot-fs/Config.in` | Register bsdiff package | `make gen-rootfs` |
| 4 | `buildroot-fs/configs/stark_rootfs_defconfig` | Enable bsdiff package | `make gen-rootfs` |
| 5 | `buildroot-fs/package/bsdiff/` | New package: builds `bspatch` for AArch64 target | `make gen-rootfs` |

---

## How the Two Tools Are Provided

| Tool | Role | How provided |
|------|------|-------------|
| `bsdiff` | Computes delta at build time (host) | Compiled from source by Makefile on every `make all` |
| `bspatch` | Applies patch at boot time (target) | Cross-compiled by buildroot, installed into `rootfs.tar.gz` via `make gen-rootfs` |

### Why two different mechanisms?

`make all` does not invoke buildroot — it unpacks the pre-built `rootfs.tar.gz` and overlays
platform-specific components. So:

- **`bspatch`** goes into `rootfs.tar.gz` via buildroot (`make gen-rootfs`) — built once,
  committed, available on all machines.
- **`bsdiff`** is compiled inline during `make all` from `buildroot-fs/package/bsdiff/bsdiff.c`.
  A single C file takes under a second. No manual setup required on any machine.

---

## Part 1: The bsdiff Buildroot Package

The package lives at `buildroot-fs/package/bsdiff/`:

```
buildroot-fs/package/bsdiff/
├── Config.in           — menuconfig entry
├── bsdiff.mk           — build rules (cross-compiles bspatch for AArch64)
├── bsdiff-4.3.tar.gz   — source tarball (bsdiff.c + bspatch.c + bzlib.h)
├── bsdiff.c            — also kept directly for Makefile host compilation
└── bzlib.h             — bzip2 header (libbz2-dev not installed in Docker image)
```

**`bsdiff.mk`** uses `generic-package`. It cross-compiles only `bspatch.c` for the target and
installs it to `/alpha/bin/bspatch`:

```makefile
define BSDIFF_BUILD_CMDS
    $(TARGET_CC) $(TARGET_CFLAGS) -I$(@D) -o $(@D)/bspatch $(@D)/bspatch.c -lbz2
endef

define BSDIFF_INSTALL_TARGET_CMDS
    $(INSTALL) -D -m 755 $(@D)/bspatch $(TARGET_DIR)/alpha/bin/bspatch
endef

$(eval $(generic-package))
```

### Obtaining the Source Files

The package directory contains three source files (`bsdiff.c`, `bspatch.c`, `bzlib.h`) and a
tarball (`bsdiff-4.3.tar.gz`) that buildroot uses as `BSDIFF_SOURCE`. Assemble them as follows
on the build server (or any Linux host with internet access):

```bash
cd /tmp

# 1. bsdiff 4.3 — Colin Percival, BSD-2-Clause
wget https://distfiles.freebsd.org/distfiles/bsdiff-4.3.tar.gz
tar xzf bsdiff-4.3.tar.gz
cp bsdiff-4.3/bsdiff.c bsdiff-4.3/bspatch.c .

# 2. bzlib.h — Docker image has libbz2.so.1 runtime but NOT libbz2-dev headers
wget https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz
tar xzf bzip2-1.0.8.tar.gz
cp bzip2-1.0.8/bzlib.h .

# 3. Repackage into the custom tarball buildroot expects
tar czf bsdiff-4.3.tar.gz bsdiff.c bspatch.c bzlib.h

# 4. Copy everything into the package directory
cp bsdiff.c bspatch.c bzlib.h bsdiff-4.3.tar.gz \
   ~/project/opdiag/stark-diag/buildroot-fs/package/bsdiff/
```

> `bspatch.c` is only needed inside the tarball (buildroot extracts it to cross-compile for
> AArch64). `bsdiff.c` and `bzlib.h` are also kept directly in the package directory for the
> Makefile host compilation rule (which does not unpack the tarball).

To activate the package, run `make gen-rootfs` and commit the new `rootfs.tar.gz`.

---

## Part 2: Makefile — Host bsdiff + apply_bsdiff

Two additions to the top-level `Makefile`:

```makefile
host_bsdiff := $(build_dir)/host/bsdiff

$(host_bsdiff): $(buildroot_external_dir)/package/bsdiff/bsdiff.c
	@mkdir -p $(dir $@)
	gcc -O2 -I$(buildroot_external_dir)/package/bsdiff \
		-o $@ $< \
		-L/usr/lib/x86_64-linux-gnu -l:libbz2.so.1

apply_bsdiff: $(host_bsdiff)
	@echo ":: Creating bsdiff patch stark->fjord"
	@if [ -f $(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_fjord.so ]; then \
		$(host_bsdiff) \
			$(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_stark.so \
			$(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_fjord.so \
			$(rootfs-temp_dir)/alpha/lib/module/stark_to_fjord.patch; \
		rm $(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_fjord.so; \
		echo "Fjord patch created"; \
	fi
```

- `$(host_bsdiff)` is a real file target — Make only recompiles if `bsdiff.c` is newer.
- `gcc` and `libbz2.so.1` are both available inside the Docker build container.
- `bzlib.h` is provided in the package directory (Docker has runtime libbz2 but not the
  dev headers).

---

## Part 3: Boot-time Reconstruction — `S01boardid`

`S01boardid` is the earliest init script. It reconstructs the correct plugin before the CLI starts:

```sh
PLUGIN_DIR="/alpha/lib/module"
PATCH="${PLUGIN_DIR}/stark_to_fjord.patch"
STARK="${PLUGIN_DIR}/clish_plugin_mfg_stark.so"
FJORD="${PLUGIN_DIR}/clish_plugin_mfg_fjord.so"
if [ -f "${PATCH}" ]; then
    if [ "$FAMILY" = "fjord" ]; then
        echo "Reconstructing fjord plugin from patch..."
        /alpha/bin/bspatch "${STARK}" "${FJORD}" "${PATCH}"
        rm "${STARK}" "${PATCH}"
        echo "Fjord plugin ready"
    else
        rm "${PATCH}"
    fi
fi
```

- **Fjord board**: `bspatch` reconstructs `fjord.so`, then `stark.so` and the patch are deleted.
- **Stark board**: patch is deleted. Only `stark.so` remains.

---

## Part 4: Build

### First time (or after `make clean-rootfs`)

Run buildroot to cross-compile `bspatch` into `rootfs.tar.gz`:

```bash
make gen-rootfs
```

Then commit the updated `rootfs.tar.gz`.

### Every build

```bash
bash docker.sh make all -j32
```

The build sequence:
1. `rootfs.tar.gz` is unpacked (contains `bspatch` at `/alpha/bin/bspatch`)
2. `$(host_bsdiff)` is compiled from `bsdiff.c` (sub-second)
3. Both plugins are compiled and stripped
4. `apply_bsdiff` runs: generates `stark_to_fjord.patch`, deletes `fjord.so`
5. CPIO is packed and LZMA-compressed

---

## Part 5: Verify

After the build, check the image size:

```bash
ls -lh ~/project/opdiag/stark-diag/image/
# Expected: ~45.5 MB  (vs 59.8 MB for type2)
```

Netboot to a Stark board:
```
setenv bootargs 'console=ttyS0,115200 opdiag_mode=normal'
```

Expected: full POST, 9/10 PASS, `alphadiags:/#` prompt.

---

## Files to Commit

| File | Action |
|------|--------|
| `Makefile` | `git add` (modified) |
| `rootfs.overlay/etc/init.d/S01boardid` | `git add` (modified) |
| `buildroot-fs/Config.in` | `git add` (modified) |
| `buildroot-fs/configs/stark_rootfs_defconfig` | `git add` (modified) |
| `buildroot-fs/package/bsdiff/` | `git add` (new directory — all 5 files) |
| `rootfs.tar.gz` | `git add` after running `make gen-rootfs` |
