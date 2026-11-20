# Triage: understand the PR and mark where care is needed

The title, body, and commit messages are claims. Derive what the PR does from the code, then
compare. Large PR: a read-only sonnet subagent writes the per-area summary and the lead
spot-checks it.

## Live facts to collect

- `gh pr view <N> --json title,body,files,commits,baseRefOid,headRefOid,mergeable,mergeStateStatus,updatedAt`
- Body freshness: GraphQL `lastEditedAt` of the body against the latest commit date; force-pushes;
  review threads; existing comments (avoid repeating them, and check whether they are already
  fixed at the current head).
- Reconcile every description claim with the diff: matches, not in the diff, or in the diff but
  unmentioned. A description that no longer matches the code is itself a finding.

## Types and where to mark care

Classify from the diff, not from the title. Tag each changed file with a type; a PR can have several. If none fits, use "other" and say why.

- Behavior change to existing code (bug fix, logic change): paths through real callers, boundary
  and error cases, a test that would fail on the old code.
- New feature: reachability from real callers, tests for the new behavior, documents that state it.
- Refactor, rename, move, or deletion: behavior actually preserved, surviving references to
  removed or renamed symbols, imports of deleted files.
- Public interface, configuration, schema, or output-format change: consumers outside the diff,
  defaults, compatibility, migration.
- Tests or harness only: would the test fail on the old code; is the oracle independent.
- Docs, build, dependency, packaging, or CI only: statements no longer matching the code, version
  and path consistency.
- Stacked on another PR: review the base PR first; review only this PR's own commits.

Domain-specific cautions (hardware, protocol, performance, security) come from the target
repository's design documents and CLAUDE.md, not from this skill.

## Output: the PR brief (half a page)

Intent as derived from the code, scope map by area, the type of each area, and the care marks
with the reason for each. It goes into the council briefs as claims and starting points.
