# Occupancy & Register Pressure

## What it is

Occupancy is the ratio of active waves per SIMD to the maximum possible waves.
It is determined by three resources: VGPRs, SGPRs, and LDS. Register pressure
is the primary occupancy limiter in most HIP kernels. Understanding the
relationship between register usage and wave slots is critical for performance
tuning — but higher occupancy is not always better.

## When you care

- Kernel performance drops at specific register counts (occupancy cliffs)
- Compiler output shows unexpected spills to scratch
- Memory-bound kernels need more waves to hide latency
- Balancing tile size (more registers) vs parallelism (more waves)

## Key numbers

| Resource                   | CDNA3 (gfx940/942)          | CDNA4 (gfx950)              |
|----------------------------|-----------------------------|-----------------------------|
| SIMDs per CU               | 4                           | 4                           |
| Max waves per SIMD         | 8                           | 8                           |
| Max waves per CU           | 32                          | 32                          |
| VGPRs per SIMD             | 512 ArchVGPR + 512 AGPR     | 512 unified (shared pool)   |
| AGPR occupancy rule        | max(ArchVGPRs, AGPRs)       | ArchVGPRs + AGPRs (additive)|
| SGPR budget per SIMD       | 800                         | 800                         |
| Max SGPRs per wave         | 102 (+4 special)            | 102 (+4 special)            |
| LDS per CU                 | 64 KB                       | 128 KB                      |
| VGPR allocation granularity| 16 VGPRs (wave64)           | 16 VGPRs                    |
| SGPR allocation granularity| 16 SGPRs                    | 16 SGPRs                    |

### Occupancy table — VGPRs vs waves per SIMD (CDNA3, 512 VGPRs/SIMD)

| VGPRs used | Allocated (ceil to 16) | Waves/SIMD | Occupancy |
|------------|------------------------|------------|-----------|
| 1-64       | 64                     | 8          | 100%      |
| 65-72      | 72                     | 7          | 87.5%     |
| 73-80      | 80                     | 6          | 75%       |
| 81-84      | 84                     | 6          | 75%       |
| 85-96      | 96                     | 5          | 62.5%     |
| 97-102     | 112                    | 4          | 50%       |
| 103-128    | 128                    | 4          | 50%       |
| **129-144**| **144**                | **3**      | **37.5%** |
| 145-170    | 176                    | 2          | 25%       |
| 171-256    | 256                    | 2          | 25%       |
| 257-512    | 512                    | 1          | 12.5%     |

### Critical cliff: 128→129 boundary

```
128 VGPRs: allocated = 128, waves = 512/128 = 4 waves (50%)
129 VGPRs: allocated = 144, waves = 512/144 = 3 waves (37.5%)

One extra VGPR costs 25% of your wave slots.
```

## How to use it

### Occupancy formula

```
For each SIMD:
  vgpr_waves = floor(total_vgprs / (ceil(kernel_vgprs / 16) * 16))
  sgpr_waves = floor(total_sgprs / (ceil(kernel_sgprs / 16) * 16))

For the CU (LDS is CU-level, not SIMD-level):
  max_workgroups = floor(lds_per_cu / lds_per_workgroup)
  lds_waves_per_simd = max_workgroups * waves_per_workgroup / 4

  waves_per_simd = min(vgpr_waves, sgpr_waves, lds_waves_per_simd, 8)
```

### AGPR impact on occupancy

```
CDNA3: ArchVGPRs and AccVGPRs are SEPARATE physical register files.
  Effective VGPR usage = max(ArchVGPRs_allocated, AGPRs_allocated)
  Example:
    80 ArchVGPRs + 64 AGPRs  → max(80, 64)  = 80  → 6 waves
    64 ArchVGPRs + 80 AGPRs  → max(64, 80)  = 80  → 6 waves
    128 ArchVGPRs + 16 AGPRs → max(128, 16) = 128 → 4 waves
  AGPRs are "free" as long as they don't exceed your ArchVGPR allocation.

CDNA4: ArchVGPRs and AccVGPRs are UNIFIED (same physical storage).
  Effective VGPR usage = ArchVGPRs_allocated + AGPRs_allocated
  Example:
    80 ArchVGPRs + 64 AGPRs  → 80+64  = 144 → 3 waves (was 6 on CDNA3!)
    64 ArchVGPRs + 80 AGPRs  → 64+80  = 144 → 3 waves
    128 ArchVGPRs + 16 AGPRs → 128+16 = 144 → 3 waves (was 4 on CDNA3)
  AGPRs ALWAYS cost occupancy on CDNA4. MFMA-heavy kernels may see lower
  occupancy — compensated by doubled MFMA throughput (2x K dimension).
```

