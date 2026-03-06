# LDS Bank Conflicts

## What it is

LDS (Local Data Share) is 64KB per CU on CDNA3 (128KB on CDNA4), organized as 32 banks × 4 bytes per bank.
A bank conflict occurs when 2+ lanes in the same cycle access different addresses
mapping to the same bank. Conflicts serialize and can 2-32× degrade LDS throughput.

## When you care

- FMHA: storing Q tiles in LDS for dot products with K
- Any tiled GEMM using LDS for A/B tile staging
- Softmax: storing partial sums for cross-wave reduction
- Any kernel where omniperf shows SQ_LDS_BANK_CONFLICT > 0

## Key numbers

| Property        | CDNA3           | CDNA4            |
|-----------------|-----------------|------------------|
| LDS per CU      | 64 KB           | **128 KB**       |
| Banks            | 32              | 32               |
| Bank width       | 4 bytes         | 4 bytes          |
| Bank mapping     | (addr/4) % 32   | (addr/4) % 32   |
| Broadcast        | Same-addr = free | Same-addr = free|
| Max conflict     | 32-way          | 32-way           |
| ds_read_tr_*    | B64, B128       | B64, B128 + **B64_TR_B4/B8/B16, B96_TR_B6** |

## How to use it

### Bank mapping
```
bank = (byte_address / 4) % 32

Example: float array at LDS offset 0
  &arr[0]  → bank 0   (addr=0,  0/4%32=0)
  &arr[1]  → bank 1   (addr=4,  4/4%32=1)
  &arr[31] → bank 31  (addr=124, 124/4%32=31)
  &arr[32] → bank 0   (addr=128, conflict with arr[0])
```

### Conflict-free patterns
```
Stride-1 access (sequential): each lane hits a different bank → no conflicts
  lane i accesses arr[base + i]  → banks 0,1,2,...,31 → perfect

Stride-32 access (column of 32-wide matrix): all lanes hit SAME bank → 32-way conflict!
  lane i accesses arr[i * 32]  → all map to bank 0 → serialized

Broadcast: all lanes access SAME address → free (hardware broadcasts)
```

### Padding to avoid conflicts
```cpp
// Problem: 32-wide matrix, column access = 32-way conflict
__shared__ float tile[32][32];    // column access: tile[row][0] all bank 0

// Solution: pad inner dimension by 1
__shared__ float tile[32][33];    // column access: tile[row][0] hits bank 0,1,2,...
// Bank = (row * 33 * 4 / 4) % 32 = (row * 33) % 32 → different banks!

// For FP16 (2 bytes): pad by 2 elements
__shared__ half tile[32][34];     // 34 × 2 = 68 bytes per row
```

### XOR preshuffle (advanced, used in CK)
```
Transform address before LDS access to spread banks:
  new_offset = original_offset ^ (lane_id * stride)

This distributes accesses across banks even for strided patterns.
Used in composable_kernel for conflict-free MFMA data staging.
```

### LDS instruction variants
```
ds_read_b32:  1 element (4B) per lane per cycle
ds_read_b64:  2 elements (8B) per lane — splits into 2 bank accesses
ds_read_b128: 4 elements (16B) per lane — splits into 4 bank accesses

ds_read_b128 issues fewer instructions for sequential access but has
the same bank conflict behavior (each sub-access checks banks separately).
For sequential access: prefer ds_read_b128 (fewer instructions, same BW).
```

## Pitfalls

1. **Column access in 32-wide tiles**: Classic worst case. Always pad to 33.
2. **FP16 with 32-element rows**: Each FP16 is 2 bytes. 32 × 2 = 64 bytes = 16 banks.
   Still need padding — pad to 34 elements (68 bytes) to avoid period-16 conflicts.
3. **Padding wastes LDS**: 32→33 wastes 3% LDS. For tight LDS budgets, use XOR preshuffle.
4. **ds_read_b128 doesn't fix conflicts**: It just reduces instruction count. If the
   addresses conflict, each sub-read still stalls.
5. **Measuring conflicts**: Use omniperf counter `SQ_LDS_BANK_CONFLICT`. Non-zero = problem.

## CDNA3 vs CDNA4 differences

| Aspect               | CDNA3 (gfx940/942)          | CDNA4 (gfx950)                      |
|-----------------------|-----------------------------|-------------------------------------|
| LDS per CU            | 64 KB                      | **128 KB** (2× increase)            |
| Bank count × width    | 32 × 4B                    | 32 × 4B (same)                      |
| Bank conflict rules   | (addr/4) % 32              | Same                                |
| Transpose reads       | ds_read_tr_b64, ds_read_tr_b128 | Same + **4 new ds_read_*_tr_* variants** |
| GDS / GWS             | Present                    | **Removed**                         |

**CDNA4 new LDS instructions** (transpose reads for MFMA data staging):
- `ds_read_b64_tr_b4` — read 64B with 4-bit element transpose
- `ds_read_b96_tr_b6` — read 96B with 6-bit element transpose
- `ds_read_b64_tr_b8` — read 64B with 8-bit element transpose
- `ds_read_b64_tr_b16` — read 64B with 16-bit element transpose

These enable direct transposed reads from LDS into VGPRs in the layout expected
by MFMA, avoiding extra shuffle/permute instructions. Particularly useful for
narrow-format MFMA (FP4/FP6/FP8) where data layout transformations are expensive.

**128 KB LDS** means CDNA4 can hold larger tiles, enabling more data reuse and
relaxing LDS-limited occupancy constraints (see occupancy-register-pressure topic).

## Sources

- CK LDS bank conflicts: https://rocm.docs.amd.com/projects/composable_kernel/en/latest/conceptual/ck_tile/hardware/lds_bank_conflicts.html
- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 6: Data Share Operations
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 11 (LDS), Section 11.4 (MFMA Transpose Load)
- HIP hardware implementation: https://rocm.docs.amd.com/projects/HIP/en/latest/understand/hardware_implementation.html
