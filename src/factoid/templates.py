"""Prompts and decision questions are Jinja templates, set explicitly on a class.

A class sets wording as a string or with `template(path)`. The path is resolved relative to the file that defines the
class. A missing file fails when the class is defined, not at the first model call. Project templates can extend the
built-in ones, which are found under the `factoid/` prefix: `{% extends "factoid/extract.md.j2" %}`.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import jinja2

__all__ = ["Template", "template", "render", "builtin", "BUILTIN_DIR"]

BUILTIN_DIR = Path(__file__).parent / "prompts"


class _Loader(jinja2.BaseLoader):
    """Built-ins under `factoid/`, everything else relative to a search folder."""

    def __init__(self, folder: Path | None):
        self.folder = folder

    def get_source(self, environment: jinja2.Environment, name: str) -> tuple[str, str, Any]:
        if name.startswith("factoid/"):
            path = BUILTIN_DIR / name.removeprefix("factoid/")
        elif self.folder is not None:
            path = self.folder / name
        else:
            raise jinja2.TemplateNotFound(name)
        if not path.is_file():
            raise jinja2.TemplateNotFound(name)
        source = path.read_text()
        mtime = path.stat().st_mtime
        return source, str(path), lambda: path.is_file() and path.stat().st_mtime == mtime


def _env(folder: Path | None) -> jinja2.Environment:
    return jinja2.Environment(
        loader=_Loader(folder),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


class Template:
    """A Jinja template from a file or a string, with where it came from."""

    def __init__(self, source: str, origin: str, folder: Path | None):
        self.source = source
        self.origin = origin
        self.folder = folder
        self._compiled = _env(folder).from_string(source)

    def render(self, **context: Any) -> str:
        return self._compiled.render(**context).strip() + "\n"

    def __repr__(self) -> str:
        return f"Template({self.origin})"


def template(path: str) -> Template:
    """A template file, resolved relative to the file that calls `template(...)`."""
    caller = inspect.stack()[1].filename
    if path.startswith("factoid/"):
        full = BUILTIN_DIR / path.removeprefix("factoid/")
    else:
        full = (Path(caller).parent / path).resolve()
    if not full.is_file():
        raise FileNotFoundError(f"template {path!r} not found at {full}")
    return Template(full.read_text(), str(full), full.parent)


def builtin(name: str) -> Template:
    """A built-in template, such as `builtin("extract.md.j2")`."""
    full = BUILTIN_DIR / name
    return Template(full.read_text(), f"factoid/{name}", BUILTIN_DIR)


def render(wording: str | Template, **context: Any) -> str:
    """Render a string or a `Template` with the step's context."""
    if isinstance(wording, Template):
        return wording.render(**context)
    return Template(wording, "<string>", None).render(**context)
