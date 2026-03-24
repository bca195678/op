# opdiag-with-fjord-type2: Per-Family Architecture Design

**Date:** 2026-03-24
**Branch:** `opdiag-with-fjord-type2` (from `opdiag`)
**Build server:** `chester@172.31.230.36`, working dir: `~/project/opdiag/stark-diag`

---

## Background

The `opdiag` branch supports 4 Stark SKUs. The `opdiag-with-fjord-type1` branch added Fjord (5320-16P-2MXT-2X) support by inserting `if self.product_name == '5320-16P-2XT-2X'` branches throughout the monolithic codebase — 7 patches touching `opdiag`, `board.toml`, `opdiag.toml`, plus new hardware config files.

**Problem with type1:** Every family's code lives in the same files. A change for one family risks breaking another. As more families are added (3rd, 4th, ...), the branching becomes unmaintainable and testing coverage explodes.

**Type2 goal:** Full per-family isolation. Separate diagpy wheels, separate diagk plugins, separate opdiag scripts. Changes to one family never touch another family's code. A single built image contains all families; boot-time detection selects the correct set.

---

## System Components Overview

The diagnostic system has three main components:

| Component | Language | What it is | Size |
|-----------|----------|------------|------|
| **diagk** | C | Klish CLI plugin (`clish_plugin_mfg.so`) — 7 modules: common, board, cli, diag, pfe, gearbox, system. Statically links the Memory SDK (~1.7GB of `.a` archives). | ~110MB .so |
| **diagpy** | Python | Diagnostics wheel package — board init, TOML-driven config, installed at boot via init script. | ~few KB wheel |
| **opdiag** | Python | Operational diagnostics script — `OpdiagHelper` base class + `OpdiagCustom` with test methods (loopback, snake, ASIC, PoE, etc.). | ~1000 lines |

### Current Boot Sequence (type1)

1. `S01pywhl` — pip installs all wheels from `/alpha/whl/`
2. `S10boardid` — reads board ID from I2C (bus 0, addr 0x38, reg 0x00), writes to `/tmp/board_id`
3. User runs `cli` — Klish loads `clish_plugin_mfg.so` from `xml/startup.xml`
4. User runs `opdiag` — Python script with runtime branching per product name

### Current Board Inventory

| Board ID | Product Name | Family | Gearbox | PoE |
|----------|-------------|--------|---------|-----|
| 0x00 | 4630R-8W-4X-DN | Stark | No | Yes |
| 0x01 | 4630R-8T-8XE-DN | Stark | No | No |
| 0x02 | 4630R-24W-8XE-RM | Stark | No | Yes |
| 0x03 | 4630R-4MW-12W-4XE-RM | Stark | Yes (fp13-16) | Yes |
| 0x0C | 5320-16P-2MXT-2X | Fjord | Yes (u17-18) | Yes |

---

## Design Decisions

Four key architectural decisions were evaluated. Each section lists the options considered, trade-offs, and the chosen approach with reasoning.

### Decision 1: diagk / SDK Linkage Strategy

**Question:** The Broadcom SDK is ~1.7GB of static `.a` archives that get linked into the diagk plugin. Stark and Fjord diagk have 42 differing source files (board, pfe, gearbox, cli, diag modules all have family-specific code). How should we handle the SDK linkage?

#### Option A: Shared Single .so (rejected)

Build one `clish_plugin_mfg.so` that contains both families' code with runtime branching.

| Pros | Cons |
|------|------|
| Single ~110MB plugin, no size increase | All family code in one binary — a change to Fjord diag recompiles Stark |
| Simple build system (one target) | Runtime branches in C code (same problem as type1 but in C) |
| | Link errors from symbol conflicts between families |

#### Option B: Per-Family .so with Static SDK Duplication (chosen)

Each family gets its own plugin: `clish_plugin_mfg_stark.so` (~110MB) and `clish_plugin_mfg_fjord.so` (~110MB). Both statically link the same SDK independently.

| Pros | Cons |
|------|------|
| Complete isolation — Fjord changes never recompile Stark | ~110MB extra image size per additional family |
| No symbol conflicts | SDK built once, but linked twice (adds ~2 min to build) |
| Clean per-family source trees (`diagk-stark/`, `diagk-fjord/`) | |
| Adding a 3rd family = add `diagk-alpine/`, no existing code touched | |

