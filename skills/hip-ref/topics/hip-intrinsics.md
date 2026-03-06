# HIP Device Intrinsics Catalog

## What it is

Complete catalog of HIP device intrinsics for AMD GPUs: warp/wave operations, fast
math, atomics, and AMDGCN-specific builtins. These map directly to hardware
instructions and are the building blocks for high-performance kernel code.

## Warp/wave intrinsics

```cpp
// Shuffle (cross-lane data exchange):
T __shfl(T val, int srcLane);              // read from srcLane
T __shfl_up(T val, unsigned delta);        // read from lane - delta
T __shfl_down(T val, unsigned delta);      // read from lane + delta
T __shfl_xor(T val, int laneMask);         // read from lane ^ laneMask

// NOTE: AMD wave64 — no __shfl_sync needed (wave is always lockstep)
// NOTE: warpSize = 64 on CDNA (not 32)

// Vote functions:
uint64_t __ballot(int pred);               // 64-bit mask of lanes where pred!=0
int __any(int pred);                       // true if any lane has pred!=0
int __all(int pred);                       // true if all lanes have pred!=0

// Population count & bit scan:
int __popc(unsigned int x);                // count set bits
int __popcll(unsigned long long x);        // 64-bit popcount
int __ffs(int x);                          // find first set bit (1-indexed)
int __ffsll(long long x);                  // 64-bit version
int __clz(int x);                          // count leading zeros
int __clzll(long long x);                  // 64-bit version

// Lane identification:
// threadIdx.x % warpSize gives lane ID within wavefront
// warpSize = 64 on CDNA
```

## Fast math intrinsics

```cpp
// Exponential (faster but lower precision than standard):
float __expf(float x);                     // fast exp (v_exp_f32)
float __exp2f(float x);                    // fast exp2
float __exp10f(float x);                   // fast exp10

// Logarithm:
float __logf(float x);                     // fast log (v_log_f32)
float __log2f(float x);                    // fast log2
float __log10f(float x);                   // fast log10

// Trigonometry:
float __sinf(float x);                     // fast sin (v_sin_f32)
float __cosf(float x);                     // fast cos (v_cos_f32)
float __tanf(float x);                     // fast tan
void __sincosf(float x, float* s, float* c); // sin+cos together

// Reciprocal/sqrt:
float __rsqrtf(float x);                   // 1/sqrt(x) (v_rsq_f32)
float __frcp_rn(float x);                  // 1/x (v_rcp_f32)
float __fdividef(float x, float y);        // fast x/y
float __fsqrt_rn(float x);                 // fast sqrt

// Clamp:
float __saturatef(float x);                // clamp to [0.0, 1.0]
```

## Atomic intrinsics

```cpp
// Integer atomics (all address spaces):
int atomicAdd(int* addr, int val);
int atomicSub(int* addr, int val);
int atomicMin(int* addr, int val);
int atomicMax(int* addr, int val);
int atomicExch(int* addr, int val);
int atomicCAS(int* addr, int compare, int val);
int atomicAnd(int* addr, int val);
int atomicOr(int* addr, int val);
int atomicXor(int* addr, int val);

// Float atomics (native on CDNA3+):
float atomicAdd(float* addr, float val);   // buffer_atomic_add_f32 / ds_add_f32
double atomicAdd(double* addr, double val);// native FP64 atomic
// NOTE: float atomicMin/Max NOT native — use CAS loop
```

## AMDGCN-specific builtins

