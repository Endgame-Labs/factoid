"""Writes the call's real Factoid output as the data for the landing site's "What is a fact?" page.

Run it after ingesting all three documents (see README.md):

    uv run python page_data.py ../../site/what-is-a-fact.html

It replaces the page's `DEMO_DATA` object with the call's turns and its facts as they stand after the emails: their
text, class, traits, status, relations, quotes, entities, and dates. Factoid cites a whole turn; the page highlights
the sentences in that turn that share at least two words with the fact, and says so. A cited turn with no such
sentence is left out.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from factoid import api
from factoid.project import load

HERE = Path(__file__).parent
CALL = "docs/2026-10-14-kestrel-call.txt"
TURN = re.compile(r"\[(\d+:\d\d)\]\s+([^:]+):\s(.*)")
WORD = re.compile(r"[A-Za-z0-9$,.']+")
STOP = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "is", "are", "we", "our", "that", "said",
        "this", "it", "be", "with", "by", "as", "will", "would", "its", "their", "them", "she", "he"}


def words(text: str) -> set[str]:
    return {w.lower().strip(".,'") for w in WORD.findall(text)} - STOP


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]


def people(participants: str) -> dict[str, tuple[str, str]]:
    """'Maya Lin (account executive, Northstar Data), ...' as {name: (role, company)}."""
    out = {}
    for name, role, company in re.findall(r"([A-Z][\w.'-]+(?: [A-Z][\w.'-]+)*) \(([^,]+), ([^)]+)\)", participants):
        out[name] = (role, company)
    return out


def day(value: str | None) -> str | None:
    return value[:10] if value else None


def main(page: Path) -> None:
    app = load(HERE).app()
    meta = json.loads((HERE / (CALL + ".meta.json")).read_text())
    who = people(meta["participants"])
    turns, by_passage = [], {}
    for n, line in enumerate(t for t in (HERE / CALL).read_text().splitlines() if t.strip()):
        stamp, speaker, said = TURN.match(line).groups()
        role, company = who.get(speaker, ("", ""))
        turn = {"id": f"t{n + 1}", "speaker": speaker, "role": f"{role}, {company}".strip(", "),
                "side": "vendor" if company == "Northstar Data" else "customer", "timestamp": stamp,
                "sentences": [{"id": f"s{n + 1}-{i + 1}", "text": s} for i, s in enumerate(sentences(said))]}
        turns.append(turn)
        by_passage[n + 1] = turn

    call = next(d for d in app.store.query("select id from documents where uri = ?", (CALL,)))["id"]
    rows = app.store.query("select id from facts where document_id = ? order by id", (call,))
    found = [api.fact(app, r["id"]) for r in rows]
    names = {f["id"]: f"fact_{i + 1:02d}" for i, f in enumerate(found)}
    kinds = {r["id"]: r["class"] for r in app.store.query("select id, class from entities")}
    facts = []
    for f in found:
        quotes, seen = [], set()
        for q in f["quotes"]:
            turn = by_passage.get(q["passage"])
            if turn is None:
                continue
            share = [s for s in turn["sentences"] if len(words(s["text"]) & words(f["text"])) >= 2]
            for s in share:  # a cited turn with no sentence sharing two words with the fact is left out
                if s["id"] not in seen:
                    seen.add(s["id"])
                    quotes.append({"sentenceId": s["id"], "speaker": turn["speaker"], "timestamp": turn["timestamp"]})
        fact = {"id": names[f["id"]], "sentence": f["text"], "factClass": f["class"],
                "traits": ["".join(p.title() for p in t.split("_")) for t in f["traits"]], "status": f["status"],
                "quotes": quotes,
                "entities": [{"name": m["text"], "kind": kinds.get(m["entity_id"], "Entity"), "role": m["role"]}
                             for m in f["mentions"]],
                "time": {k: v for k, v in {"validFrom": day(f.get("valid_from")),
                                           "validUntil": day(f.get("valid_until")),
                                           "expires": f.get("expires")}.items() if v}}
        for r in f["relations"]:
            mine = r["fact_id"] == f["id"]
            other = r["other_id"] if mine else r["fact_id"]
            label = names.get(other, "a fact from a later email")
            verb = r["relation"] if mine else {"supersedes": "superseded", "ends": "ended", "corrects": "corrected",
                                                "contradicts": "contradicted"}.get(r["relation"], r["relation"])
            words_for = verb if mine else f"{verb} by"
            fact["relation"] = {"type": verb, "targetFactId": names.get(other, other), "label": f"{words_for} {label}"}
        facts.append(fact)

    # In the order of the call, by the first sentence each fact highlights, numbered again in that order.
    def place(fact: dict) -> tuple[int, int]:
        first = fact["quotes"][0]["sentenceId"] if fact["quotes"] else "s99-99"
        turn, sentence = first[1:].split("-")
        return int(turn), int(sentence)

    facts.sort(key=place)
    renumber = {f["id"]: f"fact_{i + 1:02d}" for i, f in enumerate(facts)}
    for f in facts:
        f["id"] = renumber[f["id"]]
        if "relation" in f and f["relation"]["targetFactId"] in renumber:
            old = f["relation"]["targetFactId"]
            f["relation"]["targetFactId"] = renumber[old]
            f["relation"]["label"] = f["relation"]["label"].replace(old, renumber[old])

    held = datetime.fromisoformat(meta["held_at"].replace("Z", "+00:00"))
    data = {
        "document": {"id": call, "title": meta["title"], "documentClass": "CallTranscript",
                     "sourceDatetime": meta["held_at"],
                     "sourceDateLabel": held.strftime("%a, %b %-d, %Y · %H:%M UTC"),
                     "sampleNote": "Real Factoid output from examples/demo",
                     "participants": [f"{n} ({c})" for n, (_, c) in who.items()]},
        "turns": turns,
        "facts": facts,
    }
    text = page.read_text()
    start = text.index("var DEMO_DATA = ")
    end = _object_end(text, start + len("var DEMO_DATA = "))
    block = json.dumps(data, indent=2, ensure_ascii=False).replace("\n", "\n      ")
    page.write_text(text[:start] + "var DEMO_DATA = " + block + text[end:])
    print(f"{page}: {len(turns)} turns, {len(facts)} facts")


def _object_end(text: str, at: int) -> int:
    """The index just after the object literal that starts at `at`, skipping braces inside strings."""
    depth, quote, i = 0, None, at
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("DEMO_DATA has no end")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
