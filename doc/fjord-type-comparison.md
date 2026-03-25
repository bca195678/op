# Fjord Integration: Type1 vs Type2 vs Type3

| | **Type1** | **Type2** | **Type3** |
|---|---|---|---|
| **Branch** | `opdiag-with-fjord-type1` | `opdiag-with-fjord-type2` | `opdiag-with-fjord-type3` |
| **Approach** | Monolithic — if/elif branches in shared codebase | Per-family isolation — separate source trees | Per-family isolation + shared SDK dynamic lib |
| **diagk** | Single `diagnostics/diagk/` with conditionals | `diagk-stark/` + `diagk-fjord/` (independent) | Same as type2 |
| **diagpy** | Single `diagnostics/diagpy/` with conditionals | `diagpy-stark/` + `diagpy-fjord/` (independent) | Same as type2 |
| **SDK linking** | Static, one plugin | Static per family (~110MB each) | Dynamic — `libsdk_bcm.so` shared (~110MB once) |
| **Plugin size** | ~110MB x 1 | ~110MB x 2 | ~300KB x 2 + 110MB shared lib |
| **Image size** | ~45MB | ~60MB | ~45MB |
| **Adding a family** | Add more if/elif branches everywhere | Add new directories, no existing code touched | Same as type2 |
| **Risk** | Fjord change can break Stark | Fully isolated — zero cross-family risk | Same isolation, but shared SDK is a single point |
| **Complexity** | Low (one codebase) | Medium (duplicated source trees) | Higher (dynamic linking, rpath, sdk_shared.mk) |
| **Boot-time selection** | Code branches on board ID at runtime | `family_detect` dispatchers pick per-family binaries | Same as type2 |

## Trade-off Summary

- **Type1** is simplest but doesn't scale — every family touches the same files.
- **Type2** gives full isolation at the cost of ~15MB larger image (SDK duplicated in two static plugins).
- **Type3** recovers the size by sharing the SDK as a `.so`, but adds dynamic linking complexity.
