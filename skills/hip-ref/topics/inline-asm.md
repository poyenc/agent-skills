# Inline Assembly in HIP

## What it is

HIP supports GCC-style inline assembly to emit specific AMDGCN ISA instructions
directly from device code. This gives precise control over instruction selection,
register allocation, and pipeline management — essential for s_waitcnt, MFMA,
ds_permute, and cache-flagged loads.

## When you care

- Fine-grained s_waitcnt control (software pipelining)
- MFMA with specific register allocation
- ds_permute/ds_bpermute for cross-lane ops
- Cache-flagged loads (GLC/SLC bits)
- Performance-critical inner loops where compiler output is suboptimal

## How to use it

### Basic syntax
```cpp
asm volatile("instruction %0, %1" : "=v"(output) : "v"(input));
//            ^instruction         ^output         ^input
//                                 "=v" = write to VGPR
//                                                 "v" = read from VGPR
```

### Register constraints
```
"v"  — VGPR (vector register)
"s"  — SGPR (scalar register)
"a"  — AGPR (accumulation register)
"={v0}" — specific VGPR v0
"={s0}" — specific SGPR s0
"n"  — immediate integer constant
"I"  — inline constant (fits in instruction encoding)
```

### Common patterns

```cpp
// s_waitcnt:
asm volatile("s_waitcnt vmcnt(0) lgkmcnt(0)" ::: "memory");
asm volatile("s_waitcnt vmcnt(3)" ::: "memory");  // keep 3 loads in flight

// s_barrier:
asm volatile("s_barrier" ::: "memory");

// MFMA (FP16 32×32×8):
typedef _Float16 half4 __attribute__((ext_vector_type(4)));
typedef float float16 __attribute__((ext_vector_type(16)));
float16 d;
asm volatile("v_mfma_f32_32x32x8_f16 %0, %1, %2, %3"
    : "=a"(d) : "v"(a), "v"(b), "a"(c));

// ds_permute (cross-lane gather):
int result;
asm volatile("ds_permute_b32 %0, %1, %2"
    : "=v"(result) : "v"(src_lane_id * 4), "v"(value));

// Global load with cache flags:
float val;
asm volatile("global_load_dword %0, %1, off glc slc"
    : "=v"(val) : "v"(addr) : "memory");

// v_readfirstlane (VGPR lane 0 → SGPR):
int scalar_val;
asm volatile("v_readfirstlane_b32 %0, %1"
    : "=s"(scalar_val) : "v"(vector_val));
```

## Pitfalls

1. **Forgetting memory clobber**: `"memory"` in clobber list prevents reordering.
   Required for s_waitcnt, barriers, memory loads/stores.
2. **Wrong register constraint**: using `"v"` when instruction expects AGPR (`"a"`)
   causes silent wrong results or assembler error.
3. **volatile is essential**: without it, compiler may eliminate "unused" asm blocks.
4. **Register pressure**: inline asm blocks opaque to register allocator, may cause
   unnecessary spills if many registers are pinned.
5. **No s_waitcnt → undefined behavior**: using VMEM load result without waitcnt
   is a data hazard. Hardware does NOT interlock.

## CDNA3 vs CDNA4 differences

| Aspect                    | CDNA3 (gfx940/942)          | CDNA4 (gfx950)                     |
|---------------------------|-----------------------------|------------------------------------|
| Cache flag syntax         | `glc slc dlc`               | **`scope:X th:Y`** (new syntax)    |
| AGPR constraint `"a"`     | Maps to separate AGPR file  | Maps to unified VGPR file          |
| v_accvgpr_read/write      | Required (1 VALU cycle)     | No-op (same physical file)         |
| s_set_gpr_idx_mode        | Available                   | **Removed** — will not assemble    |
| s_waitcnt expcnt(N)       | Functional                  | **Ignored** (expcnt unused)        |
| New instructions          | —                           | v_permlane16/32_swap_b32, v_prng_b32, v_cvt_scalef32_*, ds_read_*_tr_* |
| MFMA encoding             | VOP3P-MAI                   | Extended VOP3P-MAI with SCALEF32   |

**Inline asm migration for gfx950**:
```cpp
// CDNA3 cache-flagged load:
asm volatile("global_load_dword %0, %1, off glc slc"
    : "=v"(val) : "v"(addr) : "memory");

// CDNA4 equivalent:
asm volatile("global_load_dword %0, %1, off scope:SCOPE_DEV th:TH_LOAD_NT"
    : "=v"(val) : "v"(addr) : "memory");

// CDNA4 permlane swap (new):
asm volatile("v_permlane32_swap_b32 %0, %1"
    : "+v"(vdst) : "v"(src0));
```

## Sources

- HIP kernel language: https://rocm.docs.amd.com/projects/HIP/en/develop/reference/kernel_language.html
- Art of AMDGCN assembly: https://gpuopen.com/learn/amdgcn-assembly/
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf`
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf`
