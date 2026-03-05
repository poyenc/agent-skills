# Software Pipelining

## What it is

Software pipelining overlaps data loading (iteration N+1) with computation (iteration N)
to hide memory latency. The key patterns are double-buffer LDS (PGR1_LB2) and
VGPR-only staging, both used extensively in high-performance GEMM and FMHA kernels.

## When you care

- FMHA inner loop over K/V sequence tiles
- Any MFMA loop where VMEM latency idles the matrix core
- Kernels at <80% MFMA utilization despite high compute intensity

## Key numbers

| Pattern        | LDS cost | VGPR cost       | Latency hiding | Complexity |
|----------------|----------|-----------------|----------------|------------|
| No pipelining  | 1×       | Baseline        | None           | Low        |
| Double buf LDS | 2×       | Baseline        | Good           | Medium     |
| Triple buf LDS | 3×       | Baseline        | Excellent      | High       |
| VGPR staging   | 1×       | +staging VGPRs  | Good           | Medium     |

## How to use it

### Double-buffer LDS (PGR1_LB2)
```cpp
// Allocate 2× LDS
__shared__ float lds_A[TILE_SIZE];  // buffer A
__shared__ float lds_B[TILE_SIZE];  // buffer B
float* lds_cur = lds_A;
float* lds_nxt = lds_B;

// Prologue: prefetch first tile
async_load(lds_cur, global_ptr[0]);
s_waitcnt();
s_barrier();

for (int i = 0; i < num_tiles - 1; i++) {
    // Start loading next tile into lds_nxt
    async_load(lds_nxt, global_ptr[i+1]);

    // Compute on current tile from lds_cur
    mfma_compute(lds_cur);

    // Wait for next tile load
    s_waitcnt();
    s_barrier();

    // Swap buffers
    float* tmp = lds_cur; lds_cur = lds_nxt; lds_nxt = tmp;
}

// Epilogue: compute last tile
mfma_compute(lds_cur);
```

### s_waitcnt management
```
Key insight: don't wait for ALL loads, wait for SPECIFIC loads.

// 4 loads in flight:
global_load v0, ...   // load 0 (vmcnt=4 after this)
global_load v1, ...   // load 1 (vmcnt=4)
global_load v2, ...   // load 2 (vmcnt=4)
global_load v3, ...   // load 3 (vmcnt=4)

s_waitcnt vmcnt(3)    // wait for load 0 only
use(v0)               // safe

// ... more compute ...

s_waitcnt vmcnt(2)    // wait for load 1
use(v1)               // safe

// NEVER: s_waitcnt vmcnt(0) between every load/use pair
// That serializes everything and wastes pipeline overlap.
```

### FMHA pipelining pattern
```
Pipeline over K/V sequence tiles:
  Prologue: prefetch K[0], V[0]
  Loop i:
    1. Issue MFMA: Q × K[i]^T → S[i] (attention scores)
    2. Prefetch K[i+1]
    3. Apply softmax to S[i] (VALU, can overlap with VMEM prefetch)
    4. Issue MFMA: S[i] × V[i] → O (output accumulation)
    5. Prefetch V[i+1]
  Epilogue: process last tile

This overlaps K[i+1] prefetch with Q×K[i] MFMA,
and V[i+1] prefetch with S[i]×V[i] MFMA.
```

### LDS budget calculation
```
With double-buffer:
  LDS needed = 2 × tile_size × element_bytes

Example (FP16, 128×64 tile):
  2 × 128 × 64 × 2 = 32,768 bytes = 32 KB per buffer × 2 = 64 KB total
  → Uses ALL LDS → only 1 workgroup per CU → 4 waves per CU (1 per SIMD)

If you need >64KB: reduce tile size, or use VGPR staging instead of LDS double-buf.
```

## Pitfalls

1. **Double buffer uses 2× LDS**: may limit to 1 workgroup per CU.
2. **Forgetting s_barrier**: between LDS write (wave A) and LDS read (wave B).
3. **Over-pipelining**: triple buffering adds complexity with diminishing returns.
   Double buffer is usually sufficient.
4. **Wrong vmcnt value**: off-by-one in vmcnt causes use-before-ready bugs.
   Count your outstanding loads carefully.

## Sources

- rocWMMA programmer's guide (PGR1_LB2 pattern): https://rocm.docs.amd.com/projects/rocWMMA/en/latest/conceptual/programmers-guide.html
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 2 (pipeline model)
