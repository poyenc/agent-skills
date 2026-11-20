# Review task: PR {{PR}} in {{REPO}}

The lead of a PR review team, at herdr pane `{{LEAD}}`, asks you to review GitHub pull request
{{PR}} in {{REPO}}. The lead verifies your findings and decides what is posted; you only report.

## Inputs

- Checkout: {{CHECKOUT}}, already on the PR head. Other team members read it at the same time.
- Base (merge base with the target branch): {{BASE}}
- Head: {{HEAD}}
- The PR's change: `git -C {{CHECKOUT}} diff {{BASE}} {{HEAD}}`. This is a branch-submission
  review with {{BASE}} as the effective base. Use `git -C {{CHECKOUT}} show <commit>:<path>` for
  full files on either side.
- Mode: {{MODE}}
- Your files (other files are context only):

{{FILES}}

- Focus for this PR: {{FOCUS}}
- Blocking threshold: {{THRESHOLD}}
- Threads to re-check (follow-up only):

{{THREADS}}

## Rules

- Static review only. Read code; never build, compile, run tests, benchmarks, profilers or any
  repository code, and never use a GPU.
- Do not change the checkout: no checkout, switch, reset, stash, commit, fetch or file edits.
- Do not post, comment, approve or change anything on GitHub.
- Severity threshold for this review: a finding at or above {{THRESHOLD}} severity is blocking;
  a confirmed finding below it is non-blocking. This replaces your default rule that every
  confirmed Low-or-higher defect blocks. Report both kinds, each with its severity.
- Reading scope: read the PR's diff and, for each changed artifact, its full definition on both
  sides (base and head). Beyond that read only the direct callers and the direct callees of the
  changed code (one hop). Read anything further only when a specific finding you are already
  forming needs it, and name that finding and why in your report next to the evidence. Do not
  read unrelated files, whole directories, other tests, docs or history to "get context". This
  replaces your default instruction to read enclosing components, interfaces, implementations,
  tests, configuration consumers, document references, overlapping mechanisms and adjacent
  lifecycle paths.
- Performance: state the mechanism and what the author should measure. Never give a number
  (no estimated speedup, cycle count or percentage).

## Mode first-review

Review the change to your files as one whole, under your usual standard, with the focus above.
For each finding give: repository-relative path, line and side (`RIGHT` with the head line
number; `LEFT` with the base line number only for a removed line), severity, confidence with
its evidence, what is wrong, the concrete consequence, and the clean fix. Say whether the line
is inside a diff hunk.

## Mode follow-up

Check only the threads listed above, against the code at {{HEAD}} and the author's replies. Do
not report anything else: a follow-up never raises new issues.

Saved reports: {{SAVED_REPORTS}}. If that is `none` (for example threads opened by hand), read
files as needed. Otherwise it is a directory holding our team's final reports and critiques
from the first review: read them for the evidence behind each thread, then the commits since
our last run, `git -C {{CHECKOUT}} diff <last-reviewed-sha> {{HEAD}}` (the last reviewed head
is given with each thread). Read other files only where a thread's saved evidence points. A
thread the saved reports do not cover: read files as needed for it.

For each thread give its ID and one verdict with evidence:

- `addressed`: the issue is fixed, or the remaining gap is acceptable;
- `partly`: some of it is still open (say what), including a thread the author resolved
  without fixing it;
- `author-right`: the author's reply shows our comment was wrong or missed something.

Also say whether the author's change broke the lines under the comment.

## Report

Write your complete report to {{REPORT_PATH}} (create its directory if needed), then notify the
lead with the path only:

```bash
{{CLI}} notify {{LEAD}} "report {{REPORT_PATH}}"
```

Then wait. If the lead messages you with a question, answer it the same way with
`{{CLI}} notify {{LEAD}} "<answer>"`. If you cannot finish the task, notify the lead with the
reason instead of a report.

## Cross-review (first review only)

After your first-review report, the lead runs one exchange with the architect's report. Do
each step once, when the lead asks for it.

**Critique.** The lead sends `critique <report path> into <critique path>`, naming the
architect's report on the whole PR. Read it and write a short critique to the critique path:
what is wrong, what is missing and what you disagree with, each with its evidence. Do not edit
the report you read. Then notify the lead:

```bash
{{CLI}} notify {{LEAD}} "critique <critique path>"
```

**Revise.** The lead then sends `revise <critique path>`, naming the architect's critique of
your report. Revise your own report, {{REPORT_PATH}}, in place, so it stays your complete
report: fix what the critique showed, or say why a disputed point stands. You may add findings
only in your own area (correctness of your files, under the focus above) that you learned about
from the other report; a point in the other role's area belongs in your critique. Never edit the
other report or the critiques. Then notify the lead:

```bash
{{CLI}} notify {{LEAD}} "revised {{REPORT_PATH}}"
```
