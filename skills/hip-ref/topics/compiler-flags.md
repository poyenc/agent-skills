# Compiler Flags & Attributes

## What it is

hipcc/clang compiler flags and kernel attributes control code generation for
AMD GPUs: target architecture, register limits, occupancy hints, inlining,
and optimization level. These are the primary knobs for tuning compiled kernel
performance without changing source code.

## When you care

- Setting the correct target architecture (gfx942 vs gfx950)
- Controlling occupancy via register limits
- Debugging with ISA output (--save-temps)
- Forcing function inlining for kernel performance
- Tuning wavefront size and CU mode

## Key flags

### Architecture targeting
```bash
# MI300A:
hipcc --offload-arch=gfx940 kernel.hip

# MI300X / MI325X:
hipcc --offload-arch=gfx942 kernel.hip

# MI350X / MI355X:
hipcc --offload-arch=gfx950 kernel.hip

# Multiple targets:
hipcc --offload-arch=gfx942 --offload-arch=gfx950 kernel.hip
```

### Kernel attributes (in source)
```cpp
// Target occupancy (waves per SIMD):
__attribute__((amdgpu_waves_per_eu(4, 4)))    // exactly 4 waves
__attribute__((amdgpu_waves_per_eu(2)))        // at least 2 waves

// Cap register usage:
__attribute__((amdgpu_num_vgpr(128)))          // max 128 VGPRs
__attribute__((amdgpu_num_sgpr(48)))           // max 48 SGPRs

// Workgroup size hint:
__attribute__((amdgpu_flat_work_group_size(256, 256)))
```

### Optimization and debug
```bash
-O3                    # max optimization (default for release)
-O0                    # no optimization (debug)
-g                     # debug info
-save-temps            # save intermediate files (including ISA .s)
-Rpass-analysis=kernel-resource-usage  # print VGPR/SGPR/occupancy

# LLVM backend options:
-mllvm -amdgpu-function-calls=false   # inline all functions
-mllvm -amdgpu-early-inline-all=true  # aggressive early inlining
```

### Wave and CU mode
```bash
-mwavefrontsize64      # force wave64 (default on CDNA)
-mcumode               # CU mode (default on CDNA)
```

## How to use it

### Workflow for occupancy tuning
```bash
# 1. Compile with resource usage reporting:
hipcc --offload-arch=gfx942 -Rpass-analysis=kernel-resource-usage -O3 kernel.hip

# 2. Read output:
# SGPRs: 48, VGPRs: 132, AGPRs: 16, ScratchSize: 0, Occupancy: 3

# 3. If occupancy too low, try:
# Option A: add attribute to cap VGPRs
__attribute__((amdgpu_num_vgpr(128)))  // forces 4 waves

# Option B: refactor code to reduce register pressure

# 4. Recompile and verify no scratch spills appeared
```

### Getting ISA output
```bash
# Save all intermediate files:
hipcc --save-temps --offload-arch=gfx942 -O3 kernel.hip
# Look for .s file — contains ISA assembly

# Or use llvm-objdump on compiled binary:
llvm-objdump --mcpu=gfx942 -d kernel.o > kernel.isa
```

## Pitfalls

1. **Wrong --offload-arch**: using gfx942 binary on MI350X (gfx950) = crash.
2. **amdgpu_num_vgpr causing spills**: capping VGPRs too low forces spills,
   which is worse than the occupancy gain. Always check ScratchSize.
3. **amdgpu_waves_per_eu misunderstanding**: this is waves per SIMD (EU=SIMD),
   not per CU. Max is 8, not 32.
4. **-O0 for profiling**: don't profile unoptimized code. Use -O3 + debug info (-g).

## CDNA3 vs CDNA4 differences

| Aspect                | CDNA3                     | CDNA4                             |
|-----------------------|---------------------------|-----------------------------------|
| Target arch           | gfx940 (MI300A), gfx942 (MI300X/MI325X) | **gfx950** (MI350X/MI355X) |
| Wave mode             | wave64                    | wave64 (same)                     |
| CU mode               | -mcumode (default)        | Same                              |
| VGPR/occupancy report | ArchVGPRs + AGPRs separate| ArchVGPRs + AGPRs **additive**    |
| New target features   | —                         | scaled-mfma, f8f6f4, prng, permlane-swap, lds-transpose-read |
| Inline asm cache flags| `glc slc dlc`             | **`scope:X th:Y`** (new syntax)   |

**Key migration steps for CDNA4**:
1. Add `--offload-arch=gfx950` to build command
2. Inline assembly using `glc`/`slc`/`dlc` must be updated to `scope:`/`th:` syntax
3. Occupancy analysis must account for additive AGPR+VGPR (not max)
4. `s_set_gpr_idx_mode` / `s_set_gpr_idx_idx` are removed — check for usage
5. `expcnt` in `s_waitcnt` is unused on gfx950

## Sources

- LLVM AMDGPU Backend: https://rocm.docs.amd.com/projects/llvm-project/en/latest/LLVM/llvm/html/AMDGPUUsage.html
- Clang attributes: https://rocm.docs.amd.com/projects/llvm-project/en/latest/LLVM/clang/html/AttributeReference.html
- ROCmcc reference: https://rocm.docs.amd.com/en/docs-6.0.2/reference/rocmcc.html
- hipcc documentation: `pdfs/hipcc-documentation.pdf`
