# pr-watch: configure a watcher

You run in the user's own agent session. Create a watcher config, or change one, by asking the user questions. In this file, `pr-watch` means `<skill dir>/scripts/pr-watch`, and `<home>` is `$PR_WATCH_HOME` if set, else `~/.claude/pr-watch`. The config file is `<home>/<name>.yaml`.

A watcher config holds only what the supervisor and its leads need to be started: which PRs to pick, when, and with which agents. How a PR is reviewed (the review team, the blocking threshold, dry run, paths to skip) is the per-repository config of the `pr-review` skill, which every lead uses; it is not set here.

## Rules

- Ask one question at a time. Every question carries a recommended value and a one-line reason; the user can answer "ok" to accept it.
- Do not ask what you can read. Check the filesystem, `gh`, and `which` first, and only ask when the answer is not there.
- Change only what the user asked to change. Keep every other key and its value as it is.
- Never touch GitHub or the record, except for the clear-scan-mark step below. Never run the `pr-review` skill's commands or read or write its files.

## 1. Pick the mode

- No name given, or `<home>/<name>.yaml` does not exist: new watcher, step 2.
- The file exists: existing watcher, step 3.

## 2. New watcher

Ask for each field in turn, in this order, with a recommended value:

1. `name`: lowercase letter first, then up to 9 letters, digits or hyphens (`^[a-z][a-z0-9-]{0,9}$`). It names the record directory `<home>/<name>/` and is part of the lead's agent name. Recommend a short word for the topic, for example `fmha`.
2. `repo`: `owner/name`. Check it with `gh repo view <repo> --json name`. Then tell the user: each lead uses the `pr-review` skill, which needs its own config for this repository; if they have not done so yet, they should run `/pr-review <owner>/<repo> <PR>` once for this repository (any PR) before starting the watcher. Until then every lead stops at once and reports `needs-config`. You cannot check this yourself.
3. `checkout`: the worktree every lead reviews in. Each run discards every uncommitted and untracked file in it before checking out the PR, so it must be a dedicated worktree of a local clone of `repo` that nothing else uses. Recommend `~/workspace/worktree/pr-watch-<name>`. If the path does not exist, ask the user to create such a worktree there (or give another path) and continue once it exists.
4. `prefilter`: cheap `gh`-side filters, all optional. Ask in turn:
   - `labels` (list): recommend none unless the repository labels its areas.
   - `base`: recommend the repository's default branch.
   - `authors` (list): recommend none.
   - `include_drafts`: recommend `false` (a draft gets its first review once it is marked ready).
   - `include_own_prs`: recommend `false` (PRs authored by the `gh` account's user are classified but not queued).
5. `interest`: plain-language criteria the Haiku scanner applies to a PR's title, description and changed files; the lead also checks a PR against it before reviewing. Recommend wording that names the area and says incidental touches do not count, for example the one in `examples/fmha.yaml`. Tell the user the scanner leans towards "interesting" when unsure.
6. `schedule.every`: loop interval, `<int>m|h|d`, shorter than `7d`. Recommend `24h`. Then `schedule.until` (optional end time): recommend none.
7. `team`: one block per role. Recommend the values of `examples/fmha.yaml`:
   - `team.supervisor` `claude sonnet medium`: the session the user runs `/pr-watch <name>` in. Its harness must be `claude` (it schedules its loop with `/loop` and starts the scanner as a subagent).
   - `team.scanner` model `haiku`: a Claude subagent, so it takes only a model.
   - `team.lead`: the agent started in each PR's tab. Do not ask for its keys: tell the user the default (harness `claude`, model `Claude-Sonnet-5.5[1m]`, effort `high`) and ask only whether to override it; recommend no, and write no `team.lead` entry unless they override. Write only the keys they override: the omitted keys keep the default. If they change `harness` to the other harness (`claude` or `pi`), also ask for its `model` (for `pi`, a `provider/id`), since a default model id is not valid on another harness. Do not ask for `invoke` (how the lead is told to use the `pr-review` skill): it defaults to `/pr-review` for `claude` and `/skill:pr-review` for `pi`; set it only if the user says their lead harness invokes skills differently.
   Check each chosen harness with `which`.
8. `max_reviews_per_fire`: the most leads one fire starts, to bound token spend; other interesting PRs wait for the next fire, oldest first. Ask whether to cap and what N (an integer 1 or more). Recommend `4` (the default; leave the key out to keep it). There is no "no cap" value: for practically none, give a large number.
9. `persona_dir`: do not ask. The default is `~/workspace/repo/claude-code-setting/agents`. Ask for a path only when `<persona_dir>/orchestrator/system-prompt.md` (the lead's persona) does not exist on this machine, and write the answer into the config.

State, do not ask: `max_pr_duration: 3h` (the supervisor flags a lead that runs longer and starts no other PR until the user decides). Write it into the file so the user can see and change it.

Then go to step 4.

## 3. Existing watcher

Show the current values from the file, ask what to change, and ask about each requested field as in step 2 (recommended value, one question at a time). Change only that. Then go to step 4.

If the user asks for a review setting (review team, threshold, dry run, paths to skip), tell them it belongs to the `pr-review` skill's config for the repository, not to the watcher.

## 4. Validate the candidate, then replace the config

A running supervisor re-reads the config on every fire, so never leave a failing config at `<home>/<name>.yaml`. `pr-watch validate <name>` reads `$PR_WATCH_HOME/<name>.yaml`, so validate a candidate in a temp directory:

1. Create a temp directory (`mktemp -d`) and write the full candidate config to `<tmpdir>/<name>.yaml` (for an existing watcher: the current file with only the requested changes, keeping its other keys and comments).
2. Run `PR_WATCH_HOME=<tmpdir> pr-watch validate <name>`. It prints one line per problem and exits non-zero. It checks: the name rule and that `name` equals the file name, `schedule.every` and `max_pr_duration` are durations (`every` shorter than `7d`), `max_reviews_per_fire` is an integer 1 or more when set, the repository is reachable with `gh` and the `gh` account has write access to it (WRITE, MAINTAIN or ADMIN), `checkout` is a worktree whose origin is exactly `repo`, the supervisor harness is `claude`, the lead harness (default applied when omitted) is installed and has a model (required when the harness is overridden) and an effort, the scanner has a model, and the lead's persona file exists.
3. On a non-zero exit, tell the user each problem, ask again for that field only (with a recommended value), update the candidate, and repeat step 2. The real config file stays untouched meanwhile.
4. On exit 0, create `<home>` if needed and move the candidate to `<home>/<name>.yaml`. Remove the temp directory.

Do not declare done until the validated file is in place. If the user cannot fix a problem now, say which problem remains and that the real config was left unchanged (for a new watcher: not created).

## 5. After changing `interest` or `prefilter`

Ask whether to clear the scan mark so older PRs are classified again under the new criteria (recommend yes when the criteria widened, no when they only narrowed). On yes, run `pr-watch clear-scan-mark <name>`. The next fire then re-classifies every open PR; PRs already recorded keep their record.

## 6. Tell the user when changes apply

A running supervisor re-reads the config at the start of each fire, and opening a PR's tab reads it again:

- Apply at once (opening a PR's tab reads the config): `max_reviews_per_fire`.
- Apply on the next fire: `interest`, `prefilter`, `schedule.until`, `max_pr_duration`, `checkout`, `persona_dir`, `team.scanner` and `team.lead`. A lead already running keeps its settings.
- Need a restart: `schedule.every` is fixed when the loop is scheduled. Tell the user to stop the watcher in its supervisor session and run `/pr-watch <name>` again. `team.supervisor` describes that session; change the session itself to match.

Finish with a short summary: file path, what changed, validate result (exit 0 on the candidate before it was moved into place), and which changes are pending a restart. Do not start or stop the watcher unless the user asks.
