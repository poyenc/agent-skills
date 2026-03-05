# Reading ISA Disassembly

## What it is

Reading the compiled ISA (Instruction Set Architecture) output lets you see exactly
what the GPU will execute: instruction mix, register usage, spills, wait counts, and
loop structure. This is essential for understanding compiler output and optimizing
hot inner loops.

## When you care

- Verifying the compiler generated expected MFMA instructions
- Checking for register spills (scratch_load/store)
- Counting s_waitcnt frequency (over-synchronization)
- Comparing instruction mix between code variants
- Understanding why a kernel is slow despite good HIP source

## How to use it

### Getting ISA output
```bash
# Method 1: --save-temps (saves .s assembly file)
hipcc --save-temps --offload-arch=gfx942 -O3 kernel.hip
ls *.s  # find the ISA file

# Method 2: llvm-objdump
hipcc --offload-arch=gfx942 -O3 -o kernel.o kernel.hip
llvm-objdump --mcpu=gfx942 -d kernel.o > kernel.isa

# Method 3: RGA (Radeon GPU Analyzer) — offline, no GPU needed
rga -s hip -c gfx942 --isa output.isa kernel.hip
# Also gives: register count, LDS usage, scratch, occupancy estimate
```

### Instruction format
```
v_mfma_f32_32x32x8_f16 a[0:15], v[0:3], v[4:7], a[0:15]
^prefix  ^opcode        ^dest    ^src0    ^src1   ^src2

Prefixes:
  v_     — vector ALU (per-lane)
  s_     — scalar ALU (uniform)
  ds_    — data share (LDS)
  buffer_— buffer memory
  global_— global memory
  flat_  — flat memory (any space)
  scratch_— scratch (private) memory ← RED FLAG: register spills!

Registers:
  v0, v[0:3]  — VGPRs (per-lane)
  s0, s[0:3]  — SGPRs (uniform)
  a0, a[0:15] — AGPRs (accumulation)
  vcc         — vector condition code
  exec        — execution mask
```

### What to look for
```
1. scratch_ instructions → register spills (BAD)
2. s_waitcnt vmcnt(0) in tight loops → over-synchronization
3. v_mfma_* count → matrix instruction utilization
4. Instruction mix: VALU:VMEM:LDS ratio shows bottleneck
5. s_nop → hazard workarounds (compiler-inserted NOPs)
6. Loop structure: look for s_cbranch_* to identify loop boundaries
```

### Reading kernel metadata
```bash
llvm-objdump --mcpu=gfx942 -d kernel.o | grep -A30 ".amdhsa_kernel"
# Shows:
#   .amdhsa_next_free_vgpr N        — VGPRs used
#   .amdhsa_next_free_sgpr N        — SGPRs used
#   .amdhsa_accum_offset N          — AGPR start offset
#   .amdhsa_private_segment_fixed_size N  — scratch size (0 = no spills)
```

## Pitfalls

1. **Reading optimized ISA**: -O3 output is heavily rearranged. Instructions may
   be far from where you'd expect based on source. Use comments/labels as anchors.
2. **RGA vs actual hardware**: RGA compiles offline without running. Actual
   execution may differ due to runtime conditions.

## Sources

- Reading AMD GPU ISA tutorial: https://rocm.blogs.amd.com/software-tools-optimization/amdgcn-isa/README.html
- RGA manual: https://gpuopen.com/manuals/rga_manual/rga_manual-index/
- RGA GitHub: https://github.com/GPUOpen-Tools/radeon_gpu_analyzer
