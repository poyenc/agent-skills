# XCD Topology & NUMA Effects

## What it is

MI300X/MI325X use 8 XCDs (Accelerator Complex Dies) on 2 IODs. Each XCD is a
complete GPU die with its own CUs and L2 cache partition. NPS (NUMA Per Socket)
modes control how memory is partitioned across XCDs, affecting bandwidth locality.

## When you care

- Kernel accesses memory "owned" by different XCDs → reduced bandwidth
- Choosing NPS mode for best FMHA performance
- Understanding why same kernel runs differently on different NPS configs
- Multi-GPU scale-up topology planning

## Key numbers

| Property         | CDNA3 MI300X    | CDNA3 MI325X    | CDNA4 MI350X    |
|------------------|-----------------|-----------------|-----------------|
| XCDs             | 8               | 8               | 8               |
| CUs per XCD      | 38              | 38              | 32              |
| L2 per XCD       | 4 MB            | 4 MB            | 4 MB            |
| L2 total         | 256 MB          | 256 MB          | 256 MB          |
| IODs             | 2               | 2               | 2               |
| XCDs per IOD     | 4               | 4               | 4               |
| IF links         | 7 × 128 GB/s    | 7 × 128 GB/s    | 7 × 154 GB/s    |

### NPS modes (MI300X)

| Mode  | NUMA domains | XCDs per domain | Memory partition | Use case            |
|-------|--------------|-----------------|------------------|---------------------|
| NPS1  | 1            | 8               | Unified          | Default, simplest   |
| NPS2  | 2            | 4               | 2 halves         | Moderate locality   |
| NPS4  | 4            | 2               | 4 quarters       | Best BW locality    |

## How to use it

### Checking current mode
```bash
amd-smi static --nps
# or
rocm-smi --showcomputepartition
```

### Recommendation
```
NPS1: Use for most workloads. All memory is uniformly accessible.
      No NUMA-aware allocation needed. Slight bandwidth penalty for
      cross-XCD accesses but programming is simple.

NPS4: Use for bandwidth-sensitive workloads that can be NUMA-aware.
      Requires hipMemAdvise or numactl for correct memory placement.
      Best for workloads with strong data locality.

FMHA: NPS1 is usually fine. The attention pattern accesses Q/K/V
      arrays that may span multiple NUMA domains regardless of placement.
```

### NUMA-aware allocation
```cpp
// With NPS4, use hipMemAdvise for preferred location:
hipMemAdvise(ptr, size, hipMemAdviseSetPreferredLocation, device_id);
// Or use hipMallocManaged with hints
```

## Pitfalls

1. **Ignoring NPS mode**: code developed on NPS1 may perform differently on NPS4.
2. **Cross-XCD L2 latency**: accessing remote XCD's L2 adds ~50-100ns.
3. **Compute partition modes (CPX)**: partitioning XCDs into separate "GPUs"
   changes how hipSetDevice works. Know your configuration.

## Sources

- Compute/memory partition modes: https://rocm.blogs.amd.com/software-tools-optimization/compute-memory-modes/README.html
- MI300 architecture: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch/mi300.html
- MI300 system optimization: https://instinct.docs.amd.com/projects/amdgpu-docs/en/latest/system-optimization/mi300x.html