#### Option C: Shared SDK .so + Thin Family .so (not explored — too complex)

Factor SDK into a shared `libsdk.so`, each family links only its own code. Requires SDK to be built as position-independent code (PIC), adds runtime dependency management, and the SDK was not designed for shared linking.

**Choice: Option B** — Accept the ~110MB duplication per family. Image size is not a constraint (NOR flash has room), and complete build/source isolation is the primary goal. The SDK is built once and linked into each family independently.

---

### Decision 2: diagpy Wheel Packaging

**Question:** diagpy is a Python wheel installed at boot. It reads TOML configs and provides board initialization. How should it be split across families?

#### Option A: Single Wheel with Runtime Branching (rejected)

Keep one `diagpy` package. Family-specific behavior is handled by TOML configs already (board.toml, pfe.toml, etc.).

| Pros | Cons |
|------|------|
| Minimal change from current state | A change to Fjord's board_init.py could break Stark |
| Single wheel to manage | Testing requires verifying all families on every change |
| | Same monolithic problem as type1, just at Python level |

#### Option B: Fully Independent Packages (chosen)

Two separate wheel source trees: `diagnostics/diagpy-stark/` and `diagnostics/diagpy-fjord/`. Both produce wheels with the same `diagpy` import namespace (`packages=['diagpy']` in setup.py). Only one is installed per boot — the init script selects based on detected family.

| Pros | Cons |
|------|------|
| Complete isolation — Fjord diagpy changes never affect Stark | Two copies of common utility code (board_init.py base, etc.) |
| Independent test coverage per family | Must keep common utilities in sync manually |
| Risk management: a Fjord-only release can't regress Stark | Slightly more build targets |

#### Option C: Shared Base + Family Extension Packages (not chosen)

A `diagpy-common` wheel with shared code, plus `diagpy-stark` and `diagpy-fjord` with family-specific overrides. More elegant but adds dependency management complexity and import path issues.

**Choice: Option B** — Fully independent packages. The user's stated goal is risk and coverage management: "if I try to make some changes to one series, it won't affect the others." Full independence achieves this directly. The `diagpy` namespace stays the same, so no code changes needed in consumers — only one wheel is installed at boot.

---

### Decision 3: Board-to-Family Identification

**Question:** At boot time, the system knows the `board_id` (read from I2C EEPROM). How should it determine which family the board belongs to?

#### Option A: Explicit Lookup Table (considered)

A config file or shell case statement mapping each board_id to its family:
```sh
case "$BOARD_ID" in
  0x00|0x01|0x02|0x03) echo "stark" ;;
  0x0C) echo "fjord" ;;
esac
```

| Pros | Cons |
|------|------|
| Explicit — no ambiguity | Must update the script for every new board |
| Easy to read | Adding a new Fjord SKU (e.g. 0x0D) requires a code change |

#### Option B: Board ID Range Convention (chosen)

Reserve contiguous board_id ranges per family:
- `0x00–0x0B` = Stark (12 slots)
- `0x0C–0x1F` = Fjord (20 slots)
- `0x20–0x2F` = (future family, 16 slots)

```sh
if [ "$BOARD_ID_DEC" -ge 0 ] && [ "$BOARD_ID_DEC" -le 11 ]; then echo "stark"
elif [ "$BOARD_ID_DEC" -ge 12 ] && [ "$BOARD_ID_DEC" -le 31 ]; then echo "fjord"
fi
```

| Pros | Cons |
|------|------|
| Adding a new Fjord SKU (board_id 0x0D) requires zero code changes | Must pre-allocate ranges (but board_id is 8-bit = 256 slots, plenty) |
| Self-documenting: board_id implies family | If a family exceeds its range, must reassign (unlikely) |
| `family_detect` script is tiny and stable | |

#### Option C: TOML-Driven (from board.toml)

Add a `family = "stark"` field to each `[board-N]` entry in board.toml. Read it at boot.

| Pros | Cons |
|------|------|
| Single source of truth (board.toml) | Requires TOML parser in init script (shell-only environment pre-Python) |
| Most flexible | board.toml is read after Python is installed; chicken-and-egg with S01pywhl |

**Choice: Option B** — Board ID range convention. It's the simplest approach that works at the earliest boot stage (shell-only, no TOML parser needed), and adding new SKUs within a family requires zero script changes.

---

### Decision 4: opdiag Script Strategy

