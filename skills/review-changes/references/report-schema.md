# Review report

Write for a human maintainer with limited attention. Lead with the verdict and findings. Omit empty sections except review identity and verdict. Write findings in plain language — short sentences, the key point first, one concern at a time — the same standard the review applies to documentation.

## Header

For immutable Git comparisons:

```markdown
# Change review

- Verdict: ready | ready (no changes) | not ready
- Comparison kind: direct Git | branch submission
- Requested base ref: <ref name, when supplied>
- Requested base commit: <full object ID>
- Effective base: <full object ID; requested base for direct comparison, merge base for branch-submission review>
- Reviewed head commit: <full target object ID>
- Previous reviewed head commit: <full object ID, only for repeated review>
- Previous report: <safe logical name, only when supplied>
```

For a Git working-tree target:

```markdown
# Change review

- Verdict: ready | ready (no changes) | not ready
- Base commit: <full object ID>
- Target identity: <supplied immutable identity | mutable working-tree snapshot>
- Included layers: staged, unstaged, untracked
- Previous target identity: <supplied immutable identity, only for repeated review>
- Previous report: <safe logical name, only when supplied>
```

Do not emit `Reviewed head commit:` for a mutable target. For non-Git comparisons, replace the Git fields with supplied immutable base and target identities. If either identity is unavailable, label it `mutable snapshot`; do not claim identical-input detection or lineage continuity.

Never expose absolute local paths, usernames, machine names, agent activity, or internal task counts in the report.

For immutable Git inputs, use full object IDs. When persistence is requested, use `change-review-<comparison-kind>-<full-requested-base-commit>-<full-effective-base>-<full-target>.md`. For non-Git or mutable inputs, use the filename supplied by the invoker; otherwise return the report without persisting it.

Accept a prior report only when explicitly supplied and its recorded identities match the intended lineage. A changed requested base tip is new evidence even when the effective merge base is unchanged; inspect base-side changes that can affect the target. Never select a prior report by scanning a directory.

## Blocking findings

Order findings by severity, then stable fingerprint. Use repository-relative paths. Merge findings that share a root cause and clean fix.

```markdown
## <fingerprint>: <concise title>

- Severity: Low | Medium | High | Critical
- Project severity: <native label and mapping, only when the repository defines one>
- Confidence: <80-100>% - <evidence basis>
- Location: `relative/path:line` and symbol
- Location side: RIGHT | LEFT
- Violated requirement: <repository contract, explicit requirement, or applicable standard>
- Trigger: <supported condition or maintenance operation>
- Evidence: <concise source trace proving the issue and excluding the obvious false-positive explanation>
- Impact: <affected behavior, scope, recovery, and workaround>
- Clean fix: <smallest design-consistent correction>
- Finding verification: <static steps that reproduce or prove the defect>
- Fix verification: <author-run check that fails before, passes after, and protects the contract>
```

Build the fingerprint from repository-relative path, changed symbol or artifact, violated invariant, and consequence. Keep it stable across line movement and wording changes.

Use `RIGHT` for target-side or unchanged locations. Use `LEFT` only for deleted files or removed lines whose evidence exists solely in the effective base. A `LEFT` finding links and validates against the effective base; all others link and validate against the reviewed head commit.

## Investigation needed

List only 60-79% confidence concerns. State the missing decisive evidence. These items do not block readiness.

## Resolved since prior review

For repeated review, list prior fingerprints resolved in the new target and the static evidence. Do not repeat full old findings.

## Pre-existing critical safety observations

List only critical safety defects encountered while reading necessary context that the compared change neither introduced, worsened, nor exposed. They do not affect this change's verdict. If the change makes the defect reachable or expands its impact, treat it as a normal blocking finding instead.

## Static-review limits

List applicable behavior that source alone cannot establish and the author-run verification needed. Do not claim that any command ran.

## Evidence coverage

Briefly name applicable quality areas and important repository procedures examined. For human-authored code or documentation changes, state in one sentence whether the change keeps the design easy for a human maintainer to follow. Do not dump a completed checklist, raw commands, logs, task narration, gate names, or counts used to perform the review.

## Readiness rule

Apply the normalized blocking rule defined in `severity-and-confidence.md`. Use `ready (no changes)` when input identities are equal. Investigation-needed items and static limits remain explicit but do not change readiness.

Never invent findings to avoid a ready verdict.
