"""Argparse wiring. build_parser() is the single registry of subcommands.

Each module that owns subcommands exposes `register(subparsers)`, which adds its
subparsers and sets `func=<handler(args) -> int>` via `set_defaults`. To add a
module, import it here and append its `register` to REGISTRARS.
"""
import argparse
import sys

from . import config, proc, record, scan, team


def _register_validate(subparsers) -> None:
    p = subparsers.add_parser("validate", help="validate a watcher config")
    p.add_argument("name")
    p.set_defaults(func=_validate)


def _validate(args) -> int:
    errors = config.validate(config.load(args.name), args.name)
    for error in errors:
        print(error)
    return 1 if errors else 0


REGISTRARS = [_register_validate, record.register, scan.register, team.register]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pr-watch")
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
    except proc.CommandError as e:
        print(f"pr-watch: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        path = config.config_dir() / f"{args.name}.yaml"
        if e.filename != str(path):
            raise
        print(f"pr-watch: no config for {args.name} at {path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
