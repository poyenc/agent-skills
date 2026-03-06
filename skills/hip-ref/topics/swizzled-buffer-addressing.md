# Swizzled Buffer Addressing

## What it is

Buffer load/store instructions support a swizzle mode that remaps addresses via
XOR operations on address bits. This transforms sequential or strided access patterns
into ones that better distribute across cache lines and reduce bank conflicts, useful
for loading 2D matrix tiles from global memory.

## When you care

- Loading 2D tiles where rows have large stride (causes L1 cache set conflicts)
- Reducing VMEM bank conflicts for tiled access patterns
- Advanced buffer addressing for MFMA data layout optimization

## How it works

```
Swizzle mode is set in the buffer resource descriptor (T#, 4 SGPRs):
  - index_stride: stride between consecutive indices
  - element_size: 2, 4, 8, or 16 bytes per element
  - swizzle_enable: activates swizzle remapping

When enabled, address bits are XOR'd based on the index and element size,
spreading accesses across different cache lines.

Effect: a 2D tile load where rows would normally hit the same cache set
instead distributes across multiple sets → fewer cache conflicts.
```

## How to use it

### Setting up buffer descriptor with swizzle
```cpp
// In inline assembly, set up the buffer resource descriptor (T#):
// s[0:1] = base address
// s[2]   = {stride[13:0], num_records[13:0]}
// s[3]   = {flags including swizzle_enable, element_size, index_stride}

// The exact bit layout is in the ISA reference, Chapter 5.
// Most HIP developers use buffer_load intrinsics or compiler-generated
// buffer accesses rather than manual T# setup.
```

### When to use
```
Good candidates:
  - Matrix tile loads with large row stride (>4KB between rows)
  - Patterns where multiple wavefronts access same cache set
  - 2D blocked access patterns (MFMA tile loading)

Not useful for:
  - Sequential (stride-1) access (already optimal)
  - LDS access (has its own bank conflict resolution)
  - Irregular/pointer-chasing patterns
```

## Pitfalls

1. **Incorrect swizzle parameters → wrong data**: very hard to debug since
   data loads succeed but from wrong addresses.
2. **Only works with buffer_load/store**: global_load and flat_load don't support swizzle.
3. **Complexity**: manual T# setup is error-prone. Prefer compiler-managed buffers.
4. **Profile first**: swizzle helps only when cache conflicts are the bottleneck.
   Use omniperf to confirm TCC (L2) conflict counts before adding swizzle.

## CDNA3 vs CDNA4 differences

No significant changes to swizzled buffer addressing between CDNA3 and CDNA4.
The buffer resource descriptor format and swizzle modes are identical. The main
CDNA4 difference affecting buffer instructions is the replacement of GLC/SLC/DLC
cache flags with SCOPE/TH fields (see cache-policies topic).

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 5: Vector Memory Buffer Instructions
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 5
