"""Files `factoid init` writes: sample classes, sample documents, and an eval."""

from __future__ import annotations

from pathlib import Path

__all__ = ["PRESETS", "write"]

PYPROJECT = """[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["factoid"]

# Factoid is not on PyPI yet, so uv installs it from GitHub.
[tool.uv.sources]
factoid = {{ git = "https://github.com/Endgame-Labs/factoid" }}

[tool.factoid]
package = "{package}"
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
    """A signed contract or an amendment to one."""

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

SAMPLE_SUITE = '''"""A tiny suite: the sample contract, and the traits its facts should carry."""

from pathlib import Path

from factoid.evals import Suite, prf

HERE = Path(__file__).parent.parent / "sample_docs"


class Sample(Suite):
    name = "sample"

    def documents(self, limit=None):
        from {package}.documents import Contract
        import json

        meta = json.loads((HERE / "supply.txt.meta.json").read_text())
        yield Contract((HERE / "supply.txt").read_text(), metadata=meta, uri="sample_docs/supply.txt")

    def score(self, app, results):
        expected = {{"consent_required", "liability_cap"}}
        found = {{t for r in results for f in r.facts for t in f.trait_names}}
        return {{"traits": prf(len(expected & found), len(found - expected), len(expected - found))}}
'''


def write(root: Path, package: str, preset: str = "jev") -> list[Path]:
    files = {
        root / "pyproject.toml": PYPROJECT.format(name=package.replace("_", "-"), package=package),
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
