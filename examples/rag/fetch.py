"""Download Python's "What's New" pages for 3.9 to 3.14 into data/, as text, one document per release.

    uv run python fetch.py

Only the sections a docs assistant needs for "is this still in Python?" questions are kept: New Modules, Deprecated,
and Removed (with their "Pending removal" lists). The pages come from https://docs.python.org/3/whatsnew/ (the Python
documentation, under the PSF license) and are not committed. Raw pages are cached in data/raw/, so a second run makes
no requests.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
RAW = DATA / "raw"
AGENT = "factoid-example/0.1 (research; one request per second)"
#: Each release and the day it came out (from PEP 596, 619, 664, 693, 719, and 745).
RELEASES = {
    "3.9": "2020-10-05", "3.10": "2021-10-04", "3.11": "2022-10-24",
    "3.12": "2023-10-02", "3.13": "2024-10-07", "3.14": "2025-10-07",
}
#: The h2 sections kept. 3.13 calls them "Removed Modules And APIs" and "New Deprecations".
KEEP = re.compile(r"^(new modules|deprecated|new deprecations|removed|pending removal)", re.I)


def get(url: str) -> str:
    """A cached GET."""
    RAW.mkdir(parents=True, exist_ok=True)
    cached = RAW / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
    if cached.exists():
        return cached.read_text()
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8")
    cached.write_text(text)
    time.sleep(1)
    return text


class Sections(HTMLParser):
    """The page as Markdown-like text, split into its top-level (h2) sections."""

    BLOCKS = {"p", "li", "dt", "dd", "pre", "tr", "h2", "h3", "h4", "h5"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[tuple[str, list[str]]] = []
        self.block: list[str] | None = None
        self.tag = ""
        self.skip = 0  # inside a headerlink anchor (the pilcrow) or a script
        self.lists = 0  # how deep in <ul> or <ol>
        self.depth = 0  # the list depth of the current item

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if (tag == "a" and "headerlink" in (a.get("class") or "")) or tag in ("script", "style"):
            self.skip += 1
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists += 1
        elif tag in ("td", "th") and self.tag == "tr":
            if "".join(self.block or []).strip():
                self.block.append(" | ")  # one table row per line, cells split by |
        elif tag == "p" and self.tag == "tr":
            pass
        elif tag == "p" and self.tag in ("li", "dd") and not "".join(self.block or []).strip():
            pass  # Sphinx wraps an item's text in <p>: keep it in the item
        elif tag in self.BLOCKS:
            self._flush()
            self.block, self.tag, self.depth = [], tag, self.lists

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "script", "style") and self.skip:
            self.skip -= 1
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists = max(0, self.lists - 1)
        elif tag in self.BLOCKS and tag == self.tag:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.block is not None and not self.skip:
            self.block.append(data)

    def _flush(self) -> None:
        if self.block is None:
            return
        raw = "".join(self.block)
        text = raw.strip("\n") if self.tag == "pre" else " ".join(raw.split())
        tag, self.block, self.tag = self.tag, None, ""
        if not text:
            return
        if tag == "h2":
            self.sections.append((text, [f"## {text}"]))
        elif self.sections:
            indent = "  " * max(0, self.depth - 1)
            line = {"h3": f"### {text}", "h4": f"#### {text}", "h5": f"##### {text}", "li": f"{indent}- {text}",
                    "pre": "\n".join("    " + row for row in text.splitlines())}.get(tag, text)
            self.sections[-1][1].append(line)


def whatsnew(version: str) -> str:
    parser = Sections()
    parser.feed(get(f"https://docs.python.org/3/whatsnew/{version}.html"))
    parser.close()
    kept = ["\n\n".join(lines) for title, lines in parser.sections if KEEP.match(title)]
    text = f"# What's New In Python {version}\n\n" + "\n\n".join(kept)
    return text + "\n"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for version, released in RELEASES.items():
        text = whatsnew(version)
        path = DATA / f"whatsnew-{version}.md"
        path.write_text(text)
        meta = {"title": f"What's New In Python {version}", "version": version,
                "released_at": f"{released}T00:00:00Z",
                "url": f"https://docs.python.org/3/whatsnew/{version}.html"}
        path.with_name(path.name + ".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        print(f"{path.name}: {len(text):,} characters")


if __name__ == "__main__":
    main()
