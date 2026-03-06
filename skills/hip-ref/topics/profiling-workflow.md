# Profiling Workflow

## What it is

AMD provides a profiling stack: rocprof (basic HW counters), omniperf/rocprofiler-compute
(derived metrics, roofline, Speed-of-Light), and omnitrace (system-wide tracing). The
right tool depends on whether you need counter values, bottleneck analysis, or timeline
visualization.

## When you care

- Identifying if kernel is compute-bound, memory-bound, or latency-bound
- Measuring MFMA utilization in FMHA kernels
- Finding LDS bank conflicts, cache misses, pipeline stalls
- Comparing kernel versions with quantitative metrics
- Generating roofline plots

## Tool hierarchy

| Tool                    | Purpose                          | Output                    |
|-------------------------|----------------------------------|---------------------------|
| rocprof                 | Raw HW counter collection        | CSV of counter values     |
| omniperf (rocprofiler-compute) | Derived metrics, SoL, roofline | Interactive dashboard |
| omnitrace               | System-wide timeline tracing     | Perfetto/JSON timeline    |
| rocprofv3 (SDK)         | New unified API for counters     | Programmatic              |
| RGA                     | Static ISA analysis (offline)    | Register/instruction stats|

## How to use it

### Quick kernel timing
```bash
rocprof --stats ./my_kernel
# Output: kernel durations, call counts
```

### Omniperf workflow (recommended for optimization)
```bash
# Step 1: Profile
omniperf profile -n my_fmha -- ./my_kernel

# Step 2: Analyze
omniperf analyze -p workloads/my_fmha/

# Step 3: Look at Speed-of-Light (SoL) dashboard
# Shows % of peak for: compute, memory bandwidth, LDS, L2
```

### Key FMHA counters

| Counter                  | What it measures                     | Goal           |
|--------------------------|--------------------------------------|----------------|
| SQ_INSTS_MFMA            | MFMA instructions issued             | High           |
| SQ_INSTS_VALU            | VALU instructions issued             | Balanced       |
| SQ_BUSY_CYCLES           | Total CU busy cycles                 | High           |
| SQ_WAIT_INST_ANY         | Cycles waiting (stalls)              | Low            |
| SQ_LDS_BANK_CONFLICT     | LDS bank conflict events             | 0              |
| TCC_HIT / TCC_MISS       | L2 cache hit/miss                    | High hit rate  |
| TCP_TOTAL_READ/WRITE     | L1 cache read/write requests         | Monitor        |
| SQ_WAVES                 | Waves launched                       | Expected count |

### Counter collection with rocprof
```bash
# Create counter file:
cat > counters.txt << 'EOF'
pmc: SQ_INSTS_MFMA SQ_INSTS_VALU SQ_LDS_BANK_CONFLICT SQ_WAIT_INST_ANY
EOF

rocprof -i counters.txt ./my_kernel
# Output: results.csv with counter values per kernel invocation
```

### Omnitrace (timeline)
```bash
# Instrument and run:
omnitrace-instrument -- ./my_kernel

# View in browser (Perfetto format):
# Open chrome://tracing and load the output .json file
```

## Pitfalls

1. **Profiling overhead**: counter collection adds ~5-20% overhead. Don't benchmark
   profiled runs for timing.
2. **Counter limits**: hardware supports ~4-8 counters per pass. Omniperf runs
   multiple passes automatically — this multiplies execution time.
3. **Non-deterministic counters**: some counters are sampled, not exact. Average
   over multiple runs for stability.
4. **Kernel name matching**: rocprof uses mangled kernel names. Use `--stats` first
   to find the exact name, then filter with `-k kernelname`.

## CDNA3 vs CDNA4 differences

| Aspect                | CDNA3 (gfx940/942)       | CDNA4 (gfx950)                    |
|-----------------------|--------------------------|-----------------------------------|
| rocprof / omniperf    | Fully supported          | Requires ROCm version with gfx950 support |
| Counter names         | Standard MI300 counters  | Same names (SQ_*, TCC_*, TCP_*)   |
| GDS counters          | Available                | **Removed** (no GDS on CDNA4)     |
| MFMA counter meaning  | Per-instruction          | Per-instruction (but 2× K/instr)  |
| Occupancy metrics     | Based on max(VGPR,AGPR)  | Based on VGPR+AGPR (additive)     |

**Profiling note for CDNA4**: MFMA instruction counts (SQ_INSTS_MFMA) should be
interpreted carefully — each CDNA4 MFMA instruction processes 2× more data than
CDNA3 (doubled K dimension). Fewer instructions can mean the same or more compute.

## Sources

- Omniperf (rocprofiler-compute): https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/
- ROCProfiler-SDK (rocprofv3): https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/
- Omnitrace: https://rocm.docs.amd.com/projects/rocprofiler-systems/en/latest/
- Profiling guide: https://rocm.docs.amd.com/en/docs-6.1.0/how-to/llm-fine-tuning-optimization/profiling-and-debugging.html
- Performance counters: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch/mi300-mi200-performance-counters.html
