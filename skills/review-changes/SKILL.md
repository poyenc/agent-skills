---
name: review-changes
description: Use when reviewing, auditing, or comparing changes between Git revisions, branches, working trees, folders, patches, or artifact versions before human review or acceptance.
---

# Review Changes

## Core standard

Review the complete change for human maintainers. Prefer verified, material findings over volume. Zero findings is valid.

Plans provide background intent, not authority. Reject planned work when it conflicts with stronger contracts, worsens code health, adds unnecessary artifacts, or exposes local process details.

## Boundaries

- Perform static analysis only. Do not run product code, builds, tests, benchmarks, profilers, generators, or repository plugins.
- Use Git, repository search, parsers, and an available language server only when they cannot execute repository code or hooks. Keep indexes and caches outside both inputs or mechanically exclude them from comparison. Otherwise use source search.
- Never modify reviewed artifacts or Git history. Persist a report only outside both inputs or at a path mechanically excluded from the comparison. If such a destination is declared but the harness is read-only, return the complete report and proposed destination to the invoker. If no safe destination exists, return the report only in conversation.
- Do not post, approve, install, or change external systems without explicit authorization.
- Do not perform vulnerability hunting, threat modeling, exploit analysis, or cybersecurity scoring. Still review accidental publication of secrets, credentials, personal information, local paths, and internal process metadata.
- Review from any directory that can resolve the inputs; an isolated worktree is optional.
- Keep judgment in one reviewer context. Do not delegate review categories to independent reviewers with different thresholds.

## Normalize the comparison

Create one internal record containing the requested base reference and resolved tip, effective comparison base, target identity, available repository metadata, whether the input is a proposed submission, and any explicitly supplied prior report.

| Input | Identity and scope |
|---|---|
| Two Git revisions | Resolve both object IDs. For an explicit direct comparison, use the requested base as the effective base. For a pull request or branch-submission review, use the merge base as the effective base and record the requested base tip separately. |
| Working tree alone | Use `HEAD` as base. Record staged, unstaged, and untracked content as separate target layers. Treat the target as mutable unless the invoker supplies an immutable identity. |
| Revision and working tree | Use the named revision as base and record all working-tree layers. Treat the target as mutable unless the invoker supplies an immutable identity. |
| Two folders | Treat the first as base and second as target. Use supplied immutable identities when available; otherwise label both as mutable snapshots and mark automatic lineage unavailable. |
| Patch or diff | Use its supplied immutable identity when available; otherwise label it as a mutable snapshot and record which surrounding source is available. |
| Two artifact versions | Use immutable supplied identifiers; otherwise label them as mutable snapshots. |

If immutable input identities are equal, report `ready (no changes)` with no findings. If mutable snapshots have no observed differences, report `ready` and state that no differences were found without claiming identity continuity. Ask only when the comparison cannot be inferred safely.

If the current tool set cannot resolve or read both inputs, stop and return the exact immutable identities, diff, or source snapshots the invoker must provide. Never substitute the checked-out files for an inaccessible revision.

## Workflow

1. Apply the authority order in `references/standards.md`.
2. When repository metadata exists, discover the base input's delivery procedure.
3. Understand relevant base design before judging target changes.
4. Build an intended-outcome map from requested behavior, established contracts, and live consumers.
5. Record requirement provenance. Distinguish explicit user requirements, repository-enforced requirements, and reviewer-proposed ideas; the last category is not scope unless the user explicitly adopts it.
6. Inventory each changed artifact and record it as outcome-related, delivery-required, a finding candidate, or examined and non-defective.
7. Review in fixed order: outcomes and reachability; correctness, reliability, contracts, and applicable performance; design quality; tests, delivery, and artifacts.
8. Generate candidates, try to disprove each, merge shared root causes, then apply `references/severity-and-confidence.md`.
9. Write the report from `references/report-schema.md`.