### Checking occupancy

```bash
# Compiler output:
hipcc --offload-arch=gfx942 -Rpass-analysis=kernel-resource-usage -c kernel.cpp
# Output: SGPRs: 48, VGPRs: 128, AGPRs: 16, ScratchSize: 0, Occupancy: 4

# From binary:
llvm-objdump --mcpu=gfx942 -d kernel.o | grep -A5 ".amdhsa_kernel"
```

### Controlling register allocation

```cpp
// Target specific wave count:
__attribute__((amdgpu_waves_per_eu(4, 4)))
__global__ void kernel(...) { ... }

// Cap VGPR usage:
__attribute__((amdgpu_num_vgpr(128)))
__global__ void kernel(...) { ... }

// Workgroup size hint:
__attribute__((amdgpu_flat_work_group_size(256, 256)))
__global__ void kernel(...) { ... }
```

### When lower occupancy is acceptable

```
GEMM/MFMA-heavy kernels often run at 1-2 waves/SIMD and still hit >90% peak.

Why: MFMA takes 64 cycles, during which VALU/VMEM/LDS pipelines can execute
other instructions from the SAME wave. Software pipelining hides memory
latency within a single wave. High register count enables larger tiles
with better data reuse.

Rule of thumb:
  Memory-bound kernels: need 4+ waves/SIMD (50%+ occupancy)
  Compute-bound (MFMA-heavy): 1-2 waves/SIMD often optimal
  Mixed: profile both and compare
```

## Pitfalls

1. **Blindly maximizing occupancy**: More waves is NOT always better. For
   compute-bound kernels, reducing occupancy to use larger tiles often wins.

2. **The 128→129 cliff**: Most common performance regression. Adding one temporary
   can push past 128 VGPRs, losing 25% occupancy. Watch compiler output.

3. **LDS as the hidden bottleneck**: 64KB per CU (CDNA3) or 128KB (CDNA4), shared
   among all waves. CDNA4's larger LDS relaxes this constraint.

4. **amdgpu_waves_per_eu causing spills**: Setting too high forces the compiler to
   reduce VGPRs, potentially spilling to scratch. 3 waves with no spills almost
   always beats 4 waves with spills.

5. **Forgetting AGPR contribution**: On CDNA3, if AGPRs > ArchVGPRs, AGPRs become
   the occupancy limiter (max() rule).

## CDNA3 vs CDNA4 differences

| Aspect              | CDNA3 (gfx940/942)              | CDNA4 (gfx950)                       |
|---------------------|----------------------------------|--------------------------------------|
| VGPRs per SIMD      | 512 ArchVGPR + 512 AGPR (separate)| 512 unified (ArchVGPR + AGPR shared)|
| AGPR accounting     | max(ArchVGPRs, AGPRs)            | ArchVGPRs + AGPRs (additive)         |
| Occupancy cliffs    | 64, 72, 80, 96, 128, 144, 256   | Same cliffs, but AGPR cost now adds  |
| LDS per CU          | 64 KB                            | 128 KB (relaxes LDS-limited occupancy)|
| LDS occupancy       | 64KB / LDS_per_WG                | 128KB / LDS_per_WG (2x headroom)    |

**CDNA4 occupancy tradeoff**: MFMA-heavy kernels lose occupancy from additive AGPR
accounting, but gain from 128 KB LDS (more workgroups fit) and doubled MFMA K-dimensions
(each wave does 2x more compute per instruction, needing fewer waves for throughput).

## Sources

- AMD Lab Notes on register pressure: https://gpuopen.com/learn/amd-lab-notes/amd-lab-notes-register-pressure-readme/
- Optimizing GPU occupancy: https://gpuopen.com/learn/optimizing-gpu-occupancy-resource-usage-large-thread-groups/
- CDNA3 ISA reference: `pdfs/cdna3-isa-reference.pdf` — Chapter 2: Shader Processor
- CDNA4 ISA reference: `pdfs/cdna4-isa-reference.pdf` — Chapter 2
