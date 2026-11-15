"""Project-wide settings: models, store, search, and budgets.

A project subclasses `Settings` in its `settings.py`. Because it is Python, a project can compute its settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from .models import Model

__all__ = ["Settings", "DEFAULT_MODELS"]

DEFAULT_MODELS: dict[str, Model] = {
    "choose": Model("typesafe/jev-1.13.0"),
    "generate": Model("fireworks/glm-5p3-flash", reasoning_effort="low"),
    "embed": Model("fireworks/qwen3-embedding-8b"),
}


class Settings:
    """Defaults for a project. Override any attribute on a subclass."""

    #: Where data lives. Relative paths are relative to the project folder.
    data_dir: ClassVar[str] = ".factoid"
    #: The model for each workload: choose, generate, embed, and (optional) rerank. A generation step can have its
    #: own model (situate, extract, repair, or discover); a step without one uses generate.
    models: ClassVar[dict[str, Model]] = DEFAULT_MODELS
    #: The system of record. `None` means `.factoid/store.db` under `data_dir`.
    store: ClassVar[Any] = None
    #: The search backend. `None` means the built-in local index in the project's SQLite store.
    search: ClassVar[Any] = None
    #: How many model calls run at once.
    concurrency: ClassVar[int] = 8
    #: Reuse stored responses for identical model requests.
    replay: ClassVar[bool] = True

    @classmethod
    def data_path(cls, project_root: Path) -> Path:
        path = Path(cls.data_dir)
        return path if path.is_absolute() else project_root / path

    @classmethod
    def all_models(cls) -> dict[str, Model]:
        merged = dict(DEFAULT_MODELS)
        merged.update(cls.models)
        return merged
