# HIP-Ref Topic Index

Keyword-tagged catalog. Read this first to route queries to the right topic file.

---

## mfma-register-layout
Keywords: mfma, matrix core, register layout, lane mapping, VGPR, AGPR, intrinsics, __builtin_amdgcn_mfma, broadcast, cbsz, abid, blgp, accumulation register, v_mfma, matrix multiply, WMMA, rocWMMA, matrix instruction calculator
Topic: topics/mfma-register-layout.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.7 Matrix Fused Multiply-Add), pdfs/cdna4-isa-reference.pdf (Ch.7)
Links: https://rocm.blogs.amd.com/software-tools-optimization/matrix-cores-cdna/README.html

## occupancy-register-pressure
Keywords: occupancy, register pressure, waves per EU, waves per CU, resource limits, performance cliff, occupancy calculator, amdgpu-waves-per-eu, kernel launch, wave slots
Topic: topics/occupancy-register-pressure.md
PDFs: pdfs/amd-cdna3-whitepaper.pdf, pdfs/amd-cdna4-whitepaper.pdf
Links: https://gpuopen.com/learn/amd-lab-notes/amd-lab-notes-register-pressure-readme/

## vgpr-sgpr-agpr
Keywords: VGPR, SGPR, AGPR, register file, register types, allocation granularity, v_accvgpr, spill, register count, ArchVGPR, AccVGPR, unified register file
Topic: topics/vgpr-sgpr-agpr.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.2 Shader Processor), pdfs/cdna4-isa-reference.pdf (Ch.2)
Links: https://gpuopen.com/learn/amd-lab-notes/amd-lab-notes-register-pressure-readme/

## cross-lane-ops
Keywords: DPP, ds_permute, ds_bpermute, ds_swizzle, cross-lane, warp shuffle, shfl, butterfly, reduction, broadcast, row rotation, wave-level, permute, lane swap, __shfl, dpp_ctrl
Topic: topics/cross-lane-ops.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.6 Data Share), pdfs/cdna4-isa-reference.pdf (Ch.6)
Links: https://gpuopen.com/learn/amd-gcn-assembly-cross-lane-operations/

## wavefront-scheduling
Keywords: wave scheduling, instruction issue, VALU, VMEM, LDS pipeline, overlap, s_waitcnt, latency hiding, instruction mix, dual issue, pipeline, wavefront, warp
Topic: topics/wavefront-scheduling.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.2), pdfs/cdna4-isa-reference.pdf (Ch.2)

## data-types-precision
Keywords: FP8, FP6, FP4, BF16, FP16, FP32, FP64, MXFP, OCP, block exponent, E4M3, E5M2, E2M3, E3M2, E2M1, data type, precision, quantization, type mixing, stochastic rounding, scaled format
Topic: topics/data-types-precision.md
PDFs: pdfs/cdna4-isa-reference.pdf (Ch.7), pdfs/amd-cdna4-whitepaper.pdf
Links: https://rocm.blogs.amd.com/software-tools-optimization/matrix-cores-cdna/README.html

## memory-hierarchy
Keywords: L0, L1, L2, HBM, cache, memory, bandwidth, vector cache, scalar cache, instruction cache, last level cache, infinity cache, XCD, memory hierarchy, VMEM
Topic: topics/memory-hierarchy.md
PDFs: pdfs/amd-cdna3-whitepaper.pdf, pdfs/amd-cdna4-whitepaper.pdf
Links: https://rocm.docs.amd.com/en/latest/conceptual/gpu-arch.html

## lds-bank-conflicts
Keywords: LDS, bank conflict, shared memory, local data share, ds_read, ds_write, padding, XOR, bank, conflict-free, swizzle, CK, composable kernel, ck_tile
Topic: topics/lds-bank-conflicts.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.6 Data Share), pdfs/cdna4-isa-reference.pdf (Ch.6)
Links: https://rocm.docs.amd.com/projects/composable_kernel/en/latest/conceptual/ck_tile/hardware/lds_bank_conflicts.html

## buffer-vs-flat
Keywords: buffer_load, buffer_store, flat_load, flat_store, global_load, global_store, addressing, bounds checking, buffer resource, SGPR descriptor, oob_select, TBUFFER, buffer_load_lds
Topic: topics/buffer-vs-flat.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.5 Vector Memory, Ch.8 Flat Memory), pdfs/cdna4-isa-reference.pdf (Ch.5, Ch.8)

## async-copy-prefetch
Keywords: async copy, prefetch, global to LDS, buffer_load_lds, staging, DME, data movement engine, double buffer, software pipeline, producer consumer, global_load_lds, async
Topic: topics/async-copy-prefetch.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.5), pdfs/cdna4-isa-reference.pdf (Ch.5)
Links: https://rocm.docs.amd.com/projects/rocWMMA/en/latest/conceptual/programmers-guide.html

## cache-policies
Keywords: GLC, SLC, DLC, cache policy, L2 bypass, coherence, write-through, write-back, scope, glc, slc, dlc, cache control, non-temporal, streaming
Topic: topics/cache-policies.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.5 Vector Memory), pdfs/cdna4-isa-reference.pdf (Ch.5)

## global-scratch-spill
Keywords: scratch, spill, private segment, stack, register spill, global, scratch buffer, VGPR spill, spill cost, detect spill, s_buffer_load, private
Topic: topics/global-scratch-spill.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.8 Flat/Scratch), pdfs/cdna4-isa-reference.pdf (Ch.8)

## compiler-flags
Keywords: amdgpu-waves-per-eu, num-vgpr, num-sgpr, mcumode, wavefrontsize64, target features, hipcc, compiler, clang, -mllvm, optimization, -O3, -march, gfx940, gfx942, gfx950, compiler flags
Topic: topics/compiler-flags.md
PDFs: pdfs/hipcc-documentation.pdf
Links: https://rocm.docs.amd.com/projects/llvm-project/en/latest/LLVM/llvm/html/AMDGPUUsage.html

