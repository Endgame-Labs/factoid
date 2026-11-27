"""Write the output samples: a few rows of each structured file, ingested into a scratch store, and the facts they
became. Run `uv run python fetch.py` first, then `uv run python output_samples/make.py` from the example's folder.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
from pathlib import Path

from factoid import api
from factoid.project import load

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
FINALS_GAME_6 = "401442535"

# Which rows of each file to ingest, and which columns to show beside the facts.
SAMPLES = {
    "GameLog": ("games.csv", lambda r: r["series"] == "2022 NBA Finals",
                ["game", "date", "result", "warriors_score", "opponent_score", "series_status"]),
    "BoxScore": ("box_scores.csv", lambda r: r["game_id"] == FINALS_GAME_6 and r["starter"] == "yes",
                 ["player", "team", "minutes", "points", "rebounds", "assists", "threes"]),
    "PlayerTotals": ("player_totals.csv", lambda r: r["player"] in ("Stephen Curry", "Klay Thompson", "Draymond Green"),
                     ["player", "games", "points_per_game", "rebounds_per_game", "assists_per_game", "threes_made"]),
}


def slice_csv(name: str, keep) -> tuple[str, list[dict[str, str]]]:
    rows = list(csv.DictReader((DATA / name).open()))
    picked = [r for r in rows if keep(r)]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(picked)
    return out.getvalue(), picked


def main() -> None:
    project = load(ROOT)
    classes = {k.__name__: k for k in project.documents}
    with tempfile.TemporaryDirectory() as scratch:
        app = project.app(data_dir=scratch, calls_path=ROOT / ".factoid" / "calls.db")
        sections = []
        for kind, (name, keep, shown) in SAMPLES.items():
            text, rows = slice_csv(name, keep)
            klass = classes[kind]
            result = app.ingest(klass(text, uri=f"data/{name}", title=klass.description()))
            records = [api.fact(app, r["id"])
                       for r in api.facts(app, document=result.document.id, status="all", limit=0)]
            with (HERE / f"{kind}.jsonl").open("w") as out:
                for record in records:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
            sections.append((kind, name, klass, shown, rows, records))
        (HERE / "README.md").write_text(render(sections))


def render(sections) -> str:
    lines = [
        "# Output samples",
        "",
        "Structured files in, prose facts out. Each section below shows a few rows of one of this example's CSV",
        "files, ingested on their own into a scratch store, and the facts Factoid made from them. A templated cell",
        "becomes one sentence, with no model call, cited to its file, row, and column, and linked to the players,",
        "teams, games, and series its identity columns name. The full record of each fact, as `factoid fact` and the",
        "HTTP API return it, is in the `.jsonl` file of the same name.",
        "",
        "Made by `uv run python output_samples/make.py`, from data that `fetch.py` downloads from ESPN's public site",
        "API.",
    ]
    for kind, name, klass, shown, rows, records in sections:
        lines += ["", f"## {kind}", "", f"{klass.description()} Rows from `{name}`:", "",
                  "| " + " | ".join(shown) + " |", "| " + " | ".join("---" for _ in shown) + " |"]
        lines += ["| " + " | ".join(r[c] for c in shown) + " |" for r in rows]
        lines += ["", "Facts:", "", "| Fact | Status | Held | From | Linked to |", "| --- | --- | --- | --- | --- |"]
        for f in records:
            cite = "; ".join(f"row {q['passage']}, `{q['section']}`" for q in f["quotes"])
            linked = ", ".join(f"{m['text']} ({m['role']})" for m in f["mentions"])
            held = f"{f['valid_from'][:10]} to {(f['valid_until'] or '')[:10] or 'now'}" if f["valid_from"] else ""
            lines.append(f"| {f['text']} | {f['status']} | {held} | {cite} | {linked} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
