"""Decision Drift Gate."""

from pathlib import Path

__version__ = "0.1.0"


def console_main():
    """Console-script wrapper: exit with the code ``ddg.cli.main`` returns."""
    from .cli import main

    raise SystemExit(main())


def resource_root():
    """Directory that contains ``web/`` and ``evidence/`` (repo root or site-packages)."""
    return Path(__file__).resolve().parents[1]
