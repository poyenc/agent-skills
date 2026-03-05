# Buffer vs Flat Memory Instructions

## What it is

Three global memory instruction families: buffer_load/store (SGPR descriptor + VGPR offset),
global_load/store (64-bit VGPR address), and flat_load/store (any address space). Each has
different performance characteristics, addressing modes, and bounds-checking behavior.

## When you care

- Choosing instruction type for tiled matrix loads (FMHA Q/K/V)
- Need out-of-bounds safety (padding behavior)
- Using buffer_load_lds for async global→LDS copies
- Optimizing addressing overhead (SGPR descriptor setup vs per-lane addresses)

## Key numbers

| Instruction family | Address source    | Bounds check      | Throughput | OOB behavior         |
|-------------------|-------------------|-------------------|------------|----------------------|
| buffer_load/store | SGPR desc + VGPR  | Yes (returns 0)   | Full       | Returns 0 for reads  |
| global_load/store | 64-bit VGPR       | No (may fault)    | Full       | Page fault           |
| flat_load/store   | 64-bit VGPR       | No (may fault)    | Slightly lower | Resolves addr space |

## How to use it

### buffer_load advantages
```
1. Bounds checking: OOB reads return 0 (perfect for FMHA padding)
2. Swizzled addressing: hardware 2D address remapping
3. SGPR base + VGPR offset: saves VGPRs (base in SGPRs)
4. oob_select: control what OOB returns (0, or wrap)
5. buffer_load_lds: direct global→LDS without VGPR staging

Buffer resource descriptor (4 SGPRs):
  s[0:1] = base_address (48 bits)
  s[2]   = stride, num_records
  s[3]   = flags (swizzle, oob_select, format)
```

### global_load advantages
```
1. Simple: 64-bit address per lane, no descriptor setup
2. Good for irregular/pointer-chasing access patterns
3. Supports all cache policies (GLC, SLC, DLC)
```

### flat_load: use sparingly
```
Can address ANY memory space (global, LDS, scratch) based on address range.
Hardware must resolve which space at runtime → slight performance penalty.
Only use when address space is truly unknown (e.g., generic pointer from host).
```

### FMHA recommendation
```
Q/K/V tile loads: buffer_load (bounds checking for sequence padding)
Output stores: buffer_store or global_store (both work)
LDS-staged loads: buffer_load_lds (CDNA3+, saves VGPRs)
```

## Pitfalls

1. **flat_load when space is known**: Using flat instead of global/buffer adds overhead.
2. **Buffer descriptor setup cost**: 4 SGPRs per descriptor. Multiple buffers eat SGPRs.
3. **buffer_load_lds constraints**: all lanes write to same LDS region, limited flexibility.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Ch.5 (Vector Memory), Ch.8 (Flat Memory)
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Ch.5, Ch.8
