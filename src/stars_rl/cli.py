"""Command-line entry point for STARS-RL."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from stars_rl import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line parser."""
    parser = argparse.ArgumentParser(
        prog="stars-rl",
        description="Optimization-based STARS orchestration with RL weight selection.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    doctor = commands.add_parser("doctor", help="Check the installed optimization backend")
    doctor.add_argument("--solver", action="store_true", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return its success status."""
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        from stars_rl.optimization.doctor import diagnose
        report = diagnose()
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if report["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

