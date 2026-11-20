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
| **[pr-review](skills/pr-review/SKILL.md)** | Lead agent for reviewing one PR through the reviewer and architect agents already running in its herdr workspace (found by launch command, never started by the lead): triage with care marks by PR type, facts-only findings, a findings ledger kept across rounds and sessions, and one-by-one posting through `post-review`. |
| **[pr-review-auto](skills/pr-review-auto/SKILL.md)** | Review one GitHub PR with a herdr agent team: this session becomes the lead of one reviewer and one architect, who review independently, critique each other's report once, and post inline comments under your own `gh` account. Follows up on its threads, approves only when nothing blocks, and cleans up its `pr-review-auto/<N>` branch. Per-repository config; dry run by default; static review only. |
| **[pr-watch](skills/pr-watch/SKILL.md)** | Watch a GitHub repository for PRs matching your interest criteria: this session becomes the supervisor, scans on a schedule, and starts one `pr-review-auto` lead per PR in a tab of its own herdr workspace. Keeps a record, retries busy and unconfigured PRs, relays escalations to you. |
| **[post-review](skills/post-review/SKILL.md)** | Validate and post inline PR comments from a prior `/review` output. Spawns a subagent to verify each claim against actual code, drops wrong items, formats confirmed findings as inline comment drafts, and optionally posts them to GitHub. Works with both PR and local branch reviews. |
| **[gpu-occupant-owner](skills/gpu-occupant-owner/SKILL.md)** | Name the person behind a process occupying a GPU on a shared server: per-GPU usage and occupants, through containers and process ancestry, and through the login journal for a process that already exited. |
| **[monorepo-bridge](skills/monorepo-bridge/SKILL.md)** | Bidirectional commit transfer between monorepos and standalone submodule repos. CLI tool with setup, split, export, sync, reset, and verify subcommands. Uses fetch + subtree merge for export, rebase for sync. Auto-detects config from existing remotes. |
| **[p4-config](skills/p4-config/SKILL.md)** | Manage Perforce server configurations - switch between P4 servers, download files from depot paths, and create new server configs. Stores settings in `.p4config.<name>` files. |
| **[handoff](skills/handoff/SKILL.md)** | Compact the current conversation into a single self-contained handoff document so a fresh agent can resume the work. Captures not just what's next but the operating rules, decisions, workflow, and dead ends, then emits a copy-paste kickoff prompt for the next session. |
| **[teams-unread](skills/teams-unread/SKILL.md)** | List unread Microsoft Teams 1:1/group chats, or pull recent message history from a specific chat, by reading the Teams desktop app's UI Automation accessibility tree - no Teams API or bot registration needed. Windows only. |
| **[message-discipline](skills/message-discipline/SKILL.md)** | Gate every outbound inter-agent message on whether it carries substantive value and whether sending is required right now, suppressing bare acknowledgments and status placeholders regardless of role or recipient count. |
| **[agent-context-usage-monitor](skills/agent-context-usage-monitor/SKILL.md)** | Report how full each live herdr agent's context window is against its model's rotation threshold. `--rotate-only` prints only the agents due for rotation, so a cron can act on the output without judging percentages. Read-only: never rotates or messages an agent. |

## Usage

Install these through the Claude Code skill system or link them into the Claude Code skills directory.
