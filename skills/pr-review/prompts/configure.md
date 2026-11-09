# pr-review: configure a repository

You run in the user's own agent session. Create the repository config for `<owner>/<repo>`, or
change it, by asking the user questions. In this file, `pr-review` means
`<skill dir>/scripts/pr-review`, `<home>` is `$PR_REVIEW_HOME` if set, else
`~/.claude/pr-review`, and the config file is `<home>/<owner>/<repo>/config.yaml`.

## Rules

- Ask one question at a time. Every question carries a recommended value and a one-line reason;
  the user can answer "ok" to accept it.
- Do not ask what you can read. Check the filesystem, `gh`, and `which` first, and only ask when
  the answer is not there.
- Change only what the user asked to change, or what validation reported as a problem. Keep
  every other key and its value as it is.
- Never touch GitHub, the notes, saved reports or lock files.

## 1. Pick the mode

- The config file does not exist: new config, step 2.
- The file exists: existing config, step 3. When the lead procedure sent you here because the
  file cannot be read or `validate` reported problems, show those problems and ask only about
  the fields they name.

## 2. New config

Ask for each field in turn, in this order, with a recommended value:

1. `team.reviewer` and `team.architect`: do not ask for each key. Tell the user the defaults
   (reviewer: harness `pi`, model `amd-gateway/gpt-6.1-sol`, effort `high`; architect: harness
   `claude`, model `Claude-Opus-5.5[1m]`, effort `high`) and ask only whether to override any of
   them; recommend no. Write no `team` block unless they override. Write only the keys they
   override: a role's omitted keys keep the default. If they change a role's `harness` to the
   other harness (`claude` or `pi`), also ask for its `model` (for `pi`, a `provider/id`), since
   a default model id is not valid on another harness. Check a chosen harness with `which`.
3. `blocking_threshold` [`medium`]: `low|medium|high|critical`; findings at or above it become
   blocking inline threads, lower ones go into one non-blocking comment.
4. `dry_run` [`true`]: with `true`, the lead writes its would-be comments into the PR's notes
   file and changes nothing on GitHub. Recommend `true` until the user has read the notes of a
   first few reviews.
5. `skip_paths` [`[]`]: globs for generated or vendored files the team does not review.
6. `unrelated_change_lines` [`200`]: in a follow-up, changed lines unrelated to our threads
   above which the lead escalates instead of approving.
7. `persona_dir`: do not ask by default. Its default is
   `~/workspace/repo/claude-code-setting/agents`, which must hold `orchestrator/`, `reviewer/`
   and `architect/`, each with `system-prompt.md`. Ask for `persona_dir` only when the default
   does not exist on this machine, and write the answer into the config.

State, do not ask: `lock_stale_after: 3h` (a run's lock on a PR older than this counts as
abandoned, so a crashed run does not block that PR for good). Write it into the file so the
user can see and change it.

Then go to step 4.

## 3. Existing config

Show the current values from the file, ask what to change, and ask about each requested field
as in step 2 (recommended value, one question at a time). Change only that. Then go to step 4.

`dry_run` cannot change while a run holds a lock on this repository: the per-PR state
directory depends on it, and every CLI call of a running team re-reads the config, so a change
mid-run splits one PR's state between two directories. A run holds a lock while a file
`<home>/<owner>/<repo>/<PR>/lock` or `<home>/<owner>/<repo>-dry-run/<PR>/lock` exists. If one
exists, do not change `dry_run`: tell the user which PR is under review and to ask again once
that run has ended. A lock older than `lock_stale_after` belongs to an abandoned run; then
change `dry_run` once the user confirms no run is active. Other requested changes go ahead.

Turning `dry_run` off switches to a separate, clean state directory (`<owner>/<repo>` instead
of `<owner>/<repo>-dry-run`), so each PR's first real run is a real first review, with no
follow-ups to comments that were never posted. Say so when `dry_run` changes.

## 4. Validate the candidate, then replace the config

Every CLI call re-reads the config, so never leave a failing config at
`<home>/<owner>/<repo>/config.yaml`. Validate a candidate in a temporary home instead:

1. Create a temp directory (`mktemp -d`) and write the full candidate config to
   `<tmpdir>/<owner>/<repo>/config.yaml` (for an existing config: the current file with only
   the requested changes, keeping its other keys and comments).
2. Run `PR_REVIEW_HOME=<tmpdir> pr-review validate <owner>/<repo>`. It prints one line per
   problem and exits non-zero. It checks: the repository is reachable with `gh` and the `gh`
   account has write access to it (WRITE, MAINTAIN or ADMIN), `team.reviewer` and
   `team.architect` (defaults applied for what the file omits) each have an installed harness
   (`claude` or `pi`), a model (required when the harness is overridden) and an effort,
   `blocking_threshold`, `dry_run`, `skip_paths`, `unrelated_change_lines` and
   `lock_stale_after` have valid values, and the persona files under `persona_dir` exist.
3. On a non-zero exit, tell the user each problem, ask again for that field only (with a
   recommended value), update the candidate, and repeat item 2. The real config file stays
   untouched meanwhile.
4. On exit 0, create `<home>/<owner>/<repo>/` if needed and move the candidate to
   `<home>/<owner>/<repo>/config.yaml`. Remove the temp directory.

Do not declare done until the validated file is in place. If the user cannot fix a problem
now, say which problem remains and that the real config was left unchanged (for a new config:
not created).

## 5. Finish

Changes apply to the next run on this repository. Finish with a short summary: the file path,
what changed, and the validate result (exit 0 on the candidate before it was moved into
place). If the lead procedure sent you here, go back to it and continue where it left off.
