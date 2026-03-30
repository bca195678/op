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

**Result:** image size drops from **59.8 MB → ~51 MB** (measured; estimate had been ~45.5 MB).

---

## Overview of Changes

| # | File | What | When |
|---|------|------|------|
| 1 | `Makefile` | Host bsdiff + target bspatch build rules + `apply_bsdiff` target | Every `make all` |
| 2 | `rootfs.overlay/etc/init.d/S01boardid` | Reconstruct `fjord.so` from patch at boot | Runtime |
| 3 | `buildroot-fs/package/bsdiff/` | Source files for both tools (3 files, no buildroot package) | `make all` |

---

## How the Two Tools Are Provided

| Tool | Role | How provided |
|------|------|-------------|
| `bsdiff` | Computes delta at build time (host x86-64) | Compiled from source by Makefile on every `make all` |
| `bspatch` | Applies patch at boot time (target AArch64) | Cross-compiled from source by Makefile on every `make all` |

Both tools are single C files. Compilation takes under a second each. No manual setup,
no `make gen-rootfs`, no binary artifacts committed to `rootfs.tar.gz`.

---

## Part 1: Source Files — `buildroot-fs/package/bsdiff/`

The package directory holds three source files used directly by the Makefile:

```
buildroot-fs/package/bsdiff/
├── bsdiff.c    — compiled by Makefile for host (x86-64 bsdiff)
├── bspatch.c   — cross-compiled by Makefile for target (AArch64 bspatch)
└── bzlib.h     — bzip2 header (libbz2-dev not installed in Docker image)
```

No buildroot `Config.in` or `bsdiff.mk` — the Makefile handles both tools directly.

### Obtaining the Source Files

Run these commands on the build server. Use `apt-get source` (reliable on the build server's
Debian environment); the FreeBSD mirror URLs are a fallback if the package source is unavailable.

```bash
cd /tmp

# 1. bsdiff 4.3 — via apt source (preferred on build server)
apt-get source bsdiff
cp bsdiff-*/bsdiff.c bsdiff-*/bspatch.c .

# Alternative if apt source is unavailable:
# wget https://distfiles.freebsd.org/distfiles/bsdiff-4.3.tar.gz
# tar xzf bsdiff-4.3.tar.gz && cp bsdiff-4.3/bsdiff.c bsdiff-4.3/bspatch.c .

# 2. bzlib.h — Docker has libbz2.so.1 runtime but NOT libbz2-dev headers
#    Use dpkg to extract the header from the installed package source:
apt-get source libbz2-dev 2>/dev/null || true
dpkg -x $(apt-get download --print-uris libbz2-dev 2>/dev/null | awk '{print $1}' | tr -d "'") /tmp/bz2-extract 2>/dev/null \
  || apt-get download libbz2-dev && dpkg -x libbz2-dev_*.deb /tmp/bz2-extract
find /tmp/bz2-extract -name bzlib.h | xargs -I{} cp {} .

# Alternative if the above is awkward:
# wget https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz
# tar xzf bzip2-1.0.8.tar.gz && cp bzip2-1.0.8/bzlib.h .

# 3. Copy into the package directory
cp bsdiff.c bspatch.c bzlib.h \
   ~/project/opdiag/stark-diag/buildroot-fs/package/bsdiff/
```

---

## Part 2: Makefile — Host bsdiff + Target bspatch + `apply_bsdiff`

Four changes to the top-level `Makefile`:

**Change 1:** Add `apply_bsdiff` as a prerequisite of the CPIO target (line ~65):

```makefile
$(cpio_file)$(rootfs_ext): simplify_rootfs release_info apply_bsdiff
```

**Changes 2–4:** Add the new variables and targets after the `release_info` block (line ~82):

```makefile
host_bsdiff   := $(build_dir)/host/bsdiff
target_bspatch := $(build_dir)/target/bspatch

$(host_bsdiff): $(buildroot_external_dir)/package/bsdiff/bsdiff.c
	@mkdir -p $(dir $@)
	gcc -O2 -I$(buildroot_external_dir)/package/bsdiff \
		-o $@ $< \
		-L/usr/lib/x86_64-linux-gnu -l:libbz2.so.1

$(target_bspatch): $(buildroot_external_dir)/package/bsdiff/bspatch.c
	@mkdir -p $(dir $@)
	$(CROSS_COMPILE)gcc -O2 -I$(buildroot_external_dir)/package/bsdiff \
		-o $@ $< \
		-L$(build_dir)/rootfs/usr/lib -l:libbz2.so.1

apply_bsdiff: $(host_bsdiff) $(target_bspatch)
	install -D -m 755 $(target_bspatch) $(rootfs-temp_dir)/alpha/bin/bspatch
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

> **Note:** `$(CROSS_COMPILE)` is set to `aarch64-broadcom-linux-gnu-` by `env.mk` and
> exported into the build environment. The toolchain lives at
> `/opt/project/broadcom/XLDK_6.3.2/toolchain-a55-glibc/bin`.

- Both `$(host_bsdiff)` and `$(target_bspatch)` are real file targets — Make only recompiles
  if the corresponding `.c` source is newer.
- `gcc` and `libbz2.so.1` are available inside the Docker build container (x86-64).
- The AArch64 toolchain has its own `libbz2.so.1` under `$(build_dir)/rootfs/usr/lib` — the
  target cross-compile must link against this, not the host system's `-lbz2`.
- `bzlib.h` is provided in the package directory (Docker has runtime libbz2 but not dev headers).
- The CPIO target must depend on `apply_bsdiff` — without this dependency `apply_bsdiff` never
  runs during `make all` and `fjord.so` remains in the image (image stays at 60 MB).
- `apply_bsdiff` installs `bspatch` to `/alpha/bin/bspatch` in the staging rootfs before
  the CPIO is packed.

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

### Every build

```bash
bash docker.sh make all -j32
```

The build sequence:
1. `rootfs.tar.gz` is unpacked
2. `$(host_bsdiff)` is compiled from `bsdiff.c` (sub-second)
3. `$(target_bspatch)` is cross-compiled from `bspatch.c` (sub-second)
4. Both plugins are compiled and stripped
5. `apply_bsdiff` runs: installs `bspatch`, generates `stark_to_fjord.patch`, deletes `fjord.so`
6. CPIO is packed and LZMA-compressed

No `make gen-rootfs` step required. No `rootfs.tar.gz` update needed.

---

## Part 5: Verify

After the build, check the image size:

```bash
ls -lh ~/project/opdiag/stark-diag/image/
# Expected: ~51 MB  (vs ~60 MB for type2)
```

Netboot to a Stark board:
```
setenv bootargs 'console=ttyS0,115200 opdiag_mode=normal'
```

Expected: full POST, 9/10 PASS (internal flash FAIL is normal in netboot), then
"Diagnostics completed. Waiting for reboot..." followed by automatic reboot back to U-Boot.
The `alphadiags:/#` prompt is not persistent — the board reboots after POST completes.

---

## Files to Commit

| File | Action |
|------|--------|
| `Makefile` | `git add` (modified) |
| `rootfs.overlay/etc/init.d/S01boardid` | `git add` (modified) |
| `buildroot-fs/package/bsdiff/bsdiff.c` | `git add` (new file) |
| `buildroot-fs/package/bsdiff/bspatch.c` | `git add` (new file) |
| `buildroot-fs/package/bsdiff/bzlib.h` | `git add` (new file) |
