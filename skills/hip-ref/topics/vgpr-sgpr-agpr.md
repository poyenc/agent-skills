# VGPR, SGPR, and AGPR Register Types

## What it is

AMD GPUs have three register types: VGPRs hold per-lane (divergent) data, SGPRs
hold uniform (scalar) data shared across a wavefront, and AGPRs are accumulation
registers for MFMA output. Understanding allocation, movement costs, and how they
interact is essential for register pressure management.

## When you care

- Tuning register usage to hit an occupancy target
- Debugging spills to scratch memory
- Writing MFMA kernels where accumulator management matters
- Understanding ArchVGPR vs AccVGPR in compiler output

## Key numbers

| Register type | Per SIMD (CDNA3)     | Per SIMD (CDNA4)    | Per wave max | Granularity |
|---------------|----------------------|---------------------|--------------|-------------|
| ArchVGPR      | 512 (separate file)  | 512 (unified file)  | 256          | 16 VGPRs    |
| AGPR (AccVGPR)| 512 (separate file)  | Shared with ArchVGPR| 256          | 4 AGPRs     |
| SGPR          | 800                  | 800                 | 102 (+4 special) | 16 SGPRs|

Special SGPRs (not from the 102 budget): VCC (2), EXEC (2), FLAT_SCRATCH (2).

## How to use it

### VGPRs (v0-v255): per-lane divergent data
```
Purpose: thread-private variables, loaded data, VALU operands
64-bit values (double, pointers) consume 2 consecutive VGPRs.
```

### SGPRs (s0-s101): uniform scalar data
```
Purpose: constants, base addresses, loop counters, buffer descriptors
Buffer resource descriptor = 4 consecutive SGPRs (s[n:n+3])
```

### AGPRs (a0-a255): MFMA accumulators
```
CDNA3: SEPARATE physical file from ArchVGPRs
  - MFMA writes results to AGPRs
  - To use in VALU/store: v_accvgpr_read_b32 v_dst, a_src (1 VALU cycle)
  - To initialize: v_accvgpr_write_b32 a_dst, v_src (1 VALU cycle)
  - 32×32 MFMA: 16 read + 16 write = 32 VALU cycles overhead

CDNA4: UNIFIED register file — AGPRs and VGPRs share the same physical storage
  - v_accvgpr_read/write still exists but is a no-op (zero cost)
  - MFMA can read/write VGPRs directly as accumulators
  - But: ArchVGPRs + AGPRs consume from SAME 512-register pool (additive!)
```

### Occupancy: CDNA3 max() rule vs CDNA4 additive rule
```
CDNA3: effective_vgprs = max(ArchVGPRs_allocated, AGPRs_allocated)
  128 ArchVGPRs + 16 AGPRs  → max(128,16)  = 128 → 4 waves
  64 ArchVGPRs + 128 AGPRs  → max(64,128)  = 128 → 4 waves
  128 ArchVGPRs + 64 AGPRs  → max(128,64)  = 128 → 4 waves (AGPRs "free")

CDNA4: effective_vgprs = ArchVGPRs_allocated + AGPRs_allocated
  128 ArchVGPRs + 16 AGPRs  → 128+16  = 144 → 3 waves
  64 ArchVGPRs + 128 AGPRs  → 64+128  = 192 → 2 waves
  128 ArchVGPRs + 64 AGPRs  → 128+64  = 192 → 2 waves (AGPRs NOT free!)

  WARNING: MFMA-heavy kernels may see lower occupancy on CDNA4 vs CDNA3 with
  identical register counts. Offset by higher per-MFMA throughput (doubled K).
```

### Reducing VGPR pressure
```cpp
// 1. Recompute instead of storing temporaries
// 2. Use SGPRs for uniform values
// 3. Use FP16 packed (2 values per VGPR via v_pk_*)
// 4. Limit unrolling (#pragma unroll 4 vs full unroll)
// 5. Use __attribute__((amdgpu_num_vgpr(N))) to cap
```

## Pitfalls

1. **Spills to scratch are catastrophic**: each spill/reload ≈ 400 cycles. Check
   `ScratchSize: N` in compiler output — N > 0 means spills.
2. **SGPR spills are hidden**: overflow SGPRs spill to VGPRs, silently increasing
   VGPR pressure.
3. **64-bit values = 2 VGPRs**: pointers, doubles, int64 eat registers fast.
4. **Aggressive unrolling inflates live ranges**: more live variables = more VGPRs.

## CDNA3 vs CDNA4 differences

| Aspect                   | CDNA3 (gfx940/942)           | CDNA4 (gfx950)                   |
|--------------------------|------------------------------|----------------------------------|
| AGPR physical file       | Separate from ArchVGPR       | Unified — same physical storage  |
| Total VGPR file/SIMD     | 512 ArchVGPR + 512 AGPR      | 512 unified (shared pool)        |
| Occupancy calc           | max(ArchVGPRs, AGPRs)        | ArchVGPRs + AGPRs (additive)     |
| v_accvgpr_read/write     | Required (1 VALU cycle each) | No-op (zero cost, same file)     |
| MFMA accumulator access  | Via AGPRs, copy to VGPRs     | Direct VGPR access               |

**Key implication**: On CDNA3, a kernel using 128 ArchVGPRs + 128 AGPRs gets 4 waves
(max(128,128)=128, 512/128=4). On CDNA4, the same kernel gets 2 waves
(128+128=256, 512/256=2). CDNA4 compensates with doubled MFMA K-dimensions,
so each wave does more work per instruction.

## Sources

- AMD Lab Notes — register pressure: https://gpuopen.com/learn/amd-lab-notes/amd-lab-notes-register-pressure-readme/
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 2: Shader Processor
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 2
