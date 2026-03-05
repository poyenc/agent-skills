# MFMA Register Layout & Matrix Instructions

## What it is

Matrix Fused Multiply-Add (MFMA) instructions are the core compute primitive on
CDNA architectures. Each instruction performs `D = A × B + C` where A, B, C, D are
matrices distributed across the 64 lanes of a wavefront. The lane-to-register
mapping determines how matrix elements are laid out in VGPRs and AGPRs.

## When you care

- Writing MFMA-based GEMM or FMHA kernels with explicit register tiling
- Choosing tile sizes (32×32 vs 16×16) to balance compute throughput and register pressure
- Understanding how data must be arranged in VGPRs before issuing an MFMA
- Using broadcast flags (cbsz/abid/blgp) to reduce register pressure for shared operands
- Comparing CDNA3 vs CDNA4 instruction variants for new data types

## Key numbers

### MFMA instructions — CDNA3 (gfx940/942)

| Instruction                        | M×N×K  | A type   | B type   | D type | Cycles | ArchVGPRs (A,B) | AGPRs (C,D) |
|------------------------------------|--------|----------|----------|--------|--------|------------------|--------------|
| v_mfma_f32_32x32x8_f16            | 32×32×8  | FP16   | FP16   | FP32   | 64     | 4+4              | 16           |
| v_mfma_f32_16x16x16_f16           | 16×16×16 | FP16   | FP16   | FP32   | 32     | 4+4              | 4            |
| v_mfma_f32_32x32x8_bf16           | 32×32×8  | BF16   | BF16   | FP32   | 64     | 4+4              | 16           |
| v_mfma_f32_16x16x16_bf16          | 16×16×16 | BF16   | BF16   | FP32   | 32     | 4+4              | 4            |
| v_mfma_f32_32x32x16_f8f8          | 32×32×16 | FP8    | FP8    | FP32   | 64     | 4+4              | 16           |
| v_mfma_f32_16x16x32_f8f8          | 16×16×32 | FP8    | FP8    | FP32   | 32     | 4+4              | 4            |
| v_mfma_f32_32x32x4_2b_f16         | 32×32×4  | FP16   | FP16   | FP32   | 64     | 2+2              | 16           |
| v_mfma_f64_16x16x4_f64            | 16×16×4  | FP64   | FP64   | FP64   | 64     | 4+4              | 8            |
| v_mfma_i32_32x32x16_i8            | 32×32×16 | INT8   | INT8   | INT32  | 64     | 4+4              | 16           |
| v_mfma_i32_16x16x32_i8            | 16×16×32 | INT8   | INT8   | INT32  | 32     | 4+4              | 4            |

### CDNA4 (gfx950) new instructions

| Instruction                          | M×N×K    | A type | B type | D type | Notes                      |
|--------------------------------------|----------|--------|--------|--------|----------------------------|
| v_mfma_f32_32x32x16_f16             | 32×32×16 | FP16   | FP16   | FP32   | Doubled K vs CDNA3 (2× throughput) |
| v_mfma_f32_32x32x32_f8f8            | 32×32×32 | FP8    | FP8    | FP32   | Doubled K vs CDNA3         |
| v_mfma_f32_32x32x*_f4               | 32×32×*  | FP4    | FP4    | FP32   | New in CDNA4               |
| v_mfma_f32_32x32x*_f6               | 32×32×*  | FP6    | FP6    | FP32   | New in CDNA4               |
| v_mfma_f32_32x32x*_mxfp8            | 32×32×*  | MXFP8  | MXFP8  | FP32   | Block-scaled FP8           |
| v_mfma_f32_32x32x*_mxfp4            | 32×32×*  | MXFP4  | MXFP4  | FP32   | Block-scaled FP4           |

*Exact K dimensions for FP4/FP6/MXFP — check ISA reference for final values.*

### Throughput scaling

| Data type | CDNA3 MI300X peak | CDNA4 MI350X peak | Scaling |
|-----------|-------------------|-------------------|---------|
| FP16      | 1,307 TFLOPS      | 2,310 TFLOPS      | 1.77×   |
| FP8       | 2,615 TFLOPS      | 4,614 TFLOPS      | 1.76×   |
| FP4       | N/A               | 9,228 TFLOPS      | —       |
| FP64      | 163 TFLOPS (matrix)| 72 TFLOPS (matrix)| 0.44× ↓|

Note: CDNA4 trades FP64 matrix throughput for massively higher low-precision throughput.

## How to use it

### Lane-to-register mapping (32×32 MFMA output)

```
v_mfma_f32_32x32x8_f16 produces 16 FP32 output values per lane.
These 16 values are stored in a[0:15] (16 AGPRs per lane).

For a 32×32 output matrix D[row][col]:
  - 64 lanes are organized into 4 groups of 16 lanes
  - Each group of 16 lanes covers 16 columns of one 8-row block
  - The 4 groups cover 4 blocks of 8 rows = 32 rows total

Lane mapping:
  lane_id = thread within wave (0-63)
  group = lane_id / 16        (0-3, selects 8-row block)
  col = lane_id % 16          (column within 32-col output, repeated 2×)

  a[k] holds D[group*8 + k%8][col + (k/8)*16]

  So lane 5 (group=0, col=5):
    a[0] = D[0][5], a[1] = D[1][5], ... a[7] = D[7][5]
    a[8] = D[0][21], a[9] = D[1][21], ... a[15] = D[7][21]
```