**Question:** The `opdiag` Python script has per-board branches throughout (loopback tests, snake test, ASIC test, etc.). How should it be split?

#### Option A: Single Script with Family Dispatch (rejected)

Keep one `opdiag` file, but refactor to call family-specific methods:
```python
if self.family == 'stark':
    self._snake_test_stark()
elif self.family == 'fjord':
    self._snake_test_fjord()
```

| Pros | Cons |
|------|------|
| Single file to maintain | Still branching in the same file |
| Shared base class | Fjord test changes require touching the Stark file |
| | Growing file size as families are added |

#### Option B: Per-Family Scripts with Thin Dispatcher (chosen)

Three files:
- `opdiag` — reads `/tmp/board_family`, execs `opdiag-<family>`
- `opdiag-stark` — Stark-only (current opdiag with Fjord branches removed, snake gearbox fix included)
- `opdiag-fjord` — Fjord-only (extracted from type1 Fjord branches, standalone)

Each family script has its own `OpdiagCustom` class with only its own test methods.

| Pros | Cons |
|------|------|
| Complete file-level isolation | Some code duplication (OpdiagHelper base class in each) |
| Editing Fjord opdiag never opens the Stark file | Two files to update if OpdiagHelper base changes |
| Clear ownership: one file per family | |
| Dispatcher is 3 lines of shell | |

#### Option C: Plugin Architecture (not chosen)

A base `opdiag` that dynamically imports family-specific test modules. More Pythonic but adds import machinery complexity and makes the test flow harder to follow.

**Choice: Option B** — Per-family scripts with thin dispatcher. Matches the full-isolation philosophy. The dispatcher is trivial:
```sh
#!/bin/sh
FAMILY=$(cat /tmp/board_family)
exec /alpha/bin/opdiag-$FAMILY "$@"
```

---

## Chosen Architecture Summary

| Component | Approach | Image Contents |
|-----------|----------|----------------|
| diagk | Per-family .so, static SDK in each | `clish_plugin_mfg_stark.so` + `clish_plugin_mfg_fjord.so` |
| diagpy | Independent wheels, same namespace | `whl/stark/diagpy-*.whl` + `whl/fjord/diagpy-*.whl` |
| opdiag | Per-family scripts + dispatcher | `opdiag` → `opdiag-stark` or `opdiag-fjord` |
| CLI | Per-family Klish XML + dispatcher | `cli` → `cli-stark` or `cli-fjord` |
| Family detect | Board ID range → family name | `family_detect` shell script |
| Boot order | Board ID first, then family-aware wheel install | `S01boardid` → `S02pywhl` |

---

## Target Repository Structure

```
diagnostics/
  diagk-stark/          # Stark diagk source (full copy, Stark LED code only)
  diagk-fjord/          # Fjord diagk source (from summit-bcma55, Fjord LED code)
  diagpy-stark/         # Stark diagpy wheel source
  diagpy-fjord/         # Fjord diagpy wheel source
  (diagk/ and diagpy/ removed)

rootfs.overlay/
  alpha/bin/
    family_detect       # NEW: board_id range -> family name
    cli                 # Modified: dispatcher -> cli-stark or cli-fjord
    cli-stark           # run_klish.sh for Stark (xml-stark/)
    cli-fjord           # run_klish.sh for Fjord (xml-fjord/)
    opdiag              # Modified: dispatcher -> opdiag-stark or opdiag-fjord
    opdiag-stark        # Stark-only opdiag (no Fjord branches)
    opdiag-fjord        # Fjord-only opdiag (no Stark branches)
  alpha/lib/module/
    clish_plugin_mfg_stark.so   # Stark diagk plugin (~110MB)
    clish_plugin_mfg_fjord.so   # Fjord diagk plugin (~110MB)
  alpha/xml-stark/      # Stark Klish XML (startup.xml -> plugin_mfg_stark.so)
  alpha/xml-fjord/      # Fjord Klish XML (startup.xml -> plugin_mfg_fjord.so)
  alpha/whl/
    stark/diagpy-*.whl  # Stark diagpy wheel
    fjord/diagpy-*.whl  # Fjord diagpy wheel
    (common wheels: pyserial, pexpect, toml, smbus2, etc.)
  alpha/toml/
    board.toml          # Unified - all boards, all families
    opdiag-stark.toml   # Stark cli_prompt regex
    opdiag-fjord.toml   # Fjord cli_prompt regex
  etc/init.d/
    S01boardid          # Renamed from S10 - runs BEFORE wheel install
    S02pywhl            # Renamed from S01 - family-aware wheel install
```

