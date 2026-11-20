"""Files `factoid init` writes: sample classes, sample documents, and an eval."""

from __future__ import annotations

from pathlib import Path

from .project_id import new_project_id

__all__ = ["PRESETS", "switch", "write"]

PYPROJECT = """[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["factoid>={version}"]
{sources}
[tool.factoid]
package = "{package}"
id = "{project_id}"  # names this project's keys in ~/.factoid/projects/; keep it committed
"""

#: Model presets for `factoid init --models`. Each names the providers whose keys it needs.
_JEV = """\
        "choose": Model("typesafe/jev-1.13.0"),  # classify, evaluate facts, assess, link, and resolve
        "generate": Model("fireworks/glm-5p3-flash", reasoning_effort="low"),  # extract and repair
        "embed": Model("fireworks/qwen3-embedding-8b"),"""

_FIREWORKS = """\
        "choose": Model("fireworks/rune"),  # classify, evaluate facts, assess, link, and resolve
        "generate": Model("fireworks/glm-5p3-flash", reasoning_effort="low"),  # extract and repair
        "embed": Model("fireworks/qwen3-embedding-8b"),"""

_OPENAI = """\
        "choose": Model("openai/gpt-6-luna"),  # the Decisions API: classify, evaluate facts, assess, link, and resolve
        "generate": Model("openai/gpt-6-luna"),  # extract and repair
        "embed": Model("openai/text-embedding-3-small"),"""

PRESETS: dict[str, tuple[tuple[str, ...], str]] = {
    "jev": (("typesafe", "fireworks"), _JEV),
    "fireworks": (("fireworks",), _FIREWORKS),
    "openai": (("openai",), _OPENAI),
}

SETTINGS = '''from factoid import Model, Settings


class Project(Settings):
    """Models, store, and search for this project."""

    models = {{
{models}
    }}
'''

DOCUMENTS = '''from factoid import ProseDocument


class Contract(ProseDocument):
    """A contract, an agreement, or an amendment to one."""

    @property
    def source_datetime(self):
        return self.metadata.get("signed_at")


class CounselEmail(ProseDocument):
    """An email between our lawyers and the client or the other side."""

    @property
    def source_datetime(self):
        return self.metadata.get("sent_at")
'''

ENTITIES = '''from factoid import Entity


class Company(Entity):
    """A company that is a party to a deal or a contract."""

    unique_keys = ["domain"]


class Person(Entity):
    """A lawyer, a client contact, or someone at the other side."""

    unique_keys = ["email"]
'''

FACTS = '''from factoid import Fact, FactTrait


class ConsentRequired(FactTrait):
    """A named party must approve an action before it happens."""


class LiabilityCap(FactTrait):
    """A limit on how much a party can owe."""


class SourceFact(Fact):
    """What a contract, a client, or the other side says."""

    traits = [ConsentRequired, LiabilityCap]
'''

SAMPLE_CONTRACT = """SUPPLY AGREEMENT

This Supply Agreement is made on March 1, 2025 between Orion Inc. and Vega Corp.

Orion Inc. may not assign this Supply Agreement without the prior written consent of Vega Corp.

Vega Corp.'s total liability under this Supply Agreement is capped at $1,000,000.
"""

SAMPLE_META = '{"signed_at": "2025-03-01T00:00:00Z", "title": "Orion and Vega Supply Agreement"}\n'

SAMPLE_SUITE = '''"""A tiny suite: the sample contract, and the three facts it should give."""

from pathlib import Path

from factoid.evals import Suite, prf

HERE = Path(__file__).parent.parent / "sample_docs"


class Sample(Suite):
    name = "sample"

    def documents(self, limit=None):
        # A Raw document is classified first, the way `factoid ingest` does it.
        import json

        from factoid import Raw

        meta = json.loads((HERE / "supply.txt.meta.json").read_text())
        yield Raw((HERE / "supply.txt").read_text(), meta, uri="sample_docs/supply.txt", title=meta["title"])

    def score(self, app, results):
        # Three separate facts: the signing (no trait), the consent clause, and the cap, each with its own trait.
        # Each fact can match one of them, and a fact that matches none counts against precision.
        wanted = {{
            "signing": lambda f: not f.trait_names and ("March 1, 2025" in f.text or "2025-03-01" in f.text),
            "consent": lambda f: f.trait_names == ["consent_required"] and "consent" in f.text.lower(),
            "cap": lambda f: f.trait_names == ["liability_cap"] and "1,000,000" in f.text,
        }}
        matched, extra = set(), 0
        for f in (f for r in results for f in r.facts):
            hit = next((k for k, test in wanted.items() if k not in matched and test(f)), None)
            if hit:
                matched.add(hit)
            else:
                extra += 1
        return {{"facts": prf(len(matched), extra, len(wanted) - len(matched))}}
'''


def _sources() -> str:
    """A `[tool.uv.sources]` block when this Factoid came from a checkout or from git; nothing when from PyPI."""
    from .version import source

    found = source()
    if found is None:
        return ""
    return f"\n# uv installs Factoid from where this `factoid` came from.\n[tool.uv.sources]\nfactoid = {found}\n"


def _version() -> str:
    from .version import version

    found = version()
    return found if found[:1].isdigit() else "0.1.19"


def switch(settings: Path, preset: str) -> bool:
    """Swap the models block in a settings.py that `init` wrote for another preset's. False when the block was edited
    and matches no preset, so nothing is changed."""
    text = settings.read_text()
    for _, block in PRESETS.values():
        if block in text:
            settings.write_text(text.replace(block, PRESETS[preset][1]))
            return True
    return False


def write(root: Path, package: str, preset: str = "jev") -> list[Path]:
    files = {
        root / "pyproject.toml": PYPROJECT.format(name=package.replace("_", "-"), package=package,
                                                  sources=_sources(), version=_version(),
                                                  project_id=new_project_id(package)),
        root / package / "__init__.py": "",
        root / package / "settings.py": SETTINGS.format(models=PRESETS[preset][1]),
        root / package / "documents.py": DOCUMENTS,
        root / package / "entities.py": ENTITIES,
        root / package / "facts.py": FACTS,
        root / "sample_docs" / "supply.txt": SAMPLE_CONTRACT,
        root / "sample_docs" / "supply.txt.meta.json": SAMPLE_META,
        root / "evals" / "sample.py": SAMPLE_SUITE.format(package=package),
        root / ".gitignore": ".factoid/\nruns/\n.venv/\n__pycache__/\n*.local\n",
    }
    written = []
    for path, content in files.items():
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written.append(path)
    return written
