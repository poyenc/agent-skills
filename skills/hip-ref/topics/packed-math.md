# Packed Math (v_pk_*)

## What it is

Packed math instructions operate on 2× FP16 or 2× BF16 values packed into a single
32-bit VGPR, delivering 2× throughput per lane per cycle compared to scalar FP16.
CDNA4 adds a large family of packed scaled conversion instructions (v_cvt_scalef32_*).

## When you care

- FMHA softmax: exp, sum, scale operations on FP16 data
- Any elementwise FP16/BF16 computation in hot loops
- Maximizing VALU throughput for non-MFMA work

## Key numbers

| Operation      | Scalar FP16      | Packed FP16 (v_pk_*) | Speedup |
|----------------|------------------|----------------------|---------|
| FMA            | 1 FLOP/lane/cy   | 2 FLOPs/lane/cy      | 2×      |
| Add/Mul        | 1 FLOP/lane/cy   | 2 FLOPs/lane/cy      | 2×      |
| Min/Max        | 1 op/lane/cy     | 2 ops/lane/cy        | 2×      |

## How to use it

### HIP half2 intrinsics
```cpp
#include <hip/hip_fp16.h>

__half2 a = make_half2(1.0f, 2.0f);
__half2 b = make_half2(3.0f, 4.0f);

__half2 c = __hadd2(a, b);    // packed add → v_pk_add_f16
__half2 d = __hmul2(a, b);    // packed mul → v_pk_mul_f16
__half2 e = __hfma2(a, b, c); // packed FMA → v_pk_fma_f16
```

### Key instructions
```
v_pk_fma_f16:  c = a*b + c (2 FP16 FMAs)
v_pk_add_f16:  c = a + b
v_pk_mul_f16:  c = a * b
v_pk_max_f16:  c = max(a, b)
v_pk_min_f16:  c = min(a, b)

BF16 equivalents also available on CDNA3+.

CDNA4 additions:
  v_cvt_scalef32_pk_*: ~36 new packed conversion instructions with scale factor
    - Convert between FP4, FP6, FP8, BF8, FP16, BF16, FP32 packed formats
    - Integrated scale factor (FP32) applied during conversion
    - Examples: v_cvt_scalef32_pk_fp8_f32, v_cvt_scalef32_pk_f16_fp4
  v_dot2c_f32_bf16: BF16 dot product in compact VOP2 encoding (new)
    - CDNA3 only had v_dot2c_f32_f16 (FP16 variant)
```

### Getting compiler to emit packed math
```cpp
// Use half2 types and operations consistently
// Compiler auto-vectorizes to v_pk_* when:
//   1. Two adjacent FP16 values are aligned to 32-bit boundary
//   2. Same operation is applied to both halves
//   3. No data dependencies between the two halves

// Ensure alignment:
__half2* aligned_ptr = reinterpret_cast<__half2*>(fp16_array);
__half2 packed = aligned_ptr[i];  // loads 2 FP16 in one VGPR
```

## Pitfalls

1. **Mixing FP32 and FP16 breaks packing**: if your code converts to FP32 for
   intermediate computation, those FP32 ops won't be packed. Keep hot paths in FP16.
2. **Unaligned half2 loads**: misaligned access prevents packing. Ensure arrays
   are 4-byte aligned.
3. **VOPD does not exist on CDNA**: VOPD (dual-issue encoding) is an RDNA3+ feature
   only. Neither CDNA3 nor CDNA4 support VOPD.

## CDNA3 vs CDNA4 differences

| Aspect                    | CDNA3 (gfx940/942)           | CDNA4 (gfx950)                        |
|---------------------------|------------------------------|---------------------------------------|
| v_pk_add/mul/fma_f16      | Yes                          | Yes (identical)                       |
| v_pk_add/mul/fma_f32      | Yes                          | Yes (identical)                       |
| v_dot2c_f32_f16 (VOP2)   | Yes                          | Yes                                   |
| v_dot2c_f32_bf16 (VOP2)  | **No**                       | **New** — BF16 dot product            |
| v_cvt_scalef32_pk_*      | **No**                       | **New** — ~36 scaled convert instructions |
| VOPD (dual-issue)         | No                           | No (RDNA-only feature)               |

**CDNA4's key packed-math addition** is the v_cvt_scalef32_pk_* family for converting
between narrow formats (FP4/FP6/FP8/BF8) and wider formats (FP16/BF16/FP32) with an
integrated FP32 scale factor. These are essential for MXFP block-scaled inference
where data is stored in narrow format with per-block exponents.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 4: Vector ALU (VOP3P encoding)
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 4, Section 6.7.1 (CVT_SCALE)
