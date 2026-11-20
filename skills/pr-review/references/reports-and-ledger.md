# Reports and ledger (kept across sessions)

## Where

`${XDG_DATA_HOME:-$HOME/.local/share}/pr-review/<owner>/<repo>/pr<N>/`, created with `mkdir -m 700 -p`. Nothing is written into the repository under review.
`<owner>/<repo>` is the PR's base repository (`gh repo view --json nameWithOwner`), not a fork's
remote. If the target repository's CLAUDE.md names its own scratch directory, use that instead.

```
ledger.md
round<K>-<head sha>-reviewer-report.md
round<K>-<head sha>-architect-report.md
round<K>-<head sha>-consolidated-review.md
```

Round files are never edited after they are written. `ledger.md` is updated in place, by the
lead only; the council never edits it. No ledger for the PR means round one; otherwise the newest
round file gives the previous head sha.

## Ledger rows

One row per finding: stable ID, fingerprint (file, symbol, root cause; never a line number),
round first seen, status, and a note.

Status: open, fixed, disproved, posted (with the comment link), declined by the owner (with
their reason in one line), deferred, wording only.

A finding the owner declined stays closed in later rounds unless the code it concerns changes.
Match a new finding against the fingerprints so a rephrased old issue is recognized as the old one.
Before relying on the ledger, cross-check its posted rows against the live PR comments with
`gh api`; the ledger is a claim.

## Consolidated review layout

1. Verdict line and what was and was not verified.
2. Findings, most severe first, nothing dropped: the council's evidence, who reported it, and
   whether the lead verified it against the repo or it remains a claim.
3. Corrections to an earlier round (round two and later), with why each was missed.
4. Wording only, not an issue: items the council reported as wording or renames despite the
   brief. Never findings, never comments.
5. Coverage: every changed file with its disposition from both reports. A file or care mark with
   no disposition goes back to the council before the review is consolidated.
