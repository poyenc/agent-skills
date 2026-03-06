# Wavefront Scheduling & Pipeline Overlap

## What it is

Each CU has 4 SIMDs, each running waves in-order. The scheduler picks one ready
wave per SIMD per cycle to issue an instruction. The key performance insight is
that different instruction types (VALU, VMEM, LDS, MFMA) use different pipelines
and can overlap — especially MFMA, which occupies the matrix core for 64 cycles
while leaving VALU/VMEM/LDS free.

## When you care

- Designing software-pipelined loops to overlap compute and memory
- Understanding why MFMA-heavy kernels can run at low occupancy
- Debugging pipeline stalls (too many s_waitcnt vmcnt(0))
- Maximizing instruction-level parallelism within a single wave

## Key numbers

| Pipeline    | Throughput         | Latency (approx)    | Notes                       |
|-------------|--------------------|--------------------|------------------------------|
| VALU        | 1 op/cycle/SIMD    | 4-8 cycles         | 16-wide SIMD, wave64 = 4 cy |
| VMEM (load) | 1 op/cycle/SIMD    | 300-400 cy (HBM)   | Pipelined, many in-flight    |
| LDS         | 1 op/cycle/SIMD    | ~20-30 cycles      | ds_read/ds_write             |
| MFMA        | 1 op/64 cy (32×32) | 64 cycles (32×32)  | Matrix core, frees VALU/VMEM |
| SMEM        | 1 op/cycle         | ~20 cycles          | Scalar memory loads          |
| Branch      | 1 op/cycle         | N/A                 | Scalar branch unit           |

### MFMA pipeline overlap
```
During 64-cycle MFMA execution on matrix core:
  VALU pipeline: available — can execute ~64 VALU instructions
  VMEM pipeline: available — can issue global loads
  LDS pipeline:  available — can execute ds_read/ds_write

This is WHY MFMA kernels can achieve high throughput at low occupancy:
you don't need other waves to fill pipeline bubbles — the same wave
does useful work while its MFMA is in flight.
```

## How to use it

### Interleaving MFMA with memory loads
```
Optimal inner loop structure:
  1. Issue MFMA (64 cycles on matrix core)
  2. While MFMA runs:
     - Issue VMEM loads for next iteration (global_load)
     - Issue LDS reads for current data
     - Execute VALU ops (address calc, softmax partial)
  3. s_waitcnt for MFMA completion (if needed)
  4. Repeat

The key: DON'T s_waitcnt vmcnt(0) after every load.
Keep multiple loads in flight and only wait when you need the data.
```

### s_waitcnt usage
```
s_waitcnt vmcnt(N)   — wait until outstanding VMEM ops ≤ N
s_waitcnt lgkmcnt(N) — wait until outstanding LDS/SMEM ops ≤ N
s_waitcnt expcnt(N)  — CDNA3: wait for exports/GDS; CDNA4: unused (ignored)

s_waitcnt vmcnt(0) lgkmcnt(0)  — wait for everything (serialize)

For pipelining: use vmcnt(K-1) where K = loads in flight minus the one
you need now. E.g., 4 loads in flight, need oldest: vmcnt(3).
```

## Pitfalls

1. **Over-synchronizing**: `s_waitcnt vmcnt(0)` after every load serializes the
   pipeline. Keep loads in flight and wait only when consuming data.
2. **Ignoring MFMA pipeline freedom**: If your MFMA loop does nothing but MFMA →
   waitcnt → MFMA, you're wasting 64 cycles of free VALU/VMEM time per MFMA.
3. **Too few waves at low ILP**: If your code has low instruction-level parallelism
   (e.g., sequential dependencies), you need more waves to hide latency.

## CDNA3 vs CDNA4 differences

| Aspect              | CDNA3 (gfx940/942)        | CDNA4 (gfx950)                    |
|---------------------|---------------------------|-----------------------------------|
| SIMDs per CU        | 4                         | 4 (same)                          |
| Max waves per SIMD  | 8                         | 8 (same)                          |
| VALU throughput     | 1 op/cycle/SIMD           | 1 op/cycle/SIMD (same)            |
| MFMA throughput     | 1 op/64 cy (32×32×8 FP16) | 1 op/64 cy (32×32×16 FP16, **2× K**) |
| expcnt counter      | Active (GDS/exports)      | **Unused** (GDS removed)          |
| GDS pipeline        | Available                 | **Removed**                       |
| VOPD (dual-issue)   | No                        | No (RDNA-only feature)            |

**Key CDNA4 scheduling implication**: MFMA K-dimension doubling means each MFMA
instruction processes 2× more data in the same 64-cycle window. This effectively
doubles compute throughput per MFMA, giving more free VALU/VMEM cycles per FLOPs
ratio — making software pipelining even more effective.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 2: Shader Processor
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 2
