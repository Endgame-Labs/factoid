"""A project's stable id, which names where its own keys live: `~/.factoid/projects/<id>/.env`.

The id is written once into the project's `pyproject.toml` (`[tool.factoid] id = "..."`) and committed, so a moved or
renamed checkout, or a second checkout of the same project, finds the same keys. Keys stay out of the working tree,
where coding agents and build tools read files.
"""

from __future__ import annotations

import re
import secrets
import tomllib
from pathlib import Path

__all__ = ["new_project_id", "project_id"]


def new_project_id(package: str) -> str:
    return f"{re.sub(r'[^a-z0-9]+', '-', package.lower()).strip('-') or 'project'}-{secrets.token_hex(4)}"


def project_id(root: Path, *, create: bool = False) -> str | None:
    """The project's id from `pyproject.toml`. With `create`, a project without one gets one, written to the file."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    text = pyproject.read_text()
    config = tomllib.loads(text).get("tool", {}).get("factoid")
    if config is None:
        return None
    if config.get("id"):
        return str(config["id"])
    if not create:
        return None
    new = new_project_id(str(config.get("package") or root.name))
    lines = text.splitlines(keepends=True)
    at = next(i for i, line in enumerate(lines) if line.strip() == "[tool.factoid]")
    lines.insert(at + 1, f'id = "{new}"  # names this project\'s keys in ~/.factoid/projects/; keep it committed\n')
    pyproject.write_text("".join(lines))
    return new
