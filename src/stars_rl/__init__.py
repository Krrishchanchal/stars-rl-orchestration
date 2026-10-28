"""STARS-RL orchestration package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("stars-rl")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0+unknown"

__all__ = ["__version__"]

