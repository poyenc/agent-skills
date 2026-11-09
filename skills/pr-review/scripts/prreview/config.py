"""Repository config: load with defaults, per-repository directory, validation."""
import copy
import datetime
import os
import re
import shutil
from pathlib import Path

import yaml

from . import proc

THRESHOLDS = ("low", "medium", "high", "critical")
HARNESSES = ("claude", "pi")
TEAM_ROLES = ("reviewer", "architect")
PERSONA_ROLES = ("orchestrator", "reviewer", "architect")
DURATION_UNITS = {"m": "minutes", "h": "hours", "d": "days"}
WRITE_PERMISSIONS = ("WRITE", "MAINTAIN", "ADMIN")
REPO_RE = re.compile(r"[\w][\w.-]*/[\w][\w.-]*")
PERMISSION_QUERY = "query($owner: String!, $name: String!) " \
                   "{ repository(owner: $owner, name: $name) { viewerPermission } }"

TEAM_DEFAULTS = {
    "reviewer": {"harness": "pi", "model": "amd-gateway/gpt-6.1-sol", "effort": "high"},
    "architect": {"harness": "claude", "model": "Claude-Opus-5.5[1m]", "effort": "high"},
}

DEFAULTS = {
    "dry_run": True,
    "blocking_threshold": "medium",
    "skip_paths": [],
    "unrelated_change_lines": 200,
    "lock_stale_after": "3h",
    "persona_dir": "~/workspace/repo/claude-code-setting/agents",
    "team": TEAM_DEFAULTS,
}


class ConfigError(Exception):
    """config.yaml exists but cannot be read as a mapping."""


class BadRepository(ValueError):
    """The repository argument is not owner/name."""


def home() -> Path:
    return Path(os.environ.get("PR_REVIEW_HOME", "~/.claude/pr-review")).expanduser()


def repo_dir(repo: str) -> Path:
    """`<home>/<owner>/<repo>`; raises BadRepository unless `repo` is owner/name."""
    if not REPO_RE.fullmatch(repo) or ".." in repo:
        raise BadRepository(f"bad repository {repo!r}: expected owner/name")
    return home() / repo


def config_path(repo: str) -> Path:
    return repo_dir(repo) / "config.yaml"


def load(repo: str) -> dict:
    """Defaults merged with config.yaml; FileNotFoundError when missing, ConfigError when malformed."""
    path = config_path(repo)
    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"{path}: invalid YAML: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping, got {type(data).__name__}")
    cfg = {**copy.deepcopy(DEFAULTS), **data}
    cfg["team"] = _merge_team(data.get("team"))
    if isinstance(cfg["persona_dir"], str):
        cfg["persona_dir"] = os.path.expanduser(cfg["persona_dir"])
    return cfg


def _merge_role(default: dict, spec: dict) -> dict:
    """Per-key merge of a role's settings over its defaults.

    A default model id is not valid on another harness, so when the harness is overridden
    to a different one the model is not defaulted (validation then requires it).
    """
    given = {k: v for k, v in spec.items() if v is not None}
    merged = {**default, **given}
    if merged["harness"] != default["harness"] and "model" not in given:
        del merged["model"]
    return merged


def _merge_team(team) -> object:
    """`team` with each role's settings merged over TEAM_DEFAULTS; wrong types are left for validate."""
    if team is None:
        team = {}
    if not isinstance(team, dict):
        return team
    merged = {**team}
    for role, default in TEAM_DEFAULTS.items():
        spec = team.get(role)
        if spec is None:
            spec = {}
        merged[role] = _merge_role(default, spec) if isinstance(spec, dict) else spec
    return merged


def parse_duration(s: str) -> datetime.timedelta:
    match = re.fullmatch(r"(\d+)([mhd])", str(s))
    if not match:
        raise ValueError(f"bad duration {s!r}: expected <int>m, <int>h or <int>d")
    return datetime.timedelta(**{DURATION_UNITS[match[2]]: int(match[1])})


def _check_repo(repo: str) -> list[str]:
    if not REPO_RE.fullmatch(repo):
        return [f"repo: {repo!r} must be owner/name"]
    try:
        result = proc.run(["gh", "repo", "view", repo, "--json", "name"], check=False)
    except OSError as e:
        return [f"repo: cannot run gh: {e}"]
    if result.returncode != 0:
        return [f"repo: {repo} not reachable with gh"]
    return _check_permission(repo)


def _check_permission(repo: str) -> list[str]:
    """Resolving threads and approving need write access."""
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


def _check_team(cfg: dict) -> list[str]:
    team = cfg["team"]
    if not isinstance(team, dict):
        return [f"team: must be a mapping with keys {', '.join(TEAM_ROLES)}, got {team!r}"]
    errors = []
    for role in TEAM_ROLES:
        spec = team[role]
        if not isinstance(spec, dict):
            errors.append(f"team.{role}: must be a mapping with harness, model, effort, got {spec!r}")
            continue
        harness = spec.get("harness")
        if harness not in HARNESSES:
            errors.append(f"team.{role}.harness: {harness!r} must be one of {'|'.join(HARNESSES)}")
        elif not shutil.which(harness):
            errors.append(f"team.{role}.harness: {harness} not installed")
        if "model" not in spec:
            errors.append(f"team.{role}: model is required when harness is overridden")
        for key in ("model", "effort"):
            if key in spec and not spec[key]:
                errors.append(f"team.{role}.{key}: missing")
    return errors


def _check_files(cfg: dict) -> list[str]:
    if not isinstance(cfg["persona_dir"], str):
        return [f"persona_dir: must be a path string, got {cfg['persona_dir']!r}"]
    persona_dir = Path(cfg["persona_dir"])
    return [f"persona_dir: {persona_dir / role / 'system-prompt.md'} missing"
            for role in PERSONA_ROLES if not (persona_dir / role / "system-prompt.md").is_file()]


def _check_scalars(cfg: dict) -> list[str]:
    errors = []
    if not isinstance(cfg["dry_run"], bool):
        errors.append(f"dry_run: must be true or false, got {cfg['dry_run']!r}")
    skip = cfg["skip_paths"]
    if not isinstance(skip, list) or not all(isinstance(x, str) for x in skip):
        errors.append(f"skip_paths: must be a list of strings, got {skip!r}")
    lines = cfg["unrelated_change_lines"]
    if isinstance(lines, bool) or not isinstance(lines, int):
        errors.append(f"unrelated_change_lines: must be an integer, got {lines!r}")
    return errors


def validate(cfg: dict, repo: str) -> list[str]:
    """Problems with `cfg`, loaded from `<repo_dir(repo)>/config.yaml`; empty when valid."""
    errors = _check_scalars(cfg)
    if cfg["blocking_threshold"] not in THRESHOLDS:
        errors.append(f"blocking_threshold: {cfg['blocking_threshold']!r} not one of {'|'.join(THRESHOLDS)}")
    try:
        parse_duration(cfg["lock_stale_after"])
    except ValueError as e:
        errors.append(f"lock_stale_after: {e}")
    return errors + _check_repo(repo) + _check_team(cfg) + _check_files(cfg)