## inline-asm
Keywords: asm volatile, inline assembly, register constraint, v, s, a, s_waitcnt, __asm__, asm, assembly, GCN, AMDGCN, ISA, hand-written
Topic: topics/inline-asm.md
PDFs: pdfs/cdna3-isa-reference.pdf, pdfs/cdna4-isa-reference.pdf
Links: https://rocm.docs.amd.com/projects/HIP/en/develop/reference/kernel_language.html

## reading-isa
Keywords: disassembly, ISA, RGA, instruction encoding, objdump, amdgpu-dis, binary, ELF, code object, Radeon GPU Analyzer, llvm-objdump, assembly output
Topic: topics/reading-isa.md
Links: https://rocm.blogs.amd.com/software-tools-optimization/amdgcn-isa/README.html, https://gpuopen.com/manuals/rga_manual/rga_manual-index/

## profiling-workflow
Keywords: omniperf, rocprof, rocprofv3, profiling, performance counters, VMEM busy, LDS bank conflict, VALU util, MFMA util, omniperf analyze, metrics, hardware counters, trace, rocprofiler
Topic: topics/profiling-workflow.md
Links: https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/, https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/

## roofline-analysis
Keywords: roofline, arithmetic intensity, compute bound, memory bound, Speed-of-Light, SoL, FLOPS, bandwidth, ops/byte, performance model, bottleneck
Topic: topics/roofline-analysis.md
Links: https://rocm.docs.amd.com/projects/rocprofiler-compute/en/latest/

## xcd-topology-numa
Keywords: XCD, XCC, topology, NUMA, NPS, L2 partitioning, multi-die, 8-XCD, NPS1, NPS4, affinity, memory partition, compute partition, SPX, DPX, QPX, TPX
Topic: topics/xcd-topology-numa.md
PDFs: pdfs/amd-cdna3-whitepaper.pdf, pdfs/amd-cdna4-whitepaper.pdf
Links: https://rocm.blogs.amd.com/software-tools-optimization/compute-memory-modes/README.html

## hardware-specs-table
Keywords: specs, CU count, clock speed, HBM bandwidth, L2 size, LDS, TFLOPS, TDP, MI300X, MI300A, MI325X, MI350X, MI355X, specifications, datasheet, hardware
Topic: topics/hardware-specs-table.md
PDFs: pdfs/mi300x-accelerator-datasheet.pdf, pdfs/mi325x-accelerator-datasheet.pdf, pdfs/mi350x-gpu-datasheet.pdf, pdfs/mi355x-gpu-datasheet.pdf, pdfs/mi300a-apu-datasheet.pdf

## software-pipelining
Keywords: software pipeline, double buffer, triple buffer, PGR, ping-pong, producer consumer, overlap, prefetch loop, LDS double buffer, register staging, pipelining, PGR1_LB2
Topic: topics/software-pipelining.md
Links: https://rocm.docs.amd.com/projects/rocWMMA/en/latest/conceptual/programmers-guide.html

## atomics
Keywords: atomic, atomicAdd, atomicCAS, atomicMin, atomicMax, global atomic, LDS atomic, return, no-return, float atomic, rounding, buffer_atomic, ds_add
Topic: topics/atomics.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.5, Ch.6), pdfs/cdna4-isa-reference.pdf (Ch.5, Ch.6)

## exec-mask-control-flow
Keywords: EXEC, exec mask, divergent, control flow, predication, branching, s_and_saveexec, s_or_saveexec, s_mov_b64, lane mask, active lanes, divergence, if-else, branch
Topic: topics/exec-mask-control-flow.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.3 Scalar ALU, Ch.4 Vector ALU), pdfs/cdna4-isa-reference.pdf (Ch.3, Ch.4)

## packed-math
Keywords: packed, v_pk, FP16, BF16, packed arithmetic, two-element, VOPD, dual issue, packed_convert, v_pk_fma_f16, v_pk_add_f16, v_pk_mul_f16, packed operation
Topic: topics/packed-math.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.4 Vector ALU), pdfs/cdna4-isa-reference.pdf (Ch.4)

## sparsity
Keywords: sparsity, structured sparsity, 2:4, sparse MFMA, sparse matrix, compression, sparse index, metadata, pruning, sparse_mfma
Topic: topics/sparsity.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.7), pdfs/cdna4-isa-reference.pdf (Ch.7)

## swizzled-buffer-addressing
Keywords: swizzle, swizzled buffer, tiled access, 2D access, swizzle mode, buffer addressing, index stride, element size, swizzle pattern
Topic: topics/swizzled-buffer-addressing.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.5 Vector Memory), pdfs/cdna4-isa-reference.pdf (Ch.5)

## waitcnt-hazards
Keywords: s_waitcnt, vmcnt, lgkmcnt, expcnt, hazard, data dependency, NOP, pipeline interlock, wait, waitcount, barrier, s_barrier, memory fence, stall
Topic: topics/waitcnt-hazards.md
PDFs: pdfs/cdna3-isa-reference.pdf (Ch.2, Ch.3), pdfs/cdna4-isa-reference.pdf (Ch.2, Ch.3)

## hip-intrinsics
Keywords: intrinsic, __builtin_amdgcn, __shfl, __ballot, __any, __all, atomicAdd, atomicCAS, __ldg, __expf, __log2f, __sinf, warp, shuffle, device function, builtin, HIP API, lane_id, warp_size
Topic: topics/hip-intrinsics.md
Links: https://rocm.docs.amd.com/projects/HIP/en/develop/reference/kernel_language.html, https://llvm.org/docs/AMDGPUUsage.html
