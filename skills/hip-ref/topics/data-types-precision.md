# Data Types & Precision

## What it is

CDNA architectures support a wide range of numerical formats for MFMA instructions,
from FP64 down to FP4. CDNA4 adds MXFP (Microscaling) formats with block-level
shared exponents. Choosing the right data type trades precision for throughput —
FP8 gives 2× FP16 throughput, FP4 gives 4×.

## When you care

- Choosing precision for FMHA (FP16 vs FP8 for Q/K/V)
- Evaluating CDNA4's new FP4/FP6/MXFP formats for inference
- Understanding accumulation precision (always FP32 for MFMA)
- Implementing mixed-precision training or inference

## Key numbers

### Data type formats

| Type  | Bits | Exponent | Mantissa | Range       | Use case              |
|-------|------|----------|----------|-------------|-----------------------|
| FP64  | 64   | 11       | 52       | ±1.8×10³⁰⁸ | Scientific compute   |
| FP32  | 32   | 8        | 23       | ±3.4×10³⁸  | Accumulation, general|
| FP16  | 16   | 5        | 10       | ±65504      | Training, inference  |
| BF16  | 16   | 8        | 7        | ±3.4×10³⁸  | Training (wider range)|
| FP8 E4M3| 8  | 4        | 3        | ±448        | Inference (precision)|
| FP8 E5M2| 8  | 5        | 2        | ±57344      | Gradients (range)    |
| FP6 E2M3| 6  | 2        | 3        | ±7.5        | CDNA4 MXFP input     |
| FP6 E3M2| 6  | 3        | 2        | ±28         | CDNA4 MXFP input     |
| FP4 E2M1| 4  | 2        | 1        | ±6          | CDNA4 MXFP input     |

### MFMA throughput scaling

| Type   | MI300X TFLOPS | MI350X TFLOPS | Relative to FP16 |
|--------|---------------|---------------|-------------------|
| FP64   | 163 (matrix)  | 72 (matrix)   | 0.12× / 0.03×     |
| FP32   | 163 (matrix)  | 144 (vector)  | 0.12× / 0.06×     |
| FP16   | 1,307         | 2,310         | 1× / 1×           |
| BF16   | 1,307         | 2,310         | 1× / 1×           |
| FP8    | 2,615         | 4,614         | 2× / 2×           |
| FP4    | N/A           | 9,228         | — / 4×            |

### MXFP (Microscaling) format — CDNA4 only

```
Block scaling: 32 elements share one E8M0 scale factor (8-bit exponent only).
Each element is stored in reduced precision (FP8/FP6/FP4).
Effective precision ≈ element bits + shared exponent range.

Memory layout: [scale_0][elem_0..elem_31][scale_1][elem_32..elem_63]...

Benefits:
  - 2-4× less memory than FP16
  - Hardware decode in MFMA pipeline (no software overhead)
  - OCP (Open Compute Platform) standardized
```

## How to use it

### Type mixing in MFMA
```
All MFMA instructions accumulate in FP32 (or INT32 for integer):
  A (FP16) × B (FP16) → D (FP32) accumulator

A and B must be the same type for a given instruction.
But you can chain: FP8 MFMA for main compute, FP16 for residual corrections.
```

### FP8 E4M3 vs E5M2 tradeoff
```
E4M3: more mantissa bits → better precision, narrower range (±448)
  → Use for: weights, activations in forward pass

E5M2: more exponent bits → wider range (±57344), less precision
  → Use for: gradients in backward pass (need range for large/small values)

FMHA recommendation: E4M3 for Q, K, V (precision matters for attention scores)
```

### Stochastic rounding (CDNA4)
```
CDNA4 supports stochastic rounding for FP32→FP8 conversion.
Instead of round-to-nearest, adds random noise before rounding.
Gives unbiased estimates, important for training convergence.
```

## Pitfalls

1. **FP8 overflow in attention scores**: Q×K^T can produce large values before
   softmax. Scale Q by 1/√d_k BEFORE the matmul, not after.
2. **MXFP not backward compatible**: MXFP instructions exist only on CDNA4.
   Code must check architecture at compile time.
3. **FP64 regression on CDNA4**: FP64 matrix throughput is halved vs CDNA3.
   If your kernel needs FP64 MFMA, CDNA3 is faster per-instruction.

## CDNA3 vs CDNA4 differences

| Aspect               | CDNA3                     | CDNA4                        |
|-----------------------|---------------------------|------------------------------|
| FP16/BF16 MFMA       | Yes                       | Yes (doubled K dimension)    |
| FP8 MFMA             | E4M3, E5M2               | E4M3, E5M2, OCP-FP8         |
| FP6 MFMA             | No                        | E2M3, E3M2 (MXFP)           |
| FP4 MFMA             | No                        | E2M1 (MXFP)                 |
| Block scaling (MXFP)  | No                        | Yes (32-element blocks)      |
| Stochastic rounding   | No                        | Yes                          |
| FP64 matrix rate      | Full (= FP32 matrix rate) | Half rate                    |

## Sources

- Matrix cores on CDNA3/4: https://rocm.blogs.amd.com/software-tools-optimization/matrix-cores-cdna/README.html
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 7: MFMA
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 7
- CDNA4 whitepaper: `pdfs/amd-cdna4-whitepaper.pdf`
