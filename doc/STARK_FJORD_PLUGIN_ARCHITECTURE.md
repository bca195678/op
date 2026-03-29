# STARK/Fjord Plugin Architecture - Current Implementation (Type2 with BSDiff)

## Branch
- Current branch: `opdiag-with-fjord-type2-bsdiff`
- Latest commit: `08fcb14ba` - "Add per-family architecture for Fjord support (type2)"

## Current S01boardid Script
**Location:** `rootfs.overlay/etc/init.d/S01boardid`

The script performs the following at boot:

1. **Waits for I2C bus** - Attempts `board_id_get --export` up to 10 times (2s intervals)
2. **Detects board family** - Runs `/alpha/bin/family_detect` and stores result in `/tmp/board_family`
3. **Reconstructs family-specific plugin** (on start action):
   - Checks if patch file exists: `${PLUGIN_DIR}/stark_to_fjord.patch`
   - **For Fjord boards:** Uses `bspatch` to reconstruct the Fjord plugin from the Stark plugin + patch
     ```
     bspatch "${STARK}" "${FJORD}" "${PATCH}"
     ```
   - **For non-Fjord boards:** Just removes the patch file
   - Directory: `/alpha/lib/module/`
   - Stark plugin (base): `clish_plugin_mfg_stark.so`
   - Fjord plugin (reconstructed): `clish_plugin_mfg_fjord.so`
   - Patch file: `stark_to_fjord.patch` (deleted after use or if not needed)

## Klish/diagk Plugin Loading

### Startup Configuration Files
- **Stark:** `diagnostics/diagk-stark/cli/xml/startup.xml`
- **Fjord:** `diagnostics/diagk-fjord/cli/xml/startup.xml`

Both contain:
```xml
<PLUGIN name="mfg" file="clish_plugin_mfg_stark.so"/>  <!-- Stark -->
<PLUGIN name="mfg" file="clish_plugin_mfg_fjord.so"/>  <!-- Fjord -->
```

The plugin is loaded by Klish when CLI starts (invoked by running `cli` command on the device).

### Plugin Entry Points
- **Source files:**
  - `diagnostics/diagk-stark/cli/include/cli_init.h`
  - `diagnostics/diagk-stark/cli/src/cli_init.c`
  - `diagnostics/diagk-fjord/cli/include/cli_init.h`
  - `diagnostics/diagk-fjord/cli/src/cli_init.c`

- **Function:** Entry point function called when Klish loads `clish_plugin_mfg.so`

## Init Sequence

### Boot Scripts
**Order** (from `/etc/init.d/rcS`):
1. `S00haveged` - Entropy daemon
2. `S01boardid` - Board detection & plugin reconstruction (THIS ONE)
3. `S02pywhl` - Python wheels
4. `S15pldwdt` - Platform watchdog
5. `S50lo` - Loopback interface
6. `S90banner` - Banner message

All scripts in `/etc/init.d/` are executed numerically in order by `rcS`.

### BusyBox Init Configuration
**File:** `rootfs.overlay/etc/inittab`
- Default boot action: `::sysinit:/etc/init.d/rcS`
- Main shell: `::respawn:/bin/cttyhack /bin/bash -l`

## Build-Time Plugin Generation

### Makefile
**Target:** `apply_bsdiff` (called during firmware build)

```makefile
apply_bsdiff:
	@echo ":: Creating bsdiff patch stark->fjord"
	@if [ -f $(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_fjord.so ]; then \
		$(HOME)/bin/bsdiff \
			$(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_stark.so \
			$(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_fjord.so \
			$(rootfs-temp_dir)/alpha/lib/module/stark_to_fjord.patch; \
		rm $(rootfs-temp_dir)/alpha/lib/module/clish_plugin_mfg_fjord.so; \
		echo "Fjord patch created"; \
	fi
```

**Process:**
1. During build, both `clish_plugin_mfg_stark.so` and `clish_plugin_mfg_fjord.so` are built
2. `bsdiff` creates a delta patch file: `stark_to_fjord.patch`
3. Fjord .so is deleted from rootfs (kept only in build artifacts)
4. Final rootfs includes:
   - `clish_plugin_mfg_stark.so` (full, ~107 MB)
   - `stark_to_fjord.patch` (delta, small)

### Build Artifacts
Located in: `build/rootfs/alpha/lib/module/`
- `clish_plugin_mfg_stark.so` (~107 MB) - Final rootfs copy
- Linux kernel modules (bcm-knet, ptp-clock, kernel-bde, user-bde)

**Build directory copies** (for reference):
- `build/diag-stark/image/clish_plugin_mfg.so` (~107 MB)
- `build/diag-fjord/image/clish_plugin_mfg.so` (~106 MB)
- Debug symbols: `.so.debug.gz` (~76 MB each)
- Link maps: `.so.map` (~12 MB each)

## Binary Tools
- **bspatch:** Standalone aarch64 binary at project root (`./bspatch_aarch64`)
- **bsdiff:** Home binary used during build (`$(HOME)/bin/bsdiff`)

## File Layout Summary

### Firmware Image
```
rootfs.overlay/
├── etc/
│   ├── init.d/
│   │   ├── rcS                 (Main init script)
│   │   ├── S01boardid          (Board detection + plugin reconstruction)
│   │   ├── S02pywhl
│   │   └── ...
│   └── inittab                 (BusyBox init config)
└── alpha/lib/module/           (Created at runtime)
    ├── clish_plugin_mfg_stark.so
    └── stark_to_fjord.patch    (Generated at build time)

diagnostics/
├── diagk-stark/
│   └── cli/xml/startup.xml     (References clish_plugin_mfg_stark.so)
└── diagk-fjord/
    └── cli/xml/startup.xml     (References clish_plugin_mfg_fjord.so)
```

### Build Output
```
build/
├── rootfs/
│   └── alpha/lib/module/
│       ├── clish_plugin_mfg_stark.so  (installed to image)
│       └── stark_to_fjord.patch        (installed to image)
├── diag-stark/image/
│   └── clish_plugin_mfg.so
└── diag-fjord/image/
    └── clish_plugin_mfg.so
```

## Runtime Plugin Resolution

1. **Device boots** → `inittab` triggers `rcS`
2. **S01boardid runs** → Detects board family (Stark or Fjord)
3. **If Fjord detected:**
   - `bspatch` reconstructs `clish_plugin_mfg_fjord.so` from base + patch
   - Deletes patch file and base Stark .so
4. **If Stark detected:**
   - Just removes patch file (leaves Stark .so)
5. **CLI runs** → Klish loads the family-specific `clish_plugin_mfg_*.so`

## Key Design Points

- **Space optimization:** Only Stark plugin is shipped in firmware; Fjord is reconstructed at runtime
- **Single patch:** One small delta patch file `stark_to_fjord.patch` replaces full Fjord plugin in rootfs
- **Transparent to CLI:** Klish always loads the correct plugin for the detected board
- **Early detection:** Board ID detection happens before any Klish CLI startup (S01 runs before other services)
- **Idempotent:** S01boardid can run multiple times without harm (checks for file existence)

