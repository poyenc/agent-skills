# Later-round brief (after the author pushed new commits)

Send the same text to both agents. The ledger and the last consolidated review are the explicit
prior report.

```
Review round <K> of pull request <PR number> of <owner>/<repo> as a PR submission.
Base tip: <base tip sha>. Previous reviewed head: <previous head sha>. New head: <head sha>.
The PR is checked out in <worktree path>. Read-only: edit nothing, post nothing.

Prior report: <ledger path> and <last consolidated review path>.

1. Revalidate every finding in the ledger whose status is open or posted: fixed, still open, or
   disproved, with evidence from the new head.
2. Review only <previous head sha>..<head sha> and whatever it newly affects. Do not mine
   unchanged code for new concerns.
3. Do not re-raise a finding the ledger marks declined, deferred, or posted. Compare each new
   finding with the ledger fingerprints (file, symbol, root cause); the same cause as a listed
   finding is that finding, not a new one.
4. A new finding on code that was already in the previous diff is a correction to the earlier
   review: label it as such and say why it was missed.

Facts only. Report a statement (comment, document, PR description, name) only if it is false,
stale, or contradicts the code, and any other defect with a concrete consequence. Do not report,
and do not propose, rewording, renames, restructured prose, or a rewrite of a true statement.
A name is an issue only if it states something false about the code.

List every file changed in the delta with one disposition: finding, examined and clean, or not
examined (with the reason).

Care marks for this delta (claims, not limits):
<PR brief for the delta>

Write the report to <report path>. When it is written, send a short message to <lead name>
saying where it is. Include for every finding: file:line, severity, confidence, evidence.
```
