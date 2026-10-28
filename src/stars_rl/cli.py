"""Command-line entry point for STARS-RL."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from stars_rl import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the public command-line parser."""
    parser = argparse.ArgumentParser(
        prog="stars-rl",
        description="Optimization-based STARS orchestration with RL weight selection.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return its success status."""
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

