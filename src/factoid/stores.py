"""Store settings: where a project's system of record lives. SQLite by default, or Postgres.

    from factoid.stores import Postgres, Sqlite

    class Project(Settings):
        store = Sqlite(path=".factoid/acme.db")
        # or
        store = Postgres()  # URL from FACTOID_POSTGRES_URL, or libpq's PGHOST, PGUSER, PGPASSWORD, ...
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["Postgres", "Sqlite"]


@dataclass(frozen=True)
class Sqlite:
    """The system of record: a SQLite file. Relative paths are relative to the project folder."""

    path: str = ".factoid/store.db"

    def resolve(self, root: Path) -> Path:
        path = Path(self.path)
        return path if path.is_absolute() else root / path

    def open(self, root: Path) -> Any:
        from .store import Store

        return Store(self.resolve(root))


@dataclass(frozen=True)
class Postgres:
    """The system of record in Postgres, for many processes writing at once. Needs `factoid[postgres]`.

    `url` is a libpq connection string or URL. Leave it out to read it from the environment variable `env`
    (`FACTOID_POSTGRES_URL`), so credentials stay out of `settings.py`; with neither, libpq's own variables (`PGHOST`,
    `PGDATABASE`, `PGUSER`, `PGPASSWORD`) and `~/.pgpass` apply. Each project's tables live in its own `schema`,
    created on first use, so projects can share a database."""

    url: str | None = None
    schema: str = "factoid"
    env: str = "FACTOID_POSTGRES_URL"

    def conninfo(self) -> str:
        return self.url or os.environ.get(self.env, "")

    def open(self, root: Path | None = None) -> Any:
        from .postgres import PostgresStore

        return PostgresStore(self.conninfo(), schema=self.schema)

    def __repr__(self) -> str:  # never show a password from the URL
        return f"Postgres(schema={self.schema!r})"
