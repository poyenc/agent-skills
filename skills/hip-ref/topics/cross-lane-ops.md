# Cross-Lane Operations

## What it is

Cross-lane operations let lanes within a wavefront read each other's data without
LDS or global memory. AMD provides three mechanisms: DPP (zero-cost modifiers on
VALU instructions, within 16-lane rows), ds_permute/ds_bpermute (arbitrary
permutations across wave64), and ds_swizzle (bitwise index transforms). These map
to CUDA's `__shfl_*` family.

## When you care

- Implementing wavefront-level reductions (sum, max for softmax)
- Building prefix scans
- Butterfly patterns for FFT
- Any data sharing between threads without LDS round-trip

## Key numbers

| Operation           | Latency   | Pipeline | Range               |
|---------------------|-----------|----------|---------------------|
| DPP modifier        | 0 extra   | VALU     | Within 16-lane row  |
| DPP wave variant    | 0 extra   | VALU     | Cross-row (limited) |
| ds_permute          | ~20 cycles| LDS unit | Any lane in wave64  |
| ds_bpermute         | ~20 cycles| LDS unit | Any lane in wave64  |
| ds_swizzle          | ~20 cycles| LDS unit | Bitwise patterns    |
| v_readfirstlane_b32 | 1 cycle   | VALU     | Lane 0 → SGPR      |

DPP modifiers are "free" — they attach to VALU instructions with zero extra cost.
ds_permute uses LDS hardware but NOT LDS memory (counts toward lgkmcnt).

## How to use it

### DPP modifiers
```
Row structure (wave64): Row0=lanes 0-15, Row1=16-31, Row2=32-47, Row3=48-63

Intra-row (16 lanes):
  row_shr:N    — shift right by N within row
  row_shl:N    — shift left by N within row
  row_ror:N    — rotate right
  row_bcast:15 — broadcast lane 15 to all in row
  row_mirror   — reverse lane order
  quad_perm:[p0,p1,p2,p3] — permute within 4-lane quads

Cross-row (full wave):
  wave_shl:1   — shift left by 1 row (16 lanes)
  wave_shr:1   — shift right by 1 row
  wave_ror:1   — rotate right by 1 row
```

### Wave64 reduction (sum) — 6 steps
```cpp
float wave_sum(float val) {
    // Phase 1: intra-row DPP (4 steps, ~free)
    val += __shfl_down(val, 1);   // row_shr:1
    val += __shfl_down(val, 2);   // row_shr:2
    val += __shfl_down(val, 4);   // row_shr:4
    val += __shfl_down(val, 8);   // row_shr:8
    // Phase 2: cross-row ds_permute (2 steps, ~20 cycles each)
    val += __shfl_xor(val, 16);   // swap row pairs
    val += __shfl_xor(val, 32);   // swap half-waves
    return __shfl(val, 0);        // broadcast lane 0
}
```

### HIP intrinsics
```cpp
__shfl(val, src_lane)       // arbitrary lane read
__shfl_xor(val, mask)       // butterfly: lane i reads lane i^mask
__shfl_up(val, delta)       // lane i reads lane i-delta
__shfl_down(val, delta)     // lane i reads lane i+delta
__ballot(pred)              // 64-bit mask where pred is true
```

### AMDGCN builtins for precise control
```cpp
__builtin_amdgcn_ds_permute(src_lane * 4, val)   // gather
__builtin_amdgcn_ds_bpermute(dst_lane * 4, val)  // scatter
__builtin_amdgcn_ds_swizzle(val, pattern)         // bitwise
__builtin_amdgcn_mov_dpp(val, ctrl, mask, bound)  // DPP
```

## Pitfalls

1. **Wave64, not wave32**: Full reduction needs 6 steps (not 5). `__shfl_xor(val, 32)`
   crosses the 32-lane boundary.
2. **DPP cannot cross row boundaries**: row_shr/shl only work within 16 lanes.
   Use wave_shr/shl (1-row shift) or ds_permute for arbitrary cross-row.
3. **ds_permute address = byte offset**: Must be `lane_id * 4`, not `lane_id`.
4. **ds_permute occupies LDS pipeline**: Cannot overlap with LDS loads/stores.
5. **Inactive lanes contribute zero**: DPP on masked-off lanes gives wrong reductions.

## CDNA3 vs CDNA4 differences

No major changes expected. Both use wave64 with identical DPP and ds_permute
instruction sets. Check ISA ref for any new DPP modifier encodings on gfx950.

## Sources

- AMD GCN cross-lane ops: https://gpuopen.com/learn/amd-gcn-assembly-cross-lane-operations/
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Ch.6 (Data Share), Ch.4 (Vector ALU/DPP)
- HIP kernel language: https://rocm.docs.amd.com/projects/HIP/en/develop/reference/kernel_language.html
