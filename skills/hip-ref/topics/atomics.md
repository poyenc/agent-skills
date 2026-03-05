# Atomic Operations

## What it is

Atomic operations provide read-modify-write guarantees on shared memory locations.
AMD CDNA supports both global (HBM/L2) and LDS atomics, with native floating-point
atomics for FP32 and FP64. LDS atomics are ~10-20× faster than global atomics.

## When you care

- FMHA: partial sum accumulation across tiles (softmax denominator)
- Histogram computation, reduction output
- Cross-workgroup synchronization
- Understanding return vs no-return performance difference

## Key numbers

| Atomic type          | Location | Latency    | Return value cost |
|----------------------|----------|------------|-------------------|
| LDS int32 atomic     | LDS      | ~20 cy     | Same              |
| LDS float32 atomic   | LDS      | ~20 cy     | Same              |
| Global int32 atomic  | L2/HBM   | ~200-400 cy| +memory round-trip|
| Global float32 atomic| L2/HBM   | ~200-400 cy| +memory round-trip|
| Global float64 atomic| L2/HBM   | ~200-400 cy| +memory round-trip|

## How to use it

### Global atomics
```cpp
// Integer: native hardware support
atomicAdd(&global_counter, 1);            // buffer_atomic_add_u32
atomicMin(&global_min, local_val);        // buffer_atomic_min_i32
atomicMax(&global_max, local_val);        // buffer_atomic_max_i32
atomicCAS(&addr, expected, desired);      // buffer_atomic_cmpswap

// Float: native on CDNA3+ (no CAS loop needed!)
atomicAdd(&global_sum, local_float);      // buffer_atomic_add_f32
atomicAdd(&global_sum_f64, local_double); // buffer_atomic_add_f64
```

### LDS atomics (much faster)
```cpp
// In shared memory — maps to ds_* instructions:
__shared__ float partial_sum;
atomicAdd(&partial_sum, my_value);        // ds_add_f32

// Pattern: reduce in LDS first, then one global atomic per workgroup
__shared__ float wg_sum;
atomicAdd(&wg_sum, my_value);             // fast LDS atomic
__syncthreads();
if (threadIdx.x == 0) {
    atomicAdd(&global_sum, wg_sum);       // one global atomic
}
```

### Return vs no-return
```
"Return" atomic: fetches the OLD value back to a VGPR
  int old = atomicAdd(&addr, 1);  // needs to read old value → slower

"No-return" atomic: fire-and-forget, don't need old value
  atomicAdd(&addr, 1);            // compiler may optimize to no-return
  // Faster: no data needs to come back to the wave

Tip: if you don't use the return value, compiler should auto-optimize.
```

### CAS loop for unsupported atomics
```cpp
// For operations without native atomic (e.g., atomicMin for float):
float atomicMinFloat(float* addr, float val) {
    int* addr_as_int = (int*)addr;
    int old = *addr_as_int, assumed;
    do {
        assumed = old;
        old = atomicCAS(addr_as_int, assumed,
                        __float_as_int(fminf(val, __int_as_float(assumed))));
    } while (assumed != old);
    return __int_as_float(old);
}
```

## Pitfalls

1. **Non-deterministic FP order**: floating-point atomicAdd is not associative.
   Different execution orders give different bit-exact results.
2. **Global atomics in hot loops**: each global atomic is ~400 cycles. Use local
   reduction (registers → LDS → one global atomic) instead.
3. **Assuming FP16 atomics exist**: FP16 atomicAdd is NOT natively supported on
   CDNA3. Must use CAS loop or upconvert to FP32.

## CDNA3 vs CDNA4 differences

Both support native FP32/FP64 global atomics. CDNA4 may add FP16 atomics — check ISA.

## Sources

- CDNA3 ISA: `pdfs/cdna3-isa-reference.pdf` — Ch.5 (buffer_atomic_*), Ch.6 (ds_* atomics)
- CDNA4 ISA: `pdfs/cdna4-isa-reference.pdf` — Ch.5, Ch.6
