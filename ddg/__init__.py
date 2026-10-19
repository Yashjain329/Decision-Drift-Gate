"""Decision Drift Gate."""

from pathlib import Path

__version__ = "0.1.0"


def console_main():
    """Console-script wrapper: exit with the code ``ddg.cli.main`` returns."""
    from .cli import main

    raise SystemExit(main())


_HERE = Path(__file__).resolve().parent


def viewer_dir() -> Path:
    """The built browser viewer: ``ddg/_viewer`` when installed, ``web/out`` in a source checkout."""
    installed = _HERE / "_viewer"
    return installed if installed.is_dir() else _HERE.parent / "web" / "out"


def recorded_capture() -> Path:
    """The recorded model proposal used by ``--mode recorded``: installed copy first, then the checkout."""
    installed = _HERE / "_evidence" / "gemini-proposal.json"
    return installed if installed.is_file() else _HERE.parent / "evidence" / "gemini-proposal.json"
