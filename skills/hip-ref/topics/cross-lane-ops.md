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

| Operation                        | Latency    | Pipeline | Range              | Arch        |
|----------------------------------|------------|----------|--------------------|-------------|
| DPP modifier                     | 0 extra    | VALU     | Within 16-lane row | CDNA3+CDNA4 |
| DPP wave variant                 | 0 extra    | VALU     | Cross-row (limited)| CDNA3+CDNA4 |
| ds_permute                       | ~20 cycles | LDS unit | Any lane in wave64 | CDNA3+CDNA4 |
| ds_bpermute                      | ~20 cycles | LDS unit | Any lane in wave64 | CDNA3+CDNA4 |
| ds_swizzle                       | ~20 cycles | LDS unit | Bitwise patterns   | CDNA3+CDNA4 |
| v_readfirstlane_b32              | 1 cycle    | VALU     | Lane 0 → SGPR     | CDNA3+CDNA4 |
| v_permlane16_swap_b32            | VALU       | VALU     | Cross 16-lane rows | CDNA4 only  |
| v_permlane32_swap_b32            | VALU       | VALU     | Cross 32-lane half | CDNA4 only  |

DPP modifiers are "free" — they attach to VALU instructions with zero extra cost.
ds_permute uses LDS hardware but NOT LDS memory (counts toward lgkmcnt).
CDNA4 permlane swaps are VALU-pipeline, avoiding LDS contention entirely.

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

### Wave64 reduction (sum) — 6 steps (CDNA3)
```cpp
float wave_sum(float val) {
    // Phase 1: intra-row DPP (4 steps, ~free)
    val += __shfl_down(val, 1);   // row_shr:1
    val += __shfl_down(val, 2);   // row_shr:2
    val += __shfl_down(val, 4);   // row_shr:4
    val += __shfl_down(val, 8);   // row_shr:8
    // Phase 2: cross-row ds_permute (2 steps, ~20 cycles each, LDS pipeline)
    val += __shfl_xor(val, 16);   // swap row pairs
    val += __shfl_xor(val, 32);   // swap half-waves
    return __shfl(val, 0);        // broadcast lane 0
}
```

### Wave64 reduction (sum) — 6 steps (CDNA4, all-VALU)
```cpp
float wave_sum_cdna4(float val) {
    // Phase 1: intra-row DPP (4 steps, ~free) — same as CDNA3
    val += __shfl_down(val, 1);   // row_shr:1
    val += __shfl_down(val, 2);   // row_shr:2
    val += __shfl_down(val, 4);   // row_shr:4
    val += __shfl_down(val, 8);   // row_shr:8
    // Phase 2: permlane swaps (VALU pipeline, no LDS contention!)
    float tmp = val;
    __builtin_amdgcn_permlane16_swap(tmp, val);  // swap across 16-lane rows
    val += tmp;
    tmp = val;
    __builtin_amdgcn_permlane32_swap(tmp, val);  // swap across 32-lane halves
    val += tmp;
    return __shfl(val, 0);        // broadcast lane 0
}
```
**Why CDNA4 version is better**: all 6 steps stay in the VALU pipeline. On CDNA3,
steps 5–6 use ds_permute (LDS pipeline, ~20 cycles each), which contends with LDS
loads/stores in LDS-heavy kernels like GEMM or attention.

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
// CDNA3 + CDNA4:
__builtin_amdgcn_ds_permute(src_lane * 4, val)   // gather (LDS pipeline)
__builtin_amdgcn_ds_bpermute(dst_lane * 4, val)  // scatter (LDS pipeline)
__builtin_amdgcn_ds_swizzle(val, pattern)         // bitwise (LDS pipeline)
__builtin_amdgcn_mov_dpp(val, ctrl, mask, bound)  // DPP (VALU pipeline)

// CDNA4 only — permlane swaps (VALU pipeline):
__builtin_amdgcn_permlane16_swap(vdst, src0)      // swap odd/even 16-lane rows
__builtin_amdgcn_permlane32_swap(vdst, src0)      // swap lanes 0-31 with 32-63
// NOTE: both are destructive — both vdst and src0 are modified!
// NOTE: requires 2 wait states if a prior VALU writes the src VGPR
// NOTE: requires 4 wait states after V_CMPX that writes EXEC
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

| Feature                  | CDNA3 (gfx940/942)        | CDNA4 (gfx950)                    |
|--------------------------|---------------------------|------------------------------------|
| DPP modifiers            | Yes (intra-row, VALU)     | Yes (identical)                    |
| ds_permute / ds_bpermute | Yes (~20 cyc, LDS pipe)   | Yes (identical)                    |
| ds_swizzle               | Yes (~20 cyc, LDS pipe)   | Yes (identical)                    |
| v_permlane16_swap_b32    | **Not available**         | **New** — VALU, swaps 16-lane rows |
| v_permlane32_swap_b32    | **Not available**         | **New** — VALU, swaps 32-lane halves|
| Wave64 reduction         | 4 DPP + 2 ds_permute      | 4 DPP + 2 permlane (all VALU)     |

**Key CDNA4 improvement**: Cross-row reduction steps (shifts by 16 and 32) move from
the LDS pipeline (`ds_permute`, ~20 cycles, contends with LDS loads/stores) to the
VALU pipeline (`v_permlane*_swap`, no LDS contention). This benefits LDS-heavy kernels
like GEMM and attention where LDS bandwidth is at a premium.

**Permlane swap caveats**:
- Destructive: both src and dst VGPRs are modified (need a tmp copy for reductions)
- 2 wait states required if a prior VALU writes the source VGPR
- 4 wait states required after V_CMPX writing EXEC

## Sources

- AMD GCN cross-lane ops: https://gpuopen.com/learn/amd-gcn-assembly-cross-lane-operations/
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Ch.6 (Data Share), Ch.4 (Vector ALU/DPP)
- HIP kernel language: https://rocm.docs.amd.com/projects/HIP/en/develop/reference/kernel_language.html
