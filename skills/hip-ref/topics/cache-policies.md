# Cache Policies (GLC/SLC/DLC → SCOPE/TH)

## What it is

VMEM instructions have cache policy bits that control how data flows through
the L1 and L2 caches. On CDNA3, GLC bypasses L1, SLC marks data as non-temporal
in L2, DLC controls device-level coherence. **CDNA4 replaces GLC/SLC/DLC entirely**
with a new SCOPE + TH (Temporal Hint) system. Proper use avoids cache pollution
from streaming data while keeping reused data cached.

## When you care

- Streaming large K/V sequences (don't pollute L2 with one-shot data)
- Multi-CU coherence (shared accumulation buffers)
- Controlling L2 eviction policy for working set management

## Key numbers

### CDNA3 (gfx940/942): GLC/SLC/DLC bits

| Bit | Name | Effect on read                    | Effect on write              |
|-----|------|-----------------------------------|------------------------------|
| GLC | Globally Coherent | Bypass L1, read from L2 | Invalidate L1 line    |
| SLC | System Level Coherent | Non-temporal in L2   | Non-temporal in L2     |
| DLC | Device Level Coherent | Controls L1 caching  | Controls L1 behavior   |

#### Combinations (CDNA3)

| GLC | SLC | Behavior                                        | Use case                    |
|-----|-----|-------------------------------------------------|-----------------------------|
| 0   | 0   | Cache in L1 + L2 (default)                      | Reused data (Q tile)        |
| 1   | 0   | Bypass L1, cache in L2                           | Inter-CU shared data        |
| 0   | 1   | Cache in L1, streaming in L2                     | Locally reused, globally one-shot |
| 1   | 1   | Bypass L1, streaming L2                           | One-shot global reads (K/V stream) |

### CDNA4 (gfx950): SCOPE + TH (Temporal Hint) system

CDNA4 **replaces GLC/SLC/DLC** with two new fields on all memory instructions:

| Field | Bits | Values                                      |
|-------|------|---------------------------------------------|
| SCOPE | 2    | 0=Default, 1=SE (Shader Engine), 2=Device, 3=System |
| TH    | 3    | Bit 0=RT, Bit 1=NT, Bit 2=HT (combinable)  |

#### TH (Temporal Hint) bits

| Bit | Name | Meaning                                                  |
|-----|------|----------------------------------------------------------|
| RT  | Return-to-Temporal | Non-temporal at scope level, temporal above |
| NT  | Non-Temporal       | Bypass caching at scope level               |
| HT  | High-Temporal      | Hint to keep in cache (LRU priority)        |

#### Common CDNA4 patterns

| SCOPE | TH   | Behavior                                    | CDNA3 equivalent |
|-------|------|---------------------------------------------|------------------|
| 0     | 0    | Default caching (L1+L2)                     | GLC=0 SLC=0      |
| SE    | NT   | Non-temporal at L0/L1, temporal at L2       | GLC=1 SLC=0      |
| Device| NT   | Non-temporal at L0/L1 and L2                | GLC=1 SLC=1      |
| SE    | HT   | High-temporal at L0/L1 (keep cached)        | No equivalent     |
| Device| RT   | Non-temporal at device scope, temporal above| No equivalent     |

## How to use it

### In HIP code
```cpp
// Non-temporal load (works on both CDNA3 and CDNA4):
float val = __builtin_nontemporal_load(ptr);

// Non-temporal store:
__builtin_nontemporal_store(val, ptr);

// CDNA3 — precise control via inline assembly:
asm volatile("global_load_dword %0, %1, off glc slc"
    : "=v"(val) : "v"(addr) : "memory");

// CDNA4 — uses SCOPE+TH syntax instead:
asm volatile("global_load_dword %0, %1, off scope:SCOPE_DEV th:TH_LOAD_NT"
    : "=v"(val) : "v"(addr) : "memory");
```

### FMHA pattern
```
Q tile (reused across all K/V tiles): default (cache in L1+L2)
K/V tiles (streamed once):
  CDNA3: GLC|SLC (bypass L1, non-temporal L2)
  CDNA4: scope:SCOPE_SE th:TH_LOAD_NT (non-temporal at shader engine)
Output accumulator: default writes
```

## Pitfalls

1. **Over-using SLC**: marking everything non-temporal defeats caching entirely.
2. **Cross-XCD coherence**: GLC ensures L1 coherence but L2 is per-XCD. For
   cross-XCD visibility, use system-scope atomics or fences.
3. **Cache flag syntax varies**: buffer_load uses GLC/SLC directly; global_load
   encoding may differ. Check ISA reference for your instruction family.

## CDNA3 vs CDNA4 differences

| Aspect                | CDNA3 (gfx940/942)            | CDNA4 (gfx950)                          |
|-----------------------|-------------------------------|-----------------------------------------|
| Cache control model   | GLC/SLC/DLC (3 independent bits) | SCOPE (2-bit) + TH (3-bit)           |
| Scope granularity     | Implicit per bit              | Explicit: SE, Device, System            |
| Temporal hints        | Binary (temporal/non-temporal)| RT, NT, HT (combinable)                |
| High-temporal hint    | No                            | Yes (HT bit — LRU priority)            |
| Encoding              | GLC/SLC/DLC in instruction    | SCOPE/TH fields in all load/store/atomic|
| HIP builtins          | `__builtin_nontemporal_*`     | Same builtins, compiler maps to SCOPE+TH|

**Key migration note**: Inline assembly using `glc`, `slc`, `dlc` modifiers will
**not assemble** for gfx950. Must use `scope:` and `th:` syntax instead. HIP-level
code (`__builtin_nontemporal_*`) is portable — the compiler handles the translation.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Chapter 5: Vector Memory
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Chapter 5, Section 7.1 (Scope and Temporal Hints)
