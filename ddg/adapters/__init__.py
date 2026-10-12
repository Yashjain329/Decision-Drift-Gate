"""Adapter registry. An adapter is a module exposing the functions listed in REQUIRED."""

from __future__ import annotations

from types import ModuleType

from . import job_client, python_function

REQUIRED = ("NAME", "validate_body", "source_path", "observe", "ordinary", "expected_case")
_REGISTRY: dict[str, ModuleType] = {m.NAME: m for m in (job_client, python_function)}
for _module in _REGISTRY.values():
    missing = [name for name in REQUIRED if not hasattr(_module, name)]
    if missing:
        raise ImportError(f"Adapter {_module.__name__} is missing {missing}")


def names() -> list[str]:
    return sorted(_REGISTRY)


def get(name: str) -> ModuleType:
    if not isinstance(name, str) or name not in _REGISTRY:
        raise ValueError("Unsupported adapter")
    return _REGISTRY[name]
