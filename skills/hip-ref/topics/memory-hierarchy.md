# Memory Hierarchy

## What it is

AMD CDNA GPUs have a multi-level cache hierarchy: per-CU L0 caches (vector/scalar),
per-CU L1 data cache, per-XCD L2 cache, and HBM. Understanding bandwidth and latency
at each level determines how to structure data access for maximum throughput.

## When you care

- Determining if your kernel is memory-bound or compute-bound
- Choosing between LDS, L1, L2, or HBM for data placement
- Optimizing tile sizes for cache reuse
- Understanding cross-XCD L2 access penalties

## Key numbers

| Level           | Size (per unit)   | Bandwidth (per GPU)   | Latency     | Notes                    |
|-----------------|-------------------|-----------------------|-------------|--------------------------|
| Registers       | 512 VGPRs/SIMD    | N/A                   | 0-1 cycles  | Fastest                  |
| LDS             | 64 KB/CU          | ~12-16 TB/s total     | ~20 cycles  | Shared within workgroup  |
| L0 vector cache | 16 KB/CU          | N/A                   | ~few cycles | Read-only (texture path) |
| L0 scalar cache | 16 KB/CU          | N/A                   | ~few cycles | SMEM loads               |
| L1 data cache   | 32 KB/CU          | ~6-8 TB/s total       | ~30-50 cy   | Write-through to L2      |
| L2 cache        | 4 MB/XCD          | ~5-6 TB/s total       | ~100-200 cy | Last-level cache         |
| L2 total        | 256 MB (8 XCDs)   |                       |             | Acts as Infinity Cache   |
| HBM             | varies per GPU     | 5.3-8.0 TB/s          | 300-400 cy  | Main memory              |

### HBM specs by GPU

| GPU    | HBM Type | Capacity | Bandwidth |
|--------|----------|----------|-----------|
| MI300X | HBM3     | 192 GB   | 5.3 TB/s  |
| MI300A | HBM3     | 128 GB   | 5.3 TB/s  |
| MI325X | HBM3E    | 256 GB   | 6.0 TB/s  |
| MI350X | HBM3E    | 288 GB   | 8.0 TB/s  |
| MI355X | HBM3E    | 288 GB   | 8.0 TB/s  |

## How to use it

### Access pattern recommendations
```
Registers: keep hot loop variables, MFMA accumulators
LDS:       share data within workgroup (Q tiles, partial sums)
L1/L2:     rely on caching for reused global data (K/V tiles if small)
HBM:       streaming access (large K/V sequences, batch dimensions)
```

### FMHA data placement
```
Q tile:  load to LDS (reused across all K/V tiles)
K tile:  stream from HBM, may cache in L2 for multi-head reuse
V tile:  stream from HBM after attention scores computed
Softmax: partial sums in registers + cross-lane reduction
Output:  accumulate in registers, store to HBM at the end
```

### L2 partitioning across XCDs
```
Each XCD has its own 4MB L2 partition. A CU on XCD-0 accessing data
cached in XCD-3's L2 pays extra latency (~2× vs local L2).

Impact: kernel data locality matters. If K/V data is accessed by CUs
on the same XCD, L2 hits are fast. Random access across XCDs is slower.

NPS1 mode: all HBM is uniformly addressable, L2 handles routing.
```

## Pitfalls

1. **L2 thrashing**: working set > 4MB per XCD evicts useful data. Tile sizes should
   keep hot data within local L2.
2. **L1 is write-through**: writes go through L1 to L2 immediately. L1 is mainly
   useful for read reuse.
3. **Cross-XCD L2 misses**: accessing data from another XCD's L2 is slower. Keep
   data access patterns XCD-local when possible.

## Sources

- GPU architecture overview: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch.html
- MI300 architecture: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch/mi300.html
- CDNA3 whitepaper: `pdfs/amd-cdna3-whitepaper.pdf`
- CDNA4 whitepaper: `pdfs/amd-cdna4-whitepaper.pdf`
