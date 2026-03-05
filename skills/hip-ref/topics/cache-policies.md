# Cache Policies (GLC/SLC/DLC)

## What it is

VMEM instructions have cache policy bits that control how data flows through
the L1 and L2 caches. GLC bypasses L1, SLC marks data as non-temporal in L2,
DLC controls device-level coherence. Proper use avoids cache pollution from
streaming data while keeping reused data cached.

## When you care

- Streaming large K/V sequences (don't pollute L2 with one-shot data)
- Multi-CU coherence (shared accumulation buffers)
- Controlling L2 eviction policy for working set management

## Key numbers

| Bit | Name | Effect on read                    | Effect on write              |
|-----|------|-----------------------------------|------------------------------|
| GLC | Globally Coherent | Bypass L1, read from L2 | Invalidate L1 line    |
| SLC | System Level Coherent | Non-temporal in L2   | Non-temporal in L2     |
| DLC | Device Level Coherent | Controls L1 caching  | Controls L1 behavior   |

### Combinations

| GLC | SLC | Behavior                                        | Use case                    |
|-----|-----|-------------------------------------------------|-----------------------------|
| 0   | 0   | Cache in L1 + L2 (default)                      | Reused data (Q tile)        |
| 1   | 0   | Bypass L1, cache in L2                           | Inter-CU shared data        |
| 0   | 1   | Cache in L1, streaming in L2                     | Locally reused, globally one-shot |
| 1   | 1   | Bypass L1, streaming L2                           | One-shot global reads (K/V stream) |

## How to use it

### In HIP code
```cpp
// Non-temporal load (GLC|SLC equivalent):
float val = __builtin_nontemporal_load(ptr);

// Non-temporal store:
__builtin_nontemporal_store(val, ptr);

// For precise control, use inline assembly:
asm volatile("global_load_dword %0, %1, off glc slc"
    : "=v"(val) : "v"(addr) : "memory");
```

### FMHA pattern
```
Q tile (reused across all K/V tiles): default (cache in L1+L2)
K/V tiles (streamed once): GLC|SLC (bypass L1, non-temporal L2)
Output accumulator: default writes
```

## Pitfalls

1. **Over-using SLC**: marking everything non-temporal defeats caching entirely.
2. **Cross-XCD coherence**: GLC ensures L1 coherence but L2 is per-XCD. For
   cross-XCD visibility, use system-scope atomics or fences.
3. **Cache flag syntax varies**: buffer_load uses GLC/SLC directly; global_load
   encoding may differ. Check ISA reference for your instruction family.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 5: Vector Memory
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 5
