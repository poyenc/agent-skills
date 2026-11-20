# Round-one brief (send to the reviewer and the architect)

Fill the placeholders, then send the same text to both agents. Keep it this short: the agents'
system prompts already carry their review standards, so do not restate them and do not assign
areas.

```
Review pull request <PR number> of <owner>/<repo> as a PR submission.
Base tip: <base tip sha>. Head: <head sha>. The PR is checked out in <worktree path>.
Read-only: edit nothing, post nothing.

Review the whole PR through your own lens, reading full files, callers, tests, and the design
documents that cover the touched code, not only the diff.

Facts only. Report a statement (comment, document, PR description, name) only if it is false,
stale, or contradicts the code, and any other defect with a concrete consequence. Do not report,
and do not propose, rewording, renames, restructured prose, or a rewrite of a true statement.
A name is an issue only if it states something false about the code.

This is the only full review of this head. Be exhaustive now: a defect you miss can later be
raised only as a labeled correction to this review. List every changed file with one
disposition: finding, examined and clean, or not examined (with the reason).

Where the lead marks care is needed (claims and starting points, not limits; verify them and
cover everything else too):
<PR brief>

Write the report to <report path>. When it is written, send a short message to <lead name>
saying where it is. Include for every finding: file:line, severity, confidence, evidence.
```
