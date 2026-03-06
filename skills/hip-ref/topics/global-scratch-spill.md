# Global, Scratch, and Register Spills

## What it is

When a kernel uses more VGPRs than the hardware can allocate, the compiler spills
excess values to scratch memory — per-thread private memory backed by VRAM. Each
spill/reload is a full memory round-trip (~400 cycles). Detecting and eliminating
spills is one of the highest-impact optimizations.

## When you care

- Kernel is unexpectedly slow despite good algorithmic design
- Compiler output shows ScratchSize > 0
- Increasing occupancy target (amdgpu_waves_per_eu) tanks performance
- Need to differentiate VGPR spills vs SGPR→VGPR spills

## Key numbers

| Spill type    | Cost per access    | Path                         |
|---------------|--------------------|------------------------------|
| VGPR → scratch| ~300-400 cycles    | scratch_store → L1 → L2 → HBM|
| SGPR → VGPR  | 1 VALU cycle       | v_writelane_b32 / v_readlane  |
| VGPR → LDS   | ~20 cycles         | ds_write (if LDS available)   |

## How to use it

### Detecting spills
```bash
# Method 1: compiler resource usage
hipcc --offload-arch=gfx942 -Rpass-analysis=kernel-resource-usage -c kernel.cpp
# Look for: ScratchSize: 0 (good) or ScratchSize: 128 (bad — 128 bytes of spill)

# Method 2: ISA disassembly
hipcc --save-temps --offload-arch=gfx942 kernel.hip
# Search output for scratch_load / scratch_store instructions

# Method 3: llvm-objdump
llvm-objdump --mcpu=gfx942 -d kernel.o | grep scratch
# Any scratch_ instructions = spills present

# Method 4: kernel descriptor
llvm-objdump --mcpu=gfx942 -d kernel.o | grep -A20 ".amdhsa_kernel"
# Look for .amdhsa_private_segment_fixed_size (> 0 means spills)
```

### Eliminating spills
```cpp
// 1. Reduce VGPRs: simplify code, recompute instead of store
// 2. Allow lower occupancy:
__attribute__((amdgpu_waves_per_eu(2)))  // more registers available
// 3. Use AGPRs for MFMA (don't count against ArchVGPR spill on CDNA3)
// 4. Move uniform values to SGPRs
// 5. Use smaller types (FP16 packed: 2 per VGPR)
// 6. Reduce unroll factor
```

### When scratch is acceptable
```
Very rarely. A few spills in a long outer loop may be tolerable.
Spills in a tight inner loop are never acceptable.
Profile with and without — if spill version is still faster due to
better algorithmic choices, keep it. But usually spill-free wins.
```

## Pitfalls

1. **amdgpu_waves_per_eu too high**: compiler reduces VGPRs by spilling → catastrophic.
   3 waves with no spills >> 4 waves with spills.
2. **SGPR overflow is silent**: SGPRs spill to VGPRs, increasing VGPR pressure without
   obvious scratch usage. Check SGPR count if VGPR usage seems too high.
3. **Inline asm hiding spills**: compiler can't optimize register allocation around
   inline asm blocks, leading to unnecessary spills.

## CDNA3 vs CDNA4 differences

| Aspect                  | CDNA3 (gfx940/942)            | CDNA4 (gfx950)                     |
|-------------------------|-------------------------------|-------------------------------------|
| VGPR pool               | 512 ArchVGPR + 512 AGPR       | 512 unified (shared pool)           |
| AGPR spill pressure     | AGPRs in separate file         | AGPRs consume from VGPR pool        |
| scratch_load_lds        | **No**                        | **New** — scratch→LDS direct copy   |
| Spill path              | scratch→L1→L2→HBM             | Same path                           |

**CDNA4 spill implications**: With unified VGPR+AGPR, kernels using many AGPRs
(MFMA accumulators) have less VGPR headroom before spilling. A kernel using 128
ArchVGPRs + 128 AGPRs on CDNA3 (separate files, no spill) may approach the 512
total on CDNA4 (256 used). Adding temporaries pushes toward spills more easily.
Mitigate by reducing tile sizes or using the new scratch_load_lds for staging.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 8: Flat/Scratch Memory
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 8
- AMD Lab Notes: https://gpuopen.com/learn/amd-lab-notes/amd-lab-notes-register-pressure-readme/