---

## Boot Sequence (type2)

```
Power On
  |
  v
S01boardid
  |- board_id_get --export -> /tmp/board_id   (e.g. "0x00")
  |- family_detect -> /tmp/board_family        (e.g. "stark")
  |
  v
S02pywhl
  |- reads /tmp/board_family
  |- pip install whl/<family>/diagpy-*.whl     (family-specific)
  |- pip install whl/*.whl                     (common: pyserial, pexpect, toml, smbus2)
  |
  v
Shell ready (alphadiags:/#)
  |
  v
User runs "cli"
  |- reads /tmp/board_family
  |- exec cli-<family>
  |- Klish loads xml-<family>/startup.xml
  |- Plugin: clish_plugin_mfg_<family>.so
  |
  v
User runs "opdiag" (from Klish CLI or shell)
  |- reads /tmp/board_family
  |- exec opdiag-<family>
  |- Family-specific tests only
```

---

## Implementation Steps

### Step 0: Create Branch
```
git checkout opdiag && git checkout -b opdiag-with-fjord-type2
```

### Step 1: Split diagpy
- `cp -r diagnostics/diagpy diagnostics/diagpy-stark`
- `cp -r diagnostics/diagpy diagnostics/diagpy-fjord`
- `rm -rf diagnostics/diagpy`
- Both keep `packages=['diagpy']` in setup.py (same import namespace, only one installed per boot)

### Step 2: Split diagk
- `cp -r diagnostics/diagk diagnostics/diagk-stark`
- For `diagk-fjord`: copy from `summit-bcma55/diagnostics/diagk/` (42 files differ: board, pfe, gearbox, cli, diag modules all have Fjord-specific code)
- LED code: `diagk-stark/pfe/ledcode/` keeps only Stark `*_led.c` files; `diagk-fjord/pfe/ledcode/` has only `16p-2mxt-2x_led.c`
- `rm -rf diagnostics/diagk`

### Step 3: Update Build System

**env.mk** — add per-family directory variables:
```makefile
export diag_stark_dir = $(project_dir)/diagnostics/diagk-stark
export diag_fjord_dir = $(project_dir)/diagnostics/diagk-fjord
export diagpy_stark_dir = $(project_dir)/diagnostics/diagpy-stark
export diagpy_fjord_dir = $(project_dir)/diagnostics/diagpy-fjord
```

**Makefile** — replace single targets with per-family:
```makefile
all: diagk-stark diagk-fjord diagpy-stark diagpy-fjord oom zlflasher
    $(MAKE) -C $(project_dir) image
```
- `diagk-stark` builds to `build/diag-stark/`, installs as `clish_plugin_mfg_stark.so`
- `diagk-fjord` builds to `build/diag-fjord/`, installs as `clish_plugin_mfg_fjord.so`
- `diagpy-stark` builds wheel to `build/diagpy-stark/`, copies to `whl/stark/`
- `diagpy-fjord` builds wheel to `build/diagpy-fjord/`, copies to `whl/fjord/`
- Both diagk targets share the same `sdk` prerequisite (built once)

### Step 4: Add Family Detection
New file `rootfs.overlay/alpha/bin/family_detect`:
```sh
#!/bin/sh
BOARD_ID=$(cat /tmp/board_id 2>/dev/null)
BOARD_ID_DEC=$((BOARD_ID))
if [ "$BOARD_ID_DEC" -ge 0 ] && [ "$BOARD_ID_DEC" -le 11 ]; then echo "stark"
elif [ "$BOARD_ID_DEC" -ge 12 ] && [ "$BOARD_ID_DEC" -le 31 ]; then echo "fjord"
else echo "unknown"; exit 1; fi
```

### Step 5: Update Boot Scripts
- Rename `S10boardid` -> `S01boardid` (add `family_detect` call, write `/tmp/board_family`)
- Rename `S01pywhl` -> `S02pywhl` (read `/tmp/board_family`, install from `whl/<family>/` first)

