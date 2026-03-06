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

| Level           | CDNA3 (per unit)   | CDNA4 (per unit)   | Latency     | Notes                    |
|-----------------|--------------------|--------------------|-------------|--------------------------|
| Registers       | 512 VGPR + 512 AGPR| 512 unified VGPR  | 0-1 cycles  | Fastest                  |
| LDS             | 64 KB/CU           | **128 KB/CU**     | ~20 cycles  | Shared within workgroup  |
| L0 vector cache | 16 KB/CU           | 16 KB/CU          | ~few cycles | Read-only (texture path) |
| L0 scalar cache | 16 KB/CU           | 16 KB/CU          | ~few cycles | SMEM loads               |
| L1 data cache   | 32 KB/CU           | 32 KB/CU          | ~30-50 cy   | Write-through to L2      |
| L2 cache        | 4 MB/XCD           | 4 MB/XCD          | ~100-200 cy | Last-level cache         |
| L2 total        | 32 MB (8 XCDs)     | **48 MB (12 XCDs)**| —          | Per-XCD partitioned      |
| HBM             | varies per GPU     | varies per GPU      | 300-400 cy  | Main memory              |

### HBM specs by GPU

| GPU    | Arch  | HBM Type | Capacity | Bandwidth | XCDs | L2 total |
|--------|-------|----------|----------|-----------|------|----------|
| MI300X | CDNA3 | HBM3     | 192 GB   | 5.3 TB/s  | 8    | 32 MB    |
| MI300A | CDNA3 | HBM3     | 128 GB   | 5.3 TB/s  | 8    | 32 MB    |
| MI325X | CDNA3 | HBM3E    | 256 GB   | 6.0 TB/s  | 8    | 32 MB    |
| MI350X | CDNA4 | HBM3E    | 288 GB   | 12.2 TB/s | 12   | 48 MB    |
| MI355X | CDNA4 | HBM3E    | 288 GB   | 12.2 TB/s | 12   | 48 MB    |

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

## CDNA3 vs CDNA4 differences

| Aspect              | CDNA3 (MI300X/MI325X)     | CDNA4 (MI350X/MI355X)         |
|---------------------|---------------------------|-------------------------------|
| XCDs per GPU        | 8                         | **12** (+50%)                 |
| LDS per CU          | 64 KB                     | **128 KB** (2× increase)      |
| L2 per XCD          | 4 MB                      | 4 MB (same)                   |
| L2 total            | 32 MB                     | **48 MB** (+50%)              |
| HBM type            | HBM3 / HBM3E             | HBM3E                         |
| HBM bandwidth       | 5.3-6.0 TB/s              | **12.2 TB/s** (~2.3× MI300X) |
| HBM capacity        | 192-256 GB                | 288 GB                        |
| Register file       | 512 ArchVGPR + 512 AGPR   | 512 unified                   |
| Cache control model | GLC/SLC/DLC bits          | **SCOPE + TH** (new)          |
| global_load_lds     | Not available             | **New** — direct global→LDS   |

**Key architectural shifts**:
- 50% more XCDs means 50% more CUs and 50% more L2 aggregate cache
- 2× LDS enables larger tiles and more double-buffering headroom
- 2.3× HBM bandwidth shifts the compute-vs-memory balance point
- global_load_lds provides a new async copy path (see async-copy-prefetch topic)

## Sources

- GPU architecture overview: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch.html
- MI300 architecture: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch/mi300.html
- CDNA3 whitepaper: `pdfs/amd-cdna3-whitepaper.pdf`
- CDNA4 whitepaper: `pdfs/amd-cdna4-whitepaper.pdf`
