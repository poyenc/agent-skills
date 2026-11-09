"""Watcher config: load with defaults, home and state directory, validation."""
import copy
import datetime
import os
import re
import shutil
from pathlib import Path

import yaml

from . import proc

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,9}$")
HARNESSES = ("claude", "pi")
LEAD_INVOKE = {"claude": "/pr-review", "pi": "/skill:pr-review"}  # pi: /skill:<name> (pi docs, skills.md)
PATH_KEYS = ("checkout", "persona_dir")
DURATION_UNITS = {"m": "minutes", "h": "hours", "d": "days"}
LOOP_EXPIRY = datetime.timedelta(days=7)  # Claude Code deletes recurring cron jobs after 7 days
WRITE_PERMISSIONS = ("WRITE", "MAINTAIN", "ADMIN")
# owner/name at the end of an https, ssh:// or scp-style (git@host:owner/name) remote URL.
ORIGIN_RE = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")
PERMISSION_QUERY = "query($owner: String!, $name: String!) " \
                   "{ repository(owner: $owner, name: $name) { viewerPermission } }"

LEAD_DEFAULTS = {"harness": "claude", "model": "Claude-Sonnet-5.5[1m]", "effort": "high"}

DEFAULTS = {
    "max_pr_duration": "3h",
    "max_reviews_per_fire": 4,
    "prefilter": {"include_drafts": False, "include_own_prs": False},
    "schedule": {"until": None},
    "persona_dir": "~/workspace/repo/claude-code-setting/agents",
    "team": {"lead": LEAD_DEFAULTS},
}


def config_dir() -> Path:
    """`~/.claude/pr-watch` (env PR_WATCH_HOME overrides): the watcher configs and their state."""
    return Path(os.environ.get("PR_WATCH_HOME", "~/.claude/pr-watch")).expanduser()


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if value is None and isinstance(out.get(key), (dict, int)):
            continue  # `prefilter:`, `schedule:` or `max_reviews_per_fire:` left empty: keep the defaults
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(name: str) -> dict:
    with open(config_dir() / f"{name}.yaml") as f:
        data = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, data)
    _drop_default_model_on_other_harness(cfg, data)
    for key in PATH_KEYS:
        if isinstance(cfg.get(key), str):
            cfg[key] = os.path.expanduser(cfg[key])
    return cfg


def _drop_default_model_on_other_harness(cfg: dict, data: dict) -> None:
    """A default model id is not valid on another harness: when the file sets a different
    lead harness without a model, leave the model unset so validate asks for it."""
    team = data.get("team")
    lead = team.get("lead") if isinstance(team, dict) else None
    if (isinstance(lead, dict) and lead.get("harness") not in (None, LEAD_DEFAULTS["harness"])
            and lead.get("model") is None):
        cfg["team"]["lead"].pop("model", None)


def lead_invoke(cfg: dict) -> str:
    """The skill invocation prefix a lead is started with."""
    lead = cfg["team"]["lead"]
    return lead.get("invoke") or LEAD_INVOKE[lead["harness"]]