### Step 6: Per-Family CLI and XML
- `cli` becomes thin dispatcher: `exec /alpha/bin/cli-$(cat /tmp/board_family)`
- `cli-stark`: `clish -x /alpha/xml-stark`
- `cli-fjord`: `clish -x /alpha/xml-fjord`
- `xml-stark/startup.xml`: `<PLUGIN name="mfg" file="clish_plugin_mfg_stark.so"/>`
- `xml-fjord/startup.xml`: `<PLUGIN name="mfg" file="clish_plugin_mfg_fjord.so"/>`

### Step 7: Per-Family opdiag
- `opdiag` becomes thin dispatcher: `exec /alpha/bin/opdiag-$(cat /tmp/board_family)`
- `opdiag-stark`: current opdiag with Fjord branches removed, snake gearbox fix included
- `opdiag-fjord`: Fjord-only opdiag (from type1 Fjord branches, standalone)
- `opdiag-stark.toml` / `opdiag-fjord.toml` with family-specific `cli_prompt`

### Step 8: Fjord Hardware Configs
Copy from `summit-bcma55` (same as type1):
- `alpha/bcm/16p-2mxt-2x.bcm`, `alpha/bcm/asic/fjord_asic_*.script`
- `alpha/toml/pfe-16p-2mxt-2x.toml`, `gearbox-`, `i2c-`, `xcvr-`, `poe-`
- `alpha/script/quickstart_16p-2mxt-2x`
- Add `[board-12]` entry to `board.toml` (with `opdiag_toml = opdiag-fjord.toml`)

### Step 9: Build and Test
- Full clean build: `bash docker.sh make clean all -j16`
- Verify image contains both plugins, both wheels, all dispatchers
- Netboot on Stark DUT (DIN-8W-4X): confirm `board_family=stark`, correct wheel, correct plugin, 9/10 PASS

---

## Critical Files to Modify

| File | Change |
|------|--------|
| `Makefile` | Per-family build targets, install paths |
| `env.mk` | Per-family directory variables |
| `rootfs.overlay/etc/init.d/S10boardid` | Rename to S01, add family_detect |
| `rootfs.overlay/etc/init.d/S01pywhl` | Rename to S02, family-aware pip install |
| `rootfs.overlay/alpha/bin/cli` (run_klish.sh) | Split into dispatcher + per-family |
| `rootfs.overlay/alpha/bin/opdiag` | Split into dispatcher + per-family |
| `diagnostics/diagk/cli/xml/startup.xml` | Per-family copies with renamed .so |
| `rootfs.overlay/alpha/toml/board.toml` | Add board-12, update opdiag_toml paths |

## New Files

| File | Purpose |
|------|---------|
| `rootfs.overlay/alpha/bin/family_detect` | Board ID range -> family name |
| `rootfs.overlay/alpha/bin/cli-stark` | Stark Klish launcher |
| `rootfs.overlay/alpha/bin/cli-fjord` | Fjord Klish launcher |
| `rootfs.overlay/alpha/bin/opdiag-stark` | Stark-only opdiag |
| `rootfs.overlay/alpha/bin/opdiag-fjord` | Fjord-only opdiag |
| `rootfs.overlay/alpha/toml/opdiag-stark.toml` | Stark cli_prompt |
| `rootfs.overlay/alpha/toml/opdiag-fjord.toml` | Fjord cli_prompt |

---

## Extensibility

Adding a 3rd family (e.g. "alpine", board_id 0x20-0x2F):

1. Add range to `family_detect`
2. Create `diagnostics/diagk-alpine/` and `diagnostics/diagpy-alpine/`
3. Add `diagk-alpine` / `diagpy-alpine` Makefile targets
4. Add `cli-alpine`, `xml-alpine/`, `opdiag-alpine`, `opdiag-alpine.toml`
5. Add `whl/alpine/` with built wheel
6. Add board entries to `board.toml`

**No existing family code is touched.**

---

## Type1 vs Type2 Comparison

| Aspect | Type1 (branch-based) | Type2 (per-family) |
|--------|---------------------|-------------------|
| Code isolation | None — all families in same files | Complete — separate source trees |
| Risk of regression | High — Fjord change can break Stark | None — families never share code |
| Image size | ~110MB (one plugin) | ~220MB (two plugins) |
| Build time | Single build | SDK once + 2 link passes (~2 min extra) |
| Adding a new family | Patch every file with new branches | Add new directories + Makefile targets |
| Testing scope | Must test all families on every change | Only test the changed family |
| Complexity | Low initial, grows with families | Higher initial, stays flat |
