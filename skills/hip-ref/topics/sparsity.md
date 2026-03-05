# Structured Sparsity for MFMA

## What it is

CDNA3+ matrix cores natively support 2:4 structured sparsity: for every 4 elements
in input matrix A, exactly 2 must be zero. The non-zeros are stored in compressed
format with a metadata index. This delivers 2× MFMA throughput because A is half
the size, so the matrix core processes it twice as fast.

## When you care

- Weight matrices pruned to 2:4 pattern during training
- Inference with sparse models (LLM weight sparsity)
- Understanding peak TFLOPS numbers (sparse vs dense listed separately)

## Key numbers

| Type (with sparsity) | MI300X TFLOPS | MI350X TFLOPS | vs Dense |
|----------------------|---------------|---------------|----------|
| FP16 sparse          | 2,615         | 4,619         | 2×       |
| FP8 sparse           | 5,230         | 9,227         | 2×       |
| FP4 sparse           | N/A           | 18,455*       | 2×       |

*Estimated from 2× dense rate.

### 2:4 pattern
```
For every group of 4 elements, exactly 2 are non-zero:
  [a, 0, b, 0]  ✓
  [0, a, 0, b]  ✓
  [a, b, 0, 0]  ✓
  [a, 0, 0, b]  ✓
  [a, b, c, 0]  ✗ (3 non-zeros)
  [0, 0, 0, 0]  ✗ (0 non-zeros)
```

## How to use it

### Compressed format
```
Dense A (8 elements): [a0, 0, a2, 0, a4, a5, 0, 0]
Compressed values:    [a0, a2, a4, a5]  (4 non-zeros, half size)
Metadata indices:     [0, 2, 0, 1]     (2-bit indices: which 2 of 4 are non-zero)

Metadata encoding: 2 bits per non-zero element, packed into VGPRs.
  Index 0 = position 0, 1 = position 1, 2 = position 2, 3 = position 3
```

### Sparse MFMA instructions
```
v_mfma_*_*_*_*_sparse variants (check ISA ref for full list)

The compressed A matrix + metadata are loaded into VGPRs.
B matrix is dense (unchanged).
Hardware decompresses A during MFMA execution.
```

### Producing 2:4 sparse weights
```
1. Train with unstructured sparsity or dense
2. Apply 2:4 pruning (keep 2 largest magnitudes per group of 4)
3. Fine-tune to recover accuracy
4. Convert to compressed format with metadata

Libraries: NVIDIA ASP (adaptable for AMD), custom pruning scripts.
Not all layers tolerate 2:4 sparsity equally — attention QKV projections
are more sensitive than FFN layers.
```

## Pitfalls

1. **Dynamic data can't be sparse**: attention scores (Q×K^T output) are not
   2:4 structured → can't use sparse MFMA for softmax(Q×K^T)×V.
2. **Accuracy impact**: 2:4 pruning removes 50% of weights. Some models lose
   significant accuracy without careful fine-tuning.
3. **Metadata overhead**: metadata indices consume VGPRs and bandwidth.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 7 (sparse MFMA variants)
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 7
