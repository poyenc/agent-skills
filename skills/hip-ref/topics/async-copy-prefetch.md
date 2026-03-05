# Async Copy & Prefetch Patterns

## What it is

Async copy overlaps global memory loads with computation by issuing loads early
and consuming results later. Two main approaches: VGPR staging (load global→VGPR,
then VGPR→LDS) and buffer_load_lds (direct global→LDS bypassing VGPRs). Combined
with software pipelining, this hides the 300-400 cycle HBM latency.

## When you care

- FMHA inner loop: loading next K/V tile while computing on current tile
- Any kernel where VMEM latency is the bottleneck
- Reducing VGPR pressure by using buffer_load_lds
- Implementing double/triple-buffered LDS patterns

## Key numbers

| Approach            | VGPR cost        | Latency hiding | Complexity |
|---------------------|------------------|----------------|------------|
| VGPR staging        | High (staging regs) | Good        | Medium     |
| buffer_load_lds     | Zero             | Good           | High       |
| Software pipeline   | 2× LDS           | Excellent      | High       |

## How to use it

### VGPR staging pattern
```cpp
// Load to VGPRs (async — returns when data arrives)
float4 staged = *reinterpret_cast<float4*>(global_ptr + offset);
s_waitcnt vmcnt(0);  // wait for load
// Write to LDS
lds_tile[local_offset] = staged;  // ds_write
s_waitcnt lgkmcnt(0);  // wait for LDS write
s_barrier();  // sync workgroup
// Now compute from LDS
```

### buffer_load_lds (CDNA3+)
```
buffer_load_lds loads directly from global memory into LDS without
staging through VGPRs. Saves register pressure.

Constraints:
  - Fixed LDS offset per wavefront (set via M0 register)
  - All lanes load to the same LDS region
  - Limited to 1/2/4 dword loads per lane

// In inline assembly:
asm volatile(
    "s_mov_b32 m0, %0\n"
    "buffer_load_dword off, %1, 0 lds"
    :: "s"(lds_offset), "s"(buffer_desc)
    : "memory"
);
```

### Software pipelining (double buffer)
```
Prologue: prefetch tile 0 into LDS_A
Loop iteration i:
  1. Start prefetch of tile i+1 into LDS_B
  2. s_barrier + compute on tile i from LDS_A
  3. Swap LDS_A ↔ LDS_B
Epilogue: compute on last tile

Cost: 2× LDS allocation (32KB → only 1 workgroup per CU if 64KB total)
Benefit: near-zero memory idle time
```

### s_waitcnt for pipelining
```
DON'T: s_waitcnt vmcnt(0) after every load (serializes pipeline)
DO:    s_waitcnt vmcnt(N) where N = loads_in_flight - loads_needed_now

Example with 4 in-flight loads, need oldest:
  global_load v0, ...  // load 0
  global_load v1, ...  // load 1
  global_load v2, ...  // load 2
  global_load v3, ...  // load 3
  s_waitcnt vmcnt(3)   // wait for load 0 only (3 still outstanding)
  use v0               // safe to use load 0
```

## Pitfalls

1. **Forgetting s_barrier between LDS write and read (different waves)**: race condition.
2. **Double-buffer halves available LDS**: 64KB → 2 × 32KB. May limit workgroup count.
3. **buffer_load_lds M0 register**: must be set correctly or data goes to wrong LDS offset.

## CDNA3 vs CDNA4 differences

| Aspect             | CDNA3              | CDNA4                    |
|--------------------|--------------------|--------------------------|
| buffer_load_lds    | Yes                | Yes                      |
| DME (Data Movement)| No                 | May have HW async copy   |
| Prefetch hint      | No dedicated insn  | Check ISA for new hints  |

## Sources

- rocWMMA programmer's guide: https://rocm.docs.amd.com/projects/rocWMMA/en/latest/conceptual/programmers-guide.html
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 5: Vector Memory
