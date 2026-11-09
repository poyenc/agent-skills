"""Argparse wiring. build_parser() is the single registry of subcommands.

Each module that owns subcommands exposes `register(subparsers)`, which adds its
subparsers and sets `func=<handler(args) -> int>` via `set_defaults`. To add a
module, import it here and append its `register` to REGISTRARS.
"""
import argparse
import sys

from . import config, github, gitops, lock, proc, state, team

NEEDS_CONFIG_EXIT = 3  # the lead prompt reads this as "no repository config"
CONFIG_OPTIONAL = ("validate", "notify")  # these report a missing config differently


def _register_validate(subparsers) -> None:
    p = subparsers.add_parser("validate", help="validate a repository config")
    p.add_argument("repo")
    p.set_defaults(func=_validate)


def _validate(args) -> int:
    errors = config.validate(config.load(args.repo), args.repo)
    for error in errors:
        print(error)
    return 1 if errors else 0


REGISTRARS = [_register_validate, state.register, gitops.register, lock.register, github.register,
              team.register]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pr-review")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for register in REGISTRARS:
        register(subparsers)
    return parser


def subcommand_names(parser: argparse.ArgumentParser) -> list[str]:
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return list(action.choices)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (proc.CommandError, gitops.CheckoutError) as e:
        print(f"pr-review: {e}", file=sys.stderr)
        return 1
    except config.BadRepository as e:
        print(f"pr-review: {e}", file=sys.stderr)
        return 2
    except config.ConfigError as e:
        print(f"pr-review: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        repo = getattr(args, "repo", None)  # notify and member-close take none
        path = config.config_path(repo) if repo else None
        if e.filename != str(path):
            raise
        print(f"pr-review: no config for {args.repo} at {path}", file=sys.stderr)
        return 1 if args.command in CONFIG_OPTIONAL else NEEDS_CONFIG_EXIT


if __name__ == "__main__":
    sys.exit(main())