def state_dir(cfg: dict) -> Path:
    path = config_dir() / cfg["name"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_duration(s: str) -> datetime.timedelta:
    match = re.fullmatch(r"(\d+)([mhd])", str(s))
    if not match:
        raise ValueError(f"bad duration {s!r}: expected <int>m, <int>h or <int>d")
    return datetime.timedelta(**{DURATION_UNITS[match[2]]: int(match[1])})


def _check_repo(cfg: dict) -> list[str]:
    repo = cfg.get("repo")
    if not repo:
        return ["repo: missing"]
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", str(repo)):
        return [f"repo: {repo!r} must be owner/name"]
    try:
        result = proc.run(["gh", "repo", "view", repo, "--json", "name"], check=False)
    except OSError as e:
        return [f"repo: cannot run gh: {e}"]
    if result.returncode != 0:
        return [f"repo: {repo} not reachable with gh"]
    return _check_permission(repo)


def _check_permission(repo: str) -> list[str]:
    """The leads resolve threads and approve, which needs write access."""
    owner, name = repo.split("/", 1)
    result = proc.run(["gh", "api", "graphql", "-f", f"owner={owner}", "-f", f"name={name}",
                       "-f", f"query={PERMISSION_QUERY}", "--jq", ".data.repository.viewerPermission"],
                      check=False)
    permission = result.stdout.strip()
    if result.returncode != 0:
        return [f"repo: cannot read the gh account's permission on {repo}"]
    if permission not in WRITE_PERMISSIONS:
        return [f"repo: the gh account has {permission or 'no'} permission on {repo}; "
                f"needs {', '.join(WRITE_PERMISSIONS)}"]
    return []


def _check_checkout(cfg: dict) -> list[str]:
    path, repo = cfg.get("checkout"), cfg.get("repo")
    if not path:
        return ["checkout: missing"]
    inside = proc.run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"], check=False)
    if inside.returncode != 0:
        return [f"checkout: {path} is not a work tree of a repository"]
    origin = proc.run(["git", "-C", path, "remote", "get-url", "origin"], check=False).stdout.strip()
    match = ORIGIN_RE.search(origin)
    if repo and (not match or f"{match[1]}/{match[2]}".lower() != str(repo).lower()):
        return [f"checkout: origin {origin!r} does not match repo {repo}"]
    return []


def _check_durations(cfg: dict) -> list[str]:
    errors = []
    schedule = cfg.get("schedule")
    if not isinstance(schedule, dict):
        return [f"schedule: must be a mapping with key every, got {schedule!r}"]
    if schedule.get("every") is None:
        errors.append("schedule.every: missing")
    else:
        try:
            if parse_duration(schedule["every"]) >= LOOP_EXPIRY:
                errors.append(f"schedule.every: {schedule['every']} must be shorter than 7d "
                              "(the loop job expires after 7 days)")
        except ValueError as e:
            errors.append(f"schedule.every: {e}")
    try:
        parse_duration(cfg.get("max_pr_duration"))
    except ValueError as e:
        errors.append(f"max_pr_duration: {e}")
    return errors


def _check_cap(cfg: dict) -> list[str]:
    cap = cfg.get("max_reviews_per_fire")
    if isinstance(cap, int) and not isinstance(cap, bool) and cap >= 1:
        return []
    return [f"max_reviews_per_fire: must be an integer >= 1, got {cap!r}"]


def _check_lead(lead) -> list[str]:
    if not isinstance(lead, dict):
        return [f"team.lead: must be a mapping with harness, model, effort, got {lead!r}"]
    errors = []
    harness = lead.get("harness")
    if harness not in HARNESSES:
        errors.append(f"team.lead.harness: {harness!r} must be one of {'|'.join(HARNESSES)}")
    elif not shutil.which(harness):
        errors.append(f"team.lead.harness: {harness} not installed")
    if "model" not in lead:
        errors.append("team.lead: model is required when harness is overridden")
    for key in ("model", "effort"):
        if key in lead and not lead[key]:
            errors.append(f"team.lead.{key}: missing")
    return errors


def _check_team(cfg: dict) -> list[str]:
    errors = []
    team = cfg.get("team") or {}
    if (team.get("supervisor") or {}).get("harness") != "claude":
        errors.append("team.supervisor.harness: supervisor must use harness claude")
    errors += _check_lead(team["lead"])
    if not (team.get("scanner") or {}).get("model"):
        errors.append("team.scanner.model: missing")
    return errors


def _check_persona(cfg: dict) -> list[str]:
    path = Path(cfg["persona_dir"]) / "orchestrator" / "system-prompt.md"
    return [] if path.is_file() else [f"persona_dir: {path} missing"]


def validate(cfg: dict, file_name: str) -> list[str]:
    """Problems with `cfg`, loaded from `<config dir>/<file_name>.yaml`; empty when valid."""
    errors = []
    if not NAME_RE.match(str(cfg.get("name", ""))):
        errors.append(f"name: {cfg.get('name')!r} must match {NAME_RE.pattern}")
    elif cfg["name"] != file_name:
        errors.append(f"name: {cfg['name']!r} must equal the config file name {file_name}.yaml")
    return (errors + _check_durations(cfg) + _check_cap(cfg) + _check_repo(cfg) + _check_checkout(cfg)
            + _check_team(cfg) + _check_persona(cfg))
