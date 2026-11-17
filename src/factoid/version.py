"""Which Factoid this is: the package version, plus the git commit when it was installed from git or a checkout."""

from __future__ import annotations

import json
import subprocess
from functools import cache
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse

__all__ = ["version", "commit", "describe"]


def version() -> str:
    try:
        return metadata.version("factoid")
    except metadata.PackageNotFoundError:
        return "unknown"


@cache
def commit() -> str | None:
    """The short commit: from uv's or pip's record of a git install, or from the checkout of an editable one."""
    try:
        raw = metadata.distribution("factoid").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        raw = None
    info = json.loads(raw) if raw else {}
    sha = (info.get("vcs_info") or {}).get("commit_id")
    if sha:
        return sha[:7]
    url = urlparse(info.get("url", ""))
    folder = Path(unquote(url.path)) if url.scheme == "file" else Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(["git", "-C", str(folder), "rev-parse", "--short=7", "HEAD"], check=False,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def describe() -> str:
    """`0.1.1 (commit 6e756ce)`, or just the version."""
    sha = commit()
    return f"{version()} (commit {sha})" if sha else version()
