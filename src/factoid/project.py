"""Finding and loading a project.

A project is a Python package of plain classes. Its `pyproject.toml` names the package under `[tool.factoid]`:

    [tool.factoid]
    package = "legal"

Loading imports the conventional modules (`settings`, `sources`, `documents`, `entities`, `facts`, and
`fact_evals`) when they exist. They are defaults, not requirements: classes defined anywhere in the package and
imported by it count too.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .app import Factoid
from .document import Document
from .entity import Entity
from .fact import Fact
from .settings import Settings

__all__ = ["Project", "find_root", "load"]

CONVENTIONAL = ("settings", "sources", "documents", "entities", "facts", "fact_evals")


@dataclass
class Project:
    root: Path
    package: str
    settings: type[Settings]
    documents: list[type[Document]]
    entities: list[type[Entity]]
    facts: list[type[Fact]]

    def app(self, **kwargs: Any) -> Factoid:
        return Factoid(self.settings, documents=self.documents, entities=self.entities, facts=self.facts,
                       root=self.root, project_id=self.package, **kwargs)


def find_root(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        pyproject = folder / "pyproject.toml"
        if pyproject.is_file() and "factoid" in tomllib.loads(pyproject.read_text()).get("tool", {}):
            return folder
    return None


def package_name(root: Path) -> str:
    config = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["factoid"]
    return config.get("package") or root.name.replace("-", "_")


def load(root: Path | None = None) -> Project:
    root = root or find_root()
    if root is None:
        raise FileNotFoundError("not inside a Factoid project (no pyproject.toml with [tool.factoid])")
    package = package_name(root)
    for path in (root / "src", root):
        if (path / package).is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    importlib.import_module(package)
    modules = []
    for name in CONVENTIONAL:
        full = f"{package}.{name}"
        if importlib.util.find_spec(full) is not None:
            modules.append(importlib.import_module(full))
    settings: type[Settings] = Settings
    for module in modules:
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, Settings) and value is not Settings \
                    and value.__module__ == module.__name__:
                settings = value

    def ours(klass: type) -> bool:
        return klass.__module__ == package or klass.__module__.startswith(package + ".")

    return Project(
        root=root,
        package=package,
        settings=settings,
        documents=[k for k in Document.registered() if ours(k)],
        entities=[k for k in Entity.registered() if ours(k)],
        facts=[k for k in Fact.registered() if ours(k)],
    )