```cpp
// Lane operations:
int __builtin_amdgcn_readfirstlane(int v);        // lane 0 VGPR → SGPR
int __builtin_amdgcn_readlane(int v, int lane);   // specific lane → SGPR
int __builtin_amdgcn_writelane(int val, int lane, int old); // SGPR → specific lane

// Cross-lane (direct ISA control):
int __builtin_amdgcn_ds_permute(int addr, int val);   // ds_permute (addr = lane*4)
int __builtin_amdgcn_ds_bpermute(int addr, int val);  // ds_bpermute
int __builtin_amdgcn_ds_swizzle(int val, int pattern); // ds_swizzle
int __builtin_amdgcn_mov_dpp(int val, int ctrl,
                              int row_mask, int bank_mask,
                              bool bound_ctrl);         // DPP

// MFMA intrinsics:
float16 __builtin_amdgcn_mfma_f32_32x32x8f16(half4 a, half4 b, float16 c,
                                               int cbsz, int abid, int blgp);
float4 __builtin_amdgcn_mfma_f32_16x16x16f16(half4 a, half4 b, float4 c,
                                               int cbsz, int abid, int blgp);
// (many more variants — see ISA reference for complete list)

// Synchronization:
void __builtin_amdgcn_s_waitcnt(int cnt);    // s_waitcnt
void __builtin_amdgcn_s_barrier();           // s_barrier
void __builtin_amdgcn_fence(int ordering, const char* scope); // memory fence

// Lane ID:
unsigned __builtin_amdgcn_mbcnt_lo(unsigned mask, unsigned val); // lane ID (low 32)
unsigned __builtin_amdgcn_mbcnt_hi(unsigned mask, unsigned val); // lane ID (high 32)

// Thread/block ID:
unsigned __builtin_amdgcn_workitem_id_x();   // threadIdx.x
unsigned __builtin_amdgcn_workitem_id_y();   // threadIdx.y
unsigned __builtin_amdgcn_workitem_id_z();   // threadIdx.z
unsigned __builtin_amdgcn_workgroup_id_x();  // blockIdx.x
unsigned __builtin_amdgcn_workgroup_id_y();  // blockIdx.y
unsigned __builtin_amdgcn_workgroup_id_z();  // blockIdx.z
```

## CUDA → HIP name mapping

| CUDA                  | HIP                    | Notes                          |
|-----------------------|------------------------|--------------------------------|
| __shfl_sync           | __shfl                 | No sync needed (wave lockstep) |
| __ballot_sync         | __ballot               | Returns uint64_t (wave64)      |
| __any_sync            | __any                  | No sync mask argument          |
| __all_sync            | __all                  | No sync mask argument          |
| warpSize              | warpSize               | 64 on CDNA (not 32!)           |
| __syncwarp            | (not needed)           | Wave is always lockstep        |
| __ldg                 | (plain load)           | AMD has no texture cache path  |
| atomicAdd (float)     | atomicAdd (float)      | Native on CDNA3+               |

## CDNA4-only builtins

```cpp
// Permlane swaps (CDNA4 only — VALU pipeline, no LDS contention):
__builtin_amdgcn_permlane16_swap(vdst, src0)      // swap odd/even 16-lane rows
__builtin_amdgcn_permlane32_swap(vdst, src0)      // swap lanes 0-31 with 32-63
// NOTE: destructive — both vdst and src0 are modified

// Hardware PRNG (CDNA4 only):
unsigned __builtin_amdgcn_prng_b32(unsigned src);  // v_prng_b32
// Generates pseudo-random numbers; useful for stochastic rounding
```

## Pitfalls

1. **warpSize = 64**: all masks are 64-bit, reductions need 6 steps not 5.
2. **No _sync variants needed**: AMD waves are lockstep, no partial-wave execution.
   But __ballot returns uint64_t (not uint32_t) — check your bit manipulation.
3. **__ldg doesn't exist**: AMD has no explicit read-only texture cache load.
   Regular loads go through L1/L2 caching as normal.
4. **__builtin_amdgcn_* are Clang-specific**: not portable to other compilers.
5. **Permlane swaps are CDNA4-only**: code using `__builtin_amdgcn_permlane32_swap`
   will fail on gfx942. Guard with `#if __gfx950__` or runtime arch detection.

## Sources

- HIP kernel language: https://rocm.docs.amd.com/projects/HIP/en/develop/reference/kernel_language.html
- LLVM AMDGPU usage: https://llvm.org/docs/AMDGPUUsage.html
- LLVM source (BuiltinsAMDGPU.def): https://github.com/llvm/llvm-project