Before judging a change, read the complete pre-change definitions from the base revision and the complete current definitions from the target — not merely the diff's surrounding context lines on either side — for each changed artifact, together with enclosing components, callers, callees, interfaces, implementations, tests, configuration consumers, document references, existing overlapping mechanisms, and adjacent lifecycle paths. A diff hunk under-determines behavior whenever the change touches part of a larger function, class, or file; fetch the full base-revision and target-revision files (e.g. `git show <base>:<path>` and `git show <target>:<path>`, or the base-side/target-side folder or artifact equivalent) whenever the diff's own context is insufficient to establish what the code did before the change or does now. Stop expanding only when behavior and consequence are proved or missing evidence is explicit.

## Finding gate

A blocking finding must:

- Be introduced, worsened, or exposed by the comparison
- Have a concrete current consequence, not a preferred alternative or speculative concern
- Have a static causal trace that excludes the obvious false-positive explanation
- Meet the normalized blocking severity and confidence rules in `references/severity-and-confidence.md`
- Name the smallest clean fix
- Provide both finding verification and author-run fix verification

For a design-only finding, identify an existing maintenance operation that must now understand, touch, or synchronize the changed artifact. Unused configuration or hooks block only when they misrepresent a current contract or impose demonstrated duplicate maintenance. These are additional evidence requirements; the finding must still satisfy every condition above, including attribution to the compared change and a concrete current consequence.

Merge candidates when one minimal patch resolves them as one causal chain. Keep them separate only when either defect can remain after the other's fix. For each design or artifact candidate, identify its current consumer, present consequence, independent clean fix, and overlap with other findings. Missing answers make it Advisory or investigation needed.

Never target a finding count. Time pressure, a late review, or a request for more issues does not lower the gate. Do not report personal style preferences or relabel Advisory improvements as defects.

### Reject these rationalizations

| Pressure | Required response |
|---|---|
| "Find at least N issues" | Apply the same gate; return zero when none qualify. |
| "The plan requires it" | Plans do not override code health or live evidence. |
| "A test covers it" | Check whether the oracle is independent and proves the contract. |
| "A different design is cleaner" | Report only a concrete defect in the submitted design. |
| "This is a later review, so find something new" | Revalidate prior findings and inspect only new or newly affected change. |
| "The analyzer warned" | Confirm the source path and consequence before admission. |

## Repeated reviews

Use only an explicitly supplied prior report. Never scan a directory and guess which report belongs to the comparison.

- Preserve the original base and record previous and current target identities.
- Compare previous target with current target.
- When the requested base tip changed, treat it as changed authoritative evidence and recheck affected target behavior even when the effective merge base is unchanged.
- Revalidate unresolved findings and inspect new or newly affected code.
- Preserve stable finding fingerprints.
- Record fixed findings briefly; remove disproved findings with an explanation.
- Do not mine unrelated unchanged code for smaller concerns.
- For identical inputs, add no finding from unchanged evidence. New evidence means an input, requirement, or authoritative source added or changed since the prior review. A finding missed in unchanged evidence is a prior-review correction and must be labeled explicitly.

If a request calls this a later review without an eligible prior report, state that limitation and perform the normal full review. When persistence is allowed, preserve one report per complete comparison identity using `references/report-schema.md`.

## Reference routing

Always read:

- `references/standards.md`
- `references/severity-and-confidence.md`
- `references/report-schema.md`

Read `references/correctness-and-reliability.md` for code, configuration, schema, interface, or executable-behavior changes. Read `references/design-quality.md` for human-authored code or documentation and for proposed submission reviewability. Read `references/tests-delivery-and-artifacts.md` when repository metadata exists or the change includes tests, scripts, tools, documentation, generated files, packaging, commit metadata, or pull-request metadata.

## Stop condition

Finish after every changed artifact is classified, every relevant behavior cluster has sufficient context, every applicable quality area is considered, and every candidate is admitted, deferred, or disproved. Do not keep searching to produce findings.
