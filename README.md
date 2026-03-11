# agent-skills

A collection of Claude Code agent skills for specialized tasks.

## Skills

| Skill | Description |
|-------|-------------|
| **[hip-ref](skills/hip-ref/)** | AMD HIP GPU kernel developer reference for CDNA3 and CDNA4 architectures. Covers MFMA instructions, register layout, LDS, occupancy, profiling, and more. |
| **[ck-kernel-resource-usage](skills/ck-kernel-resource-usage/)** | Analyze GPU kernel resource usage (VGPRs, AGPRs, SGPRs, occupancy, scratch memory, LDS, register spills) by building a CK target with `-Rpass-analysis=kernel-resource-usage` and parsing the build log. |
| **[ck-fmha-codegen-guide](skills/ck-fmha-codegen-guide/)** | Generate comprehensive FMHA kernel selection guides by dynamically analyzing CK codegen source code. Produces filename structure docs, field references, minimal kernel sets, and filter commands for `generate.py`. |
| **[ck-list-fmha-prs](skills/ck-list-fmha-prs/)** | List open pull requests from ROCm/rocm-libraries focused on fused multi-head attention (FMHA) kernels. |

## Usage

These skills are designed for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install them via the Claude Code skill system or symlink them into your Claude Code skills directory.
