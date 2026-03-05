# Roofline Analysis

## What it is

Roofline analysis identifies whether a kernel is compute-bound or memory-bound by
comparing its arithmetic intensity (FLOP/byte) against the hardware's compute-to-bandwidth
ratio. The ridge point where compute and memory roofs meet tells you the minimum
arithmetic intensity needed to be compute-bound.

## When you care

- Determining the theoretical bottleneck before optimizing
- Choosing tile sizes that achieve sufficient data reuse
- Comparing FMHA at different sequence lengths (AI changes)
- Setting performance expectations (% of peak achievable)

## Key numbers

### Ridge points (FLOP/byte)

| Type     | MI300X          | MI350X          |
|----------|-----------------|-----------------|
| FP16 MFMA| 1307/5.3 = 247  | 2310/8.0 = 289  |
| FP8 MFMA | 2615/5.3 = 493  | 4614/8.0 = 577  |
| FP4 MFMA | N/A             | 9228/8.0 = 1154 |
| FP32 VALU| 163/5.3 = 31    | 144/8.0 = 18    |

Higher ridge point = harder to be compute-bound = more data reuse needed.

### FMHA arithmetic intensity examples
```
GEMM-like Q×K^T (FP16):
  FLOPs = 2 × M × N × K  (per matrix multiply)
  Bytes = 2 × (M×K + K×N + M×N) × sizeof(FP16)
  AI ≈ M×N/(M+N) for large K

For attention with head_dim=128, seq_len=2048:
  Q×K^T: AI ≈ seq_len/2 ≈ 1024 FLOP/byte >> ridge point → compute-bound
  For seq_len=32: AI ≈ 16 FLOP/byte << ridge point → memory-bound!

Softmax (elementwise): AI ≈ 5-10 FLOP/byte → always memory-bound
V accumulation: depends on tile sizes
```

## How to use it

### Omniperf roofline
```bash
# Generate roofline plot:
omniperf profile -n myrun -- ./my_kernel
omniperf analyze -p workloads/myrun/ --roof
# Shows kernel points on compute + memory roofline
```

### Speed-of-Light interpretation
```
SoL Compute: 85%  → close to peak FLOPS → compute-bound
SoL Memory:  30%  → not close to peak BW → data is being reused

If SoL Compute > SoL Memory → compute-bound (optimize instruction mix)
If SoL Memory > SoL Compute → memory-bound (optimize data reuse/caching)
If both low → latency-bound (increase occupancy or pipeline overlap)
```

### Decision framework
```
1. Compute AI of your kernel mathematically
2. Compare to ridge point for your data type
3. If AI > ridge: compute-bound → maximize MFMA utilization
4. If AI < ridge: memory-bound → maximize data reuse (bigger tiles, LDS caching)
5. If AI ≈ ridge: balanced → optimize both
```

## Pitfalls

1. **Theoretical vs achieved AI**: real AI is lower than theoretical due to cache
   misses, redundant loads, padding. Measure with omniperf.
2. **Ignoring softmax**: FMHA isn't just GEMM. Softmax is always memory-bound.
   Total kernel is a mix of compute-bound GEMM + memory-bound softmax.
3. **Peak BW is HBM, not L2**: if your data fits in L2, effective bandwidth is
   higher → ridge point moves up → harder to be compute-bound.

## Sources

- Omniperf roofline: https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/
- MI300 performance counters: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch/mi300-mi200-performance-counters.html
