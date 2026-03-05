# EXEC Mask & Divergent Control Flow

## What it is

The EXEC mask is a 64-bit register (wave64) where each bit controls whether a
lane executes vector instructions. The compiler uses EXEC mask manipulation to
implement if/else branching: both paths execute with different masks, then masks
are restored. Divergent branches always cost the sum of both paths.

## When you care

- Understanding divergent if/else performance cost
- FMHA causal masking (early exit when tile is fully masked)
- Warp-level voting (__ballot, __any, __all)
- Writing predicated code to avoid branch overhead

## How it works

### Divergent if/else pattern (compiler-generated)
```
// HIP source:
if (condition) {
    // then-block
} else {
    // else-block
}

// Compiled ISA:
v_cmp_* vcc, ...                    // evaluate condition per lane
s_and_saveexec_b64 s[0:1], vcc      // save EXEC, EXEC &= condition
// ... then-block (only lanes where condition=true) ...
s_andn2_b64 exec, s[0:1], exec     // EXEC = saved & ~current (false lanes)
// ... else-block (only lanes where condition=false) ...
s_or_b64 exec, exec, s[0:1]        // restore all lanes
```

### Predication (short branches)
```
For very short if/else (1-2 instructions), compiler uses v_cndmask_b32:
  Both paths compute, then select result based on condition.
  No EXEC mask change → no branch overhead.

// ISA:
v_cndmask_b32 v0, v_false, v_true, vcc
```

### Uniform branches (no divergence)
```
When ALL lanes take the same path:
  Compiler emits s_cbranch_* (scalar branch)
  Only one path executes → no wasted cycles

FMHA example: causal masking where entire tile is below diagonal
  → All lanes skip → uniform branch → free early exit
```

## Key numbers

| Scenario                      | Cost                              |
|-------------------------------|-----------------------------------|
| Uniform branch (all same)     | Cost of taken path only           |
| Divergent branch              | Cost of BOTH paths (serialized)   |
| Predication (v_cndmask)       | Cost of both computations (1 cycle each) |
| Nested divergence             | Multiplicative: 2^N paths for N levels |

## How to use it

### HIP intrinsics for EXEC mask queries
```cpp
// Check if any/all lanes satisfy condition:
bool any_active = __any(pred);    // s_or_b64 reduction
bool all_active = __all(pred);    // s_and_b64 reduction
uint64_t mask = __ballot(pred);   // get full EXEC mask as integer

// FMHA early exit for causal mask:
if (__all(row < col)) return;     // uniform branch if all lanes masked
```

### Minimize divergence
```cpp
// Bad: divergent branch in inner loop
for (int i = 0; i < N; i++) {
    if (threadIdx.x % 2 == 0)  // half the lanes each way → 2× cost
        val = f(val);
    else
        val = g(val);
}

// Better: restructure to avoid divergence
// Assign even/odd threads to different data, not different code paths
```

## Pitfalls

1. **Hidden divergence cost**: both paths always execute. A "fast path" optimization
   that only helps half the lanes still pays for the "slow path" too.
2. **Nested divergence**: if/else inside if/else saves/restores EXEC in SGPRs.
   Deep nesting uses more SGPRs and multiplies path costs.
3. **__syncthreads in divergent code**: calling __syncthreads() with divergent
   EXEC mask is UNDEFINED BEHAVIOR. All lanes must reach the barrier.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Ch.3 (Scalar ALU), Ch.4 (Vector ALU)
