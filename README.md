# agent-skills

A collection of Claude Code agent skills for specialized tasks.

## Skills

| Skill | Description |
|-------|-------------|
| **[ck-kernel-resource-usage](skills/ck-kernel-resource-usage/SKILL.md)** | Analyze GPU kernel resource usage (VGPRs, AGPRs, SGPRs, occupancy, scratch memory, LDS, register spills) by building a CK target with `-Rpass-analysis=kernel-resource-usage` and parsing the build log. |
| **[ck-ci-build](skills/ck-ci-build/SKILL.md)** | Trigger Jenkins CI builds for Composable Kernel PRs with optional parameter overrides. Uses curl for status checks and playwright-cli for browser-based build triggering. Supports saved parameter presets, in-progress build detection, and dry-run mode. |
| **[ck-ci-report](skills/ck-ci-report/SKILL.md)** | Analyze CI build failures for Composable Kernel PRs on the Jenkins dashboard. Uses playwright-cli for browser automation and the Blue Ocean REST API for deep-dive stage log extraction. Handles success, failure, aborted, infra, and no-build cases. |
| **[ck-fmha-codegen-guide](skills/ck-fmha-codegen-guide/SKILL.md)** | Generate comprehensive FMHA kernel selection guides by dynamically analyzing CK codegen source code. Produces filename structure docs, field references, minimal kernel sets, and filter commands for `generate.py`. |
| **[ck-list-fmha-prs](skills/ck-list-fmha-prs/SKILL.md)** | List open pull requests from ROCm/rocm-libraries focused on fused multi-head attention (FMHA) kernels. |
| **[post-review](skills/post-review/SKILL.md)** | Validate and post inline PR comments from a prior `/review` output. Spawns a subagent to verify each claim against actual code, drops wrong items, formats confirmed findings as inline comment drafts, and optionally posts them to GitHub. Works with both PR and local branch reviews. |
| **[gpu-usage](skills/gpu-usage/SKILL.md)** | Report GPU usage on shared servers — shows which processes occupy each GPU, VRAM percentage, GPU utilization, process owner, elapsed time, and Docker container name. |
| **[hip-kernel-team](skills/hip-kernel-team/SKILL.md)** | Launch and manage a multi-agent team for HIP/GPU kernel development, debugging, and optimization. Configurable roles (Lead, Implementer, Profiler, Researcher) with optional recall-plugin integration and long-running context rotation. |
| **[monorepo-bridge](skills/monorepo-bridge/SKILL.md)** | Bidirectional commit transfer between monorepos and standalone submodule repos. CLI tool with setup, split, export, sync, reset, and verify subcommands. Uses fetch + subtree merge for export, rebase for sync. Auto-detects config from existing remotes. |
| **[p4-config](skills/p4-config/SKILL.md)** | Manage Perforce server configurations — switch between P4 servers, download files from depot paths, and create new server configs. Stores settings in `.p4config.<name>` files. |

## Usage

These skills are designed for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Install them via the Claude Code skill system or symlink them into your Claude Code skills directory.
