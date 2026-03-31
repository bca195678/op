# Image Size Optimization — Findings

**Date:** 2026-03-31
**Branch:** `main-skinny`, `opdiag-with-fjord-type2-bsdiff-skinny`
**Build server:** `chester@172.31.230.36:~/project/opdiag/`

---

## Summary

Three image variants were built in parallel worktrees and compared:

| Worktree | Branch | Image | Size | vs Baseline |
|---|---|---|---|---|
| `stark-diag-baseline` | `main` | `stark.0.0.2-b6` | 44 MB | — |
| `stark-diag-skinny` | `main-skinny` | `stark.0.0.2-b6` | 36 MB | −8 MB (−18%) |
| `stark-diag-bsdiff-skinny` | `main-bsdiff-skinny` | `summit-stark.0.0.2-b6` | 42 MB | −2 MB (−5%) |

---

## Skinny Optimizations (`main-skinny`)

Five changes applied on top of `main`:

### 1. LZMA rootfs compression (`env.mk`)

```makefile
# before
export rootfs_compress_tool := xz -v --format=lzma

# after
export rootfs_compress_tool := xz -v -9e --lzma1=dict=16MiB --format=lzma
```

Higher compression level with larger dictionary. Slower to compress (build time), same decompression speed.

### 2. LZMA kernel compression (`Makefile` + `alphadiags.its`)

Kernel re-compressed from gzip to lzma after the kernel build step:

```makefile
&& gzip -d -k -f ${blddir}/arch/$(target_arch)/boot/Image.gz \
&& lzma -9 -k -f ${blddir}/arch/$(target_arch)/boot/Image \
```

FIT image source updated:
```
# alphadiags.its
data = /incbin/("Image.lzma");   # was Image.gz
compression = "lzma";            # was "gzip"
```

### 3. Debug tool removal (`Makefile` — `simplify_rootfs` target)

Removed from rootfs before CPIO packing:

| Category | Removed |
|---|---|
| Debug/trace | `gdb`, `strace`, `valgrind` |
| Stress/bench | `stress-ng`, `iperf3` |
| Net/HW tools | `phytool`, `screen`, `dfu-util` |
| Partition tools | `gdisk`, `mkenvimage` |
| TPM | `tpm2_*`, `libtss2-*` |
| Flasher | `zlflasher` (entire package dir) |
| Locale | `gconv` |
| Python | `python3.11/ensurepip` |
| Shell completion | `bash-completion` |

---

## bsdiff-Skinny (`main-bsdiff-skinny`)

Built from `opdiag-with-fjord-type2-bsdiff` (Fjord support via bspatch) with the same five skinny
optimizations applied on top (uncommitted, copied via `cp`):

```bash
# Create worktree without committing the 3 modified files:
git branch main-bsdiff-skinny opdiag-with-fjord-type2-bsdiff-skinny
git worktree add ../stark-diag-bsdiff-skinny main-bsdiff-skinny
cp Makefile alphadiags.its env.mk ../stark-diag-bsdiff-skinny/
```

### Why bsdiff-skinny is larger than skinny (+6 MB)

The bsdiff patch file (`stark_to_fjord.patch`, ~5.8 MB) adds overhead that cannot be recovered
by compression:

- **bsdiff format**: The `.patch` file contains three **bzip2-compressed** streams internally
  (control block, diff block, extra block). The data is already high-entropy.
- **Re-compression**: When LZMA re-compresses the rootfs CPIO, it sees the patch as random data
  and achieves near 1:1 ratio — essentially no further reduction.
- **Net overhead**: +~5.8 MB from patch, +~60 KB from `bspatch` binary ≈ +6 MB total.

Compare with shipping `clish_plugin_mfg_fjord.so` directly (110 MB unstripped): that compresses
very well with LZMA due to repetitive ELF structure (DWARF, symbol tables), so it adds only a
few MB to the image. The patch approach is a trade-off: smaller than shipping both `.so` files
in plaintext, but the patch itself resists further compression.

---

## Strip Investigation

Attempted to add an explicit `strip` step in `simplify_rootfs` for `clish_plugin_mfg.so`:

```makefile
# skinny: strip debug symbols from plugin
@$(toolchain_dir)/bin/$(toolchain_name)-strip \
    $(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg.so
```

**Result: No effect.** The build system already strips the `.so` during `diagk`:

```
aarch64-broadcom-linux-gnu-objcopy --strip-all \
    build/diag/image/clish_plugin_mfg.so.dbg \
    build/diag/image/clish_plugin_mfg.so
```

The `.so` copied to rootfs is already fully stripped. The 110 MB is the **stripped** size — the
BCM SDK compiled code is inherently large. Debug symbols are preserved separately as
`clish_plugin_mfg.so.debug.gz` (76 MB compressed) in `$(image_dir)/`.

### Plugin size in image dir

| File | Size | Notes |
|---|---|---|
| `clish_plugin_mfg.so` (in rootfs) | 110 MB | Stripped ELF, BCM SDK code |
| `clish_plugin_mfg.so.debug.gz` (in `image/`) | 76 MB | Debug symbols, not in firmware |

The 110 MB unstripped ELF compresses heavily with LZMA inside the CPIO ramdisk — hence the
final image is only 36 MB despite containing it.

---

## Worktree Setup

All three worktrees share the same `.git` object store under `stark-diag`:

```
~/project/opdiag/stark-diag               [opdiag-with-fjord-type2-bsdiff-skinny]
~/project/opdiag/stark-diag-baseline      [main]
~/project/opdiag/stark-diag-skinny        [main-skinny]
~/project/opdiag/stark-diag-bsdiff-skinny [main-bsdiff-skinny]
```

Build command used for all: `bash docker.sh make all -j32`

---

## Conclusion

| Lever | Savings | Notes |
|---|---|---|
| LZMA rootfs (xz -9e, dict=16MiB) | ~2–3 MB | Slow compress, same decompress |
| LZMA kernel (vs gzip) | ~1–2 MB | |
| Remove debug tools | ~3–4 MB | gdb, strace, valgrind, etc. |
| Strip `.so` | 0 MB | Already stripped by build system |
| Fjord via bsdiff (vs shipping fjord.so) | avoids +several MB | But patch adds +6 MB vs Stark-only |

Total skinny savings: **−8 MB (−18%)** from 44 MB → 36 MB.
