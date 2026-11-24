"""The docs assistant's questions, answered by each retriever in `rag.py`, and judged.

`factoid eval qa` ingests the six "What's New" pages in release order, then asks every question three ways (facts,
chunks, and both) at three source budgets, about 500, 2,000, and 8,000 tokens. The reader and the prompt are the same each
time; only the sources differ.

Each question is about one Python version and has two reference answers, both checked against the pages: the answer
for that version, and an outdated one, true in an earlier or later release. A judge decides which one each answer
gives, or neither. "outdated" is the failure RAG over changing docs is known for: an old page says a module is
deprecated, and the reader answers that it still works in a version that removed it.

The first 30 questions ask about the release that made the change, whose own page states the answer. `LATEST` asks
about Python 3.14 for changes made in earlier releases, as a user on today's Python would: the 3.14 page says nothing
about them, so the answer has to come from the right older page, and pages that are now out of date compete with it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from factoid import Raw
from factoid.evals import Suite
from factoid.models import Model, ModelClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rag

JUDGE = Model("fireworks/kimi-k3p1-pro", reasoning_effort="none")
BUDGETS = (2000, 8000, 32000)  # characters of sources, about 500, 2,000, and 8,000 tokens
JUDGE_SYSTEM = (
    "You judge an answer to a question about Python's standard library in one Python version. You see the right "
    "answer for that version, an outdated answer that was true in another version, and the answer to judge. Decide "
    "whether it agrees with the right answer on the point that matters (whether the thing exists and works in that "
    "version, or which module to use) (\"current\"), agrees with the outdated answer instead (\"outdated\"), or "
    "neither (\"neither\", including no answer). Extra detail is fine. Return ONLY JSON: {\"verdict\": \"current\"}, "
    "{\"verdict\": \"outdated\"}, or {\"verdict\": \"neither\"}."
)

#: (question, Python version, the answer for that version, an outdated answer). Each was checked against the pages.
QUESTIONS: list[tuple[str, str, str, str]] = [
    ("Is the distutils package available?", "3.12",
     "No. distutils was removed in Python 3.12; it was deprecated in 3.10.",
     "Yes, it is available but deprecated."),
    ("Is the distutils package available?", "3.11",
     "Yes, but it is deprecated (since 3.10) and will be removed in Python 3.12.",
     "No, it has been removed."),
    ("Can I use the asyncore module?", "3.12",
     "No. asyncore was removed in Python 3.12.",
     "Yes, it is deprecated but still available."),
    ("Can I use the asynchat module?", "3.11",
     "Yes, but it is deprecated and will be removed in Python 3.12.",
     "No, it has been removed."),
    ("Is the imp module available?", "3.12",
     "No. The imp module was removed in Python 3.12.",
     "Yes, it is deprecated but still available."),
    ("Can I use the cgi module?", "3.13",
     "No. cgi (and cgitb) were removed in Python 3.13 under PEP 594.",
     "Yes, it is deprecated but still available."),
    ("Can I use the cgi module?", "3.11",
     "Yes, but it is deprecated (PEP 594) and scheduled for removal in Python 3.13.",
     "No, it has been removed."),
    ("Is telnetlib in the standard library?", "3.13",
     "No. telnetlib was removed in Python 3.13; telnetlib3 or Exscript from PyPI can replace it.",
     "Yes, it is deprecated but still available."),
    ("Does Python still ship lib2to3 and the 2to3 tool?", "3.13",
     "No. lib2to3 and 2to3 were removed in Python 3.13.",
     "Yes, they are deprecated but still included."),
    ("Can I still call unittest's assertEquals alias?", "3.12",
     "No. assertEquals and the other old TestCase aliases were removed in Python 3.12; use assertEqual().",
     "Yes, it is a deprecated alias of assertEqual()."),
    ("Is datetime.datetime.utcnow() deprecated?", "3.14",
     "Yes. utcnow() is deprecated (since 3.12) but still available; use datetime.now(tz=datetime.UTC).",
     "No, it is not deprecated, or it has been removed."),
    ("Can I use ast.Num?", "3.14",
     "No. ast.Num and the other old node classes were removed in Python 3.14; use ast.Constant.",
     "Yes, it is deprecated but still available."),
    ("Can I use ast.Num?", "3.13",
     "Yes, but it is deprecated and will be removed in Python 3.14; use ast.Constant.",
     "No, it has been removed."),
    ("Can I use asyncio.SafeChildWatcher?", "3.14",
     "No. The child watcher classes were removed in Python 3.14.",
     "Yes, it is deprecated but still available."),
    ("Does importlib.abc.ResourceReader exist?", "3.14",
     "No. It was removed in Python 3.14; use importlib.resources.abc.TraversableResources.",
     "Yes, it is deprecated but still available."),
    ("Is ssl.wrap_socket() available?", "3.12",
     "No. ssl.wrap_socket() was removed in Python 3.12; use SSLContext.wrap_socket().",
     "Yes, it is deprecated but still available."),
    ("Does configparser still have SafeConfigParser?", "3.12",
     "No. SafeConfigParser was removed in Python 3.12; use ConfigParser.",
     "Yes, it is a deprecated alias of ConfigParser."),
    ("Is the binhex module available?", "3.11",
     "No. binhex was removed in Python 3.11; it was deprecated in 3.9.",
     "Yes, it is deprecated but still available."),
    ("Can I use the @asyncio.coroutine decorator?", "3.11",
     "No. @asyncio.coroutine was removed in Python 3.11; use async def.",
     "Yes, it is deprecated but still available."),
    ("Is the parser module available?", "3.10",
     "No. The parser module was removed in Python 3.10.",
     "Yes, it is deprecated but still available."),
    ("Is the formatter module available?", "3.10",
     "No. The formatter module was removed in Python 3.10.",
     "Yes, it is deprecated but still available."),
    ("Is the tkinter.tix module available?", "3.13",
     "No. tkinter.tix was removed in Python 3.13.",
     "Yes, it is deprecated but still available."),
    ("Can I import from typing.io?", "3.13",
     "No. The typing.io and typing.re namespaces were removed in Python 3.13; import from typing.",
     "Yes, but importing from it is deprecated."),
    ("Is locale.getdefaultlocale() deprecated, and when will it be removed?", "3.11",
     "Yes. It is deprecated and will be removed in Python 3.15.",
     "No, it is not deprecated."),
    ("Can I pass type, choices, or metavar to argparse.BooleanOptionalAction?", "3.14",
     "No. Those parameters were removed in Python 3.14.",
     "Yes, but they are deprecated."),
    ("Does pkgutil.find_loader() exist?", "3.14",
     "No. pkgutil.find_loader() and get_loader() were removed in Python 3.14.",
     "Yes, it is deprecated but still available."),
    ("Which standard library module parses TOML?", "3.11",
     "tomllib, new in Python 3.11.",
     "None; the standard library has no TOML parser."),
    ("Is there an SQLite backend for dbm?", "3.13",
     "Yes. dbm.sqlite3 is new in Python 3.13.",
     "No."),
    ("Which standard library module supports Zstandard compression?", "3.14",
     "compression.zstd, new in Python 3.14.",
     "None; the standard library has no Zstandard support."),
    ("Which module gives IANA time zones?", "3.9",
     "zoneinfo, new in Python 3.9.",
     "None; the standard library has no IANA time zone support."),
]

#: The same kind of question about Python 3.14, for changes made in earlier releases.
LATEST: list[tuple[str, str, str, str]] = [
    (question, "3.14", f"No. {what} was removed in Python {version}.", "Yes, it is deprecated but still available.")
    for question, what, version in [
        ("Is the distutils package available?", "distutils", "3.12"),
        ("Can I use the asynchat module?", "asynchat", "3.12"),
        ("Is the imp module available?", "imp", "3.12"),
        ("Can I use the cgi module?", "cgi", "3.13"),
        ("Is telnetlib in the standard library?", "telnetlib", "3.13"),
        ("Is the binhex module available?", "binhex", "3.11"),
        ("Is the parser module available?", "The parser module", "3.10"),
        ("Does Python still ship lib2to3 and the 2to3 tool?", "lib2to3", "3.13"),
        ("Can I import from typing.io?", "typing.io", "3.13"),
        ("Is ssl.wrap_socket() available?", "ssl.wrap_socket()", "3.12"),
        ("Does configparser still have SafeConfigParser?", "SafeConfigParser", "3.12"),
        ("Can I use the @asyncio.coroutine decorator?", "@asyncio.coroutine", "3.11"),
        ("Is the tkinter.tix module available?", "tkinter.tix", "3.13"),
        ("Can I still call unittest's assertEquals alias?", "assertEquals", "3.12"),
    ]
] + [
    ("Which standard library module parses TOML?", "3.14", "tomllib, added in Python 3.11.",
     "None; the standard library has no TOML parser."),
]
ALL = QUESTIONS + LATEST


class QA(Suite):
    name = "qa"
    description = "Questions about the standard library, answered from facts, from chunks, and from both."

    def documents(self, limit: int | None = None):
        # In release order, so each page is resolved against the ones before it.
        for version, meta in list(rag.releases().items())[:limit]:
            text = (rag.DATA / f"whatsnew-{version}.md").read_text()
            yield Raw(text, meta, uri=f"data/whatsnew-{version}.md", title=meta["title"])

    def score(self, app: Any, results: list[Any]) -> dict[str, Any]:
        if not rag.releases():
            raise RuntimeError("no pages: run `uv run python fetch.py` first")
        judge = ModelClient({"generate": JUDGE}, app.calls, app.meter)

        def verdict(q: tuple[str, str, str, str], said: str) -> str:
            question, python, current, outdated = q
            raw = judge.generate(
                f"Python version: {python}\nQuestion: {question}\n\nRight answer: {current}\n\n"
                f"Outdated answer: {outdated}\n\nAnswer to judge: {said}", json_mode=True, max_tokens=200,
                system=JUDGE_SYSTEM)
            try:
                return str(json.loads(raw).get("verdict"))
            except (json.JSONDecodeError, AttributeError):
                return "neither"

        out: dict[str, Any] = {"questions": len(ALL)}
        rows = [{"python": q[1], "question": q[0], "set": "latest" if i >= len(QUESTIONS) else "release"}
                for i, q in enumerate(ALL)]
        for retriever in rag.RETRIEVERS:
            for budget in BUDGETS:
                cell = f"{retriever}@{budget // 4}"

                def run(q: tuple[str, str, str, str], retriever: str = retriever,
                        budget: int = budget) -> tuple[rag.Answer, str]:
                    result = rag.answer(app, q[0], q[1], retriever=retriever, budget=budget)
                    return result, verdict(q, result.text)

                answered = app.map(run, ALL)
                verdicts = [v for _, v in answered]
                read = [sum(len(s) for s in a.sources) for a, _ in answered]
                latest = verdicts[len(QUESTIONS):]
                out[cell] = {
                    "accuracy": round(verdicts.count("current") / len(ALL), 3),
                    "outdated": round(verdicts.count("outdated") / len(ALL), 3),
                    "latest_accuracy": round(latest.count("current") / len(latest), 3),
                    "latest_outdated": round(latest.count("outdated") / len(latest), 3),
                    "mean_read_tokens": round(sum(read) / len(read) / 4),
                }
                for row, (a, v) in zip(rows, answered):
                    row[cell] = v
                    row[f"{cell} answer"] = a.text[:200]
        out["details"] = rows
        return out
