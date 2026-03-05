# agent-skills

A collection of Claude Code agent skills for specialized tasks.

## Skills

| Skill | Description |
|-------|-------------|
| **[hip-ref](skills/hip-ref/)** | AMD HIP GPU kernel developer reference for CDNA3 and CDNA4 architectures. Covers MFMA instructions, register layout, LDS, occupancy, profiling, and more. |
| **[list-fmha-prs](skills/list-fmha-prs/)** | List open pull requests from ROCm/rocm-libraries focused on fused multi-head attention (FMHA) kernels. |

## Usage

These skills are designed for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install them via the Claude Code skill system or symlink them into your Claude Code skills directory.
