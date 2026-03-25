# Makefile Analysis: diagk-stark vs diagk-fjord

## Summary

Both `diagk-stark` and `diagk-fjord` use identical Makefile structures. They are clones of each other with the same build system.

## Key Variables and Paths

### SDK Configuration Source
- **Location:** `/home/chester/project/opdiag/stark-diag/build/sdk/bcmsdk_flags.mk`
- **Auto-generated file** — do not modify manually
- Contains three main variables:
  - `bcmsdk_cflags` — compiler flags
  - `bcmsdk_ldflags` — linker flags (`-pthread -lm -lrt -ldl`)
  - `bcmsdk_libs` — list of prebuilt SDK library archives
  - `bcmsdk_objs` — SDK object files

### SDK Libraries (bcmsdk_libs)

The build system links with 150+ static library archives from the Broadcom SDK, including:
- Core SDK libraries (libbcm.a, libsal_core.a, libsoc.a, etc.)
- Chip-specific libraries (libcatana.a, libenduro.a, libfirebolt.a, etc.)
- Feature libraries (libdiag.a, libtest.a, libcint.a, libphymod.a, etc.)

**Location pattern:** `/home/chester/project/opdiag/stark-diag/build/sdk/unix-user/alphadiags/`

### SDK Objects (bcmsdk_objs)

Three object files are linked into the final shared library:
```
/home/chester/project/opdiag/stark-diag/build/sdk/unix-user/alphadiags/version.o
/home/chester/project/opdiag/stark-diag/build/sdk/unix-user/alphadiags/socdiag.o
/home/chester/project/opdiag/stark-diag/build/sdk/unix-user/alphadiags/platform_defines.o
```

## Build Process

### Module Compilation (module.mk)

**Location:** `diagnostics/diagk-{stark|fjord}/module.mk`

Defines:
- Compiler and linker toolchain (`$(CROSS_COMPILE)gcc`, etc.)
- Include paths (KLISH headers, SDK headers)
- Final compilation flags combining:
  - `-g -D_GNU_SOURCE -D_DEFAULT_SOURCE -O2 -Wall -fPIC -Werror`
  - KLISH include paths
  - SDK include paths (extensive)

### Linker Configuration

**Final LDFLAGS:**
```
$(LINKER_OPTION) $(KLISH_LDFLAGS) $(BCM_LDFLAGS)
```

**Final LIBS:**
```
$(APP_LIB) $(SDK_LIB_O) $(SDK_LIB_A) $(KLISH_LIB)
```

Where:
- `$(APP_LIB)` = `$(BUILD_ROOT)/app.a` (local application code)
- `$(SDK_LIB_O)` = `$(bcmsdk_objs)` (3 SDK objects)
- `$(SDK_LIB_A)` = `$(bcmsdk_libs)` (150+ SDK libraries)
- `$(KLISH_LIB)` = `-lclish -ltinyrl -llub -lkonf` (Klish CLI framework)

### Shared Library Creation (image/Makefile)

**Location:** `diagnostics/diagk-{stark|fjord}/image/Makefile`

**Output:** `clish_plugin_mfg.so` (shared library plugin)

**Linker command:**
```bash
$(CC) -shared $(LDFLAGS) -o $(O)/$(MODULE_NAME).dbg \
    -Wl,--gc-sections \
    -Wl,--allow-multiple-definition \
    -Wl,-start-group \
    -Wl,--whole-archive \
    $(LIBS) \
    -Wl,--no-whole-archive \
    -Wl,--end-group
```

**Key linker flags:**
- `-shared` — create shared library
- `--gc-sections` — garbage collect unused sections
- `--allow-multiple-definition` — permit duplicate symbols (important for SDK)
- `--whole-archive` — force inclusion of all symbols from listed libraries
- `--start-group` / `--end-group` — allow circular dependencies between archives

**Post-link processing:**
1. Generate symbol map with `nm`
2. Extract debug symbols with `objcopy --only-keep-debug`
3. Compress debug symbols with gzip
4. Strip binary with `objcopy --strip-all`

## Differences Between stark and fjord

**None observed.** The Makefiles and build process are identical. Differences would be in:
- Source code content (`diagnostics/diagk-stark/src/` vs `diagnostics/diagk-fjord/src/`)
- Feature compilation flags (defined in module.mk)
- Build output location only

## Dependencies

### Build-time Dependencies

1. **SDK pre-build:** All libraries in `bcmsdk_libs` must already exist
   - Path: `/home/chester/project/opdiag/stark-diag/build/sdk/unix-user/alphadiags/`
2. **Klish framework:** Must be pre-built and installed
   - Headers expected in `$(klish_header_dir)`
   - Libraries in `$(build_dir)/rootfs/usr/lib`
3. **Cross-compiler:** Must be available as `$(CROSS_COMPILE)gcc`

### Deployment Artifact

The final plugin: `diagnostics/diagk-stark/image/clish_plugin_mfg.so` (or fjord version)
- Used by the Klish CLI framework on the DUT
- Provides device-specific diagnostic commands

## Variable Resolution

The module.mk includes `$(sdk_flags)` which is typically set by a parent build system:
- Defined in a higher-level Makefile or build wrapper
- Points to `build/sdk/bcmsdk_flags.mk`
- If not found, build fails with error: `"Needs $$sdk_flags."`
