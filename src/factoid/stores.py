"""Store settings. In v1, Factoid stores data in SQLite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["Sqlite"]


@dataclass(frozen=True)
class Sqlite:
    """The system of record: a SQLite file. Relative paths are relative to the project folder."""

    path: str = ".factoid/store.db"

    def resolve(self, root: Path) -> Path:
        path = Path(self.path)
        return path if path.is_absolute() else root / path
