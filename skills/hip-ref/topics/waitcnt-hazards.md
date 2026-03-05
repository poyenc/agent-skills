# s_waitcnt & Hazard Management

## What it is

AMD GPUs do NOT hardware-interlock between VMEM loads and VALU usage. You MUST
insert `s_waitcnt` instructions to ensure data is ready before use. The compiler
handles this automatically for HIP code, but inline assembly and software pipelining
require manual management.

## When you care

- Writing inline assembly with VMEM loads
- Software pipelining (keeping multiple loads in flight)
- MFMA accumulator hazards (reading AGPRs before MFMA completes)
- Workgroup synchronization (s_barrier)

## Key counters

| Counter    | Tracks                                  | Range  | Instruction          |
|------------|-----------------------------------------|--------|----------------------|
| vmcnt      | Outstanding VMEM loads/stores           | 0-63   | s_waitcnt vmcnt(N)   |
| lgkmcnt    | Outstanding LDS + SMEM operations       | 0-63   | s_waitcnt lgkmcnt(N) |
| expcnt     | Outstanding exports/GDS                 | 0-7    | s_waitcnt expcnt(N)  |
| vscnt      | Outstanding vector stores (CDNA3+)      | 0-63   | s_waitcnt_vscnt null,N |

`s_waitcnt vmcnt(N)` means: wait until outstanding VMEM ops ≤ N.
`s_waitcnt vmcnt(0)` = wait for ALL loads/stores to complete.

## How to use it

### Basic pattern
```cpp
// Load then use:
asm volatile("global_load_dword %0, %1, off" : "=v"(val) : "v"(addr));
asm volatile("s_waitcnt vmcnt(0)" ::: "memory");  // wait for load
asm volatile("v_add_f32 %0, %0, %0" : "+v"(val)); // safe to use val
```

### Software pipelining pattern
```
// Issue 4 loads, consume oldest first:
global_load v0, ...  // vmcnt increments to 1
global_load v1, ...  // vmcnt = 2
global_load v2, ...  // vmcnt = 3
global_load v3, ...  // vmcnt = 4

s_waitcnt vmcnt(3)   // wait for v0 (oldest, vmcnt drops to 3)
use(v0)              // safe

// ... do more work ...

s_waitcnt vmcnt(2)   // wait for v1
use(v1)              // safe

// Key: vmcnt(N) means N loads are STILL outstanding, not N have completed.
// So vmcnt(3) with 4 total = oldest 1 is done.
```

### LDS synchronization
```cpp
// Within a wave: lgkmcnt
asm volatile("ds_write_b32 %0, %1" :: "v"(lds_addr), "v"(val));
asm volatile("s_waitcnt lgkmcnt(0)" ::: "memory");
asm volatile("ds_read_b32 %0, %1" : "=v"(result) : "v"(lds_addr));

// Across waves in a workgroup: s_barrier
asm volatile("s_waitcnt lgkmcnt(0)" ::: "memory");
asm volatile("s_barrier" ::: "memory");
// All waves have reached barrier and their LDS writes are visible
```

### MFMA hazards
```
After MFMA, accumulator (AGPR) results need time to be ready:
  v_mfma_f32_32x32x8_f16 a[0:15], ...  // 64 cycles
  // Cannot read a[0:15] until MFMA completes
  // Compiler inserts s_nop or arranges other instructions to fill gap

In inline asm: ensure ≥64 instructions between MFMA issue and
v_accvgpr_read, or use s_waitcnt for MFMA completion.
```

### Memory fences (ordering, not waiting)
```cpp
__threadfence_block();  // workgroup scope — orders writes visible within block
__threadfence();        // device scope — orders writes visible to all CUs

// Fences ensure ORDERING, not completion. Combine with s_waitcnt for both.
```

## Pitfalls

1. **Missing waitcnt = undefined behavior**: using VMEM result without waitcnt
   reads garbage. No hardware interlock will save you.
2. **vmcnt(0) everywhere = serialized pipeline**: kills performance. Use vmcnt(N>0)
   to keep loads in flight.
3. **lgkmcnt covers both LDS and SMEM**: a large lgkmcnt value might be from
   SMEM loads, not just LDS. They share the counter.
4. **s_barrier without lgkmcnt(0)**: barrier ensures all waves reach it, but
   doesn't guarantee their LDS writes are committed. Add `s_waitcnt lgkmcnt(0)`
   BEFORE `s_barrier`.
5. **vscnt is separate from vmcnt (CDNA3+)**: vector stores have their own counter.
   `s_waitcnt vmcnt(0)` does NOT wait for stores. Use `s_waitcnt_vscnt null, 0`.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Ch.2 (pipeline model), Ch.3 (scalar instructions)
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Ch.2, Ch.3