### Input register layout (A matrix for 32×32×8 FP16)

```
A is 32×8 FP16. Each FP16 pair is packed into a 32-bit VGPR.
4 VGPRs per lane hold the A matrix:
  v[0] = A[lane_group*8 + 0..1][lane_col_offset]  (packed FP16)
  v[1] = A[lane_group*8 + 2..3][lane_col_offset]
  v[2] = A[lane_group*8 + 4..5][lane_col_offset]
  v[3] = A[lane_group*8 + 6..7][lane_col_offset]
```

### Using the AMD Matrix Instruction Calculator

```bash
# Install and run:
git clone https://github.com/ROCm/amd_matrix_instruction_calculator
cd amd_matrix_instruction_calculator
python3 matrix_calculator.py --architecture cdna3 \
    --instruction v_mfma_f32_32x32x8_f16 --detail-instruction

# Shows exact lane→register→matrix-element mapping
```

### Broadcast flags: cbsz, abid, blgp

```
MFMA supports broadcasting subsets of A or B:
  cbsz (2 bits): Controls A matrix broadcast
    0 = no broadcast (normal)
    1 = broadcast 1/2 of A (use abid to select which half)
    2 = broadcast 1/4 of A

  abid (4 bits): Selects which sub-block to broadcast when cbsz > 0

  blgp (3 bits): Controls B matrix broadcast (same concept)

Use case: when multiple MFMA operations share the same A or B matrix,
broadcast avoids loading duplicates into VGPRs.
```

### MFMA in HIP (using intrinsics)

```cpp
#include <hip/hip_runtime.h>

// FP16 32×32×8:
typedef _Float16 half4 __attribute__((ext_vector_type(4)));
typedef float float16 __attribute__((ext_vector_type(16)));

float16 d = __builtin_amdgcn_mfma_f32_32x32x8f16(a, b, c, 0, 0, 0);
//                                                         cbsz abid blgp

// FP8 32×32×16 (CDNA3):
// Use __builtin_amdgcn_mfma_f32_32x32x16_fp8_fp8(a, b, c, 0, 0, 0);
```

### Inline assembly for MFMA

```cpp
// When you need precise register control:
asm volatile(
    "v_mfma_f32_32x32x8_f16 %0, %1, %2, %3"
    : "=a"(d)          // output: AGPR (accumulator)
    : "v"(a),          // input A: VGPR
      "v"(b),          // input B: VGPR
      "a"(c)           // input C: AGPR (accumulator)
);
// Note: "a" constraint = AGPR, "v" = VGPR
```

## Pitfalls

1. **AGPR extraction cost (CDNA3)**: After MFMA, results are in AGPRs. To store to
   memory or use in VALU, you need `v_accvgpr_read_b32` (1 VALU cycle each).
   For 16 accumulators: 16 VALU cycles overhead per MFMA.

2. **Lane mapping confusion**: The layout is NOT row-major or column-major in any
   simple sense. Use the matrix instruction calculator to verify your mapping.

3. **Wrong data type packing**: FP16 inputs must be packed 2 per VGPR (low/high).
   Wrong packing order produces silently wrong results.

4. **Forgetting accumulator initialization**: C input must be initialized before
   first MFMA. Use `v_accvgpr_write_b32 a[N], 0` or load from memory.

5. **Register pressure from large tiles**: 32×32 MFMA uses 16 AGPRs for output
   + 4+4 VGPRs for inputs. Multiple tiles multiply this.

## CDNA3 vs CDNA4 differences

| Aspect                  | CDNA3 (gfx940/942)              | CDNA4 (gfx950)                      |
|-------------------------|----------------------------------|--------------------------------------|
| Max K dimension (FP16)  | 8                                | 16 (doubled throughput)              |
| Max K dimension (FP8)   | 16                               | 32 (doubled throughput)              |
| FP4/FP6/MXFP support   | No                               | Yes (new instruction variants)       |
| Accumulator registers   | AGPRs (separate file)            | May use unified ArchVGPR file        |
| FP64 matrix rate        | Full rate (= FP32 matrix)        | Half rate                            |
| Block scaling (MXFP)    | No                               | Yes (shared exponent per 32 elements)|
| Stochastic rounding     | No                               | Yes (for FP8 conversion)             |

## Sources

- Matrix cores on CDNA3/4: https://rocm.blogs.amd.com/software-tools-optimization/matrix-cores-cdna/README.html
- Matrix cores (original): https://rocm.blogs.amd.com/software-tools-optimization/matrix-cores/README.html
- Matrix instruction calculator: https://github.com/ROCm/amd_matrix_instruction_calculator
- GPUOpen Lab Notes on matrix cores: https://gpuopen.com/learn/amd-lab-notes/amd-lab-notes-matrix-cores-readme/
- CDNA3 ISA reference: `pdfs/cdna3-isa-reference.pdf` — Chapter 7: Matrix Fused Multiply-Add
- CDNA4 ISA reference: `pdfs/cdna4-isa-reference.pdf` — Chapter 7
