"""The Warriors' 2022 playoffs, end to end: games, box scores, player totals, recaps, interviews, and articles.

Run `uv run python fetch.py` first. Documents go in by date within each kind, structured files first, so a later
row or story can supersede an earlier one. The checks were written from the source data before any run.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from factoid.evals import Suite

DATA = Path(__file__).resolve().parent.parent / "data"


class Playoffs(Suite):
    name = "playoffs"
    description = "The Warriors' 2022 playoff run: stats, games, recaps, interviews, and articles."
    parallel = 1  # in date order, so later documents supersede earlier ones

    def documents(self, limit: int | None = None):
        from nba import documents as d

        if not (DATA / "games.csv").exists():
            raise FileNotFoundError("run `uv run python fetch.py` first")
        for name, klass in (("games.csv", d.GameLog), ("box_scores.csv", d.BoxScore),
                            ("player_totals.csv", d.PlayerTotals)):
            yield klass((DATA / name).read_text(), uri=f"data/{name}", title=klass.description())
        prose = []
        for folder, klass, when in (("recaps", d.Recap, "published"), ("interviews", d.Interview, "said_at"),
                                    ("articles", d.Article, "published")):
            for path in sorted((DATA / folder).glob("*.txt")):
                meta = json.loads(path.with_name(path.name + ".meta.json").read_text())
                prose.append((folder == "articles", meta[when], path, klass, meta))
        prose.sort(key=lambda item: item[:2])  # articles, written later, go last
        for _, _, path, klass, meta in prose[:limit]:
            yield klass(path.read_text(), metadata=meta, uri=f"data/{path.parent.name}/{path.name}",
                        title=meta["title"])

    def score(self, app, results) -> dict[str, Any]:
        from nba.entities import Game, Player, Series, Team
        from nba.facts import Injury, Milestone, Remark

        checks: dict[str, bool] = {}
        facts = app.list_facts()
        kinds = {r.document.id: type(r.document).__name__ for r in results}

        def about(entity, text=None, current=False):
            return [f for f in (entity.facts(include_retired=True) if entity else [])
                    if (text is None or text.lower() in f.text.lower()) and (not current or f.status == "current")]

        curry = Player.find("3975")  # ESPN's id for Stephen Curry
        game6 = Game.find("401442535")
        finals = Series.find("2022 NBA Finals")
        celtics = Team.find("Boston Celtics")
        checks["game log: Game 6 of the Finals, 103-90 over Boston"] = any(
            "103-90" in f.text and "Boston Celtics" in f.text for f in about(game6))
        # The game log's standings: each replaces the one before, so none of the earlier ones is current, and the 4-2
        # title is current from some source. (A later article restating the result can take it over.)
        standings = [f for f in about(finals, "In the 2022 NBA Finals, the") if kinds.get(f.document_id) == "GameLog"]
        title = [f for f in about(finals, current=True) if "4-2" in f.text.replace("–", "-")
                 and ("won the series" in f.text or "beat the Boston Celtics" in f.text)]
        checks["game log: earlier Finals standings replaced, the 4-2 title current"] = len(standings) == 6 and \
            not any(f.status == "current" for f in standings if "4-2" not in f.text) and bool(title)
        hits = app.search_facts("Who leads the 2022 NBA Finals series?", as_of="2022-06-10T12:00:00Z", top_k=3)
        checks["search: after Game 3 of the Finals, the Celtics lead 2-1"] = bool(hits) and \
            "Celtics lead the series 2-1" in hits[0].fact.text
        checks["box score: Curry's 34 points in Finals Game 6, linked to the game"] = any(
            "34 points" in f.text and any(m.entity_id == game6.id for m in f.mentions) for f in about(curry)) \
            if curry and game6 else False
        checks["totals: Curry averaged 27.4 points"] = bool(about(curry, "27.4 points"))
        sources = {kinds.get(f.document_id) for f in about(curry)}
        checks["entities: Curry links stats, recaps, interviews, and articles"] = \
            {"BoxScore", "Recap", "Interview", "Article"} <= sources
        checks["entities: one Stephen Curry"] = sum(
            1 for row in app.store.query("select name from entities where merged_into is null and class = 'Player'")
            if "curry" in row["name"].lower() and "seth" not in row["name"].lower()) == 1
        checks["recaps: Curry was Finals MVP, a milestone"] = any(
            "mvp" in f.text.lower() and f.has(Milestone) for f in about(curry))
        checks["interviews: a remark by Curry, quoted with him as the speaker"] = any(
            isinstance(f, Remark) and any(q.speaker and "CURRY" in q.speaker for q in f.quotes) for f in about(curry))
        checks["injury: a fact about an injury to Curry or Klay Thompson"] = any(
            f.has(Injury) for name in ("Stephen Curry", "Klay Thompson") for f in about(Player.find(name)))
        checks["entities: the Celtics link games and recaps"] = {"GameLog", "Recap"} <= {
            kinds.get(f.document_id) for f in about(celtics)}

        passed = sum(checks.values())
        statuses_count = Counter(f.status for f in facts)
        classes = Counter(type(f).__name__ for f in facts if f.status != "retracted")
        by_kind = Counter(kinds.get(f.document_id) for f in facts if f.status != "retracted")
        entities = Counter(row["class"] for row in app.store.query(
            "select class from entities where merged_into is null"))
        return {"passed": f"{passed}/{len(checks)}", "score": round(passed / len(checks), 3),
                "checks": {k: "ok" if v else "FAIL" for k, v in checks.items()},
                "facts": dict(statuses_count), "fact_classes": dict(classes), "facts_by_document": dict(by_kind),
                "entities": dict(entities)}
