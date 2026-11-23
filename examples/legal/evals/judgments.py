"""Small labeled sets for single decisions, written by hand before any run.

- `linking`: does a mention link to the entity it names, and only to it, when the names differ a little (issue #23)?
- `grounded_cases`: does the `grounded` question pass a fact its passage supports, and fail one that says more, such as
  a role that grows past what the passage gives (issue #19)?
- `slip_notes`: short notes where the extractor tends to add a year or a consequence the note does not state. Run with
  `--vary fact_evals=default,@evals.variants:GROUNDED_REPAIR` to compare dropping such a fact with trimming it (#6).
"""

from __future__ import annotations

from typing import Any

from factoid import Entity, Fact, Mention, ProseDocument
from factoid.evals import Suite, prf
from factoid.fact_evals import DEFAULT_FLOORS, MODEL_FLOORS, QUESTIONS

# (registered name, kind, mention in a fact, the fact, same thing?)
LINKS: list[tuple[str, str, str, str, bool]] = [
    ("Acme Corporation", "company", "Acme Corp", "Acme Corp signed the order form.", True),
    ("Acme Corporation", "company", "ACME", "ACME asked for a discount.", True),
    ("International Business Machines", "company", "IBM", "IBM renewed its support contract.", True),
    ("Robert Smith", "person", "Bob Smith", "Bob Smith approved the budget.", True),
    ("Katherine O'Neill", "person", "Kate O'Neill", "Kate O'Neill joined the call.", True),
    ("Brightwater Logistics, Inc.", "company", "Brightwater", "Brightwater wants a pilot in December.", True),
    ("The Coca-Cola Company", "company", "Coca-Cola", "Coca-Cola extended the term by a year.", True),
    ("Kestrel Foods LLC", "company", "Kestrel", "Kestrel is comparing two vendors.", True),
    ("Massachusetts Institute of Technology", "university", "MIT", "MIT licensed the patent.", True),
    ("Johnson & Johnson", "company", "Johnson and Johnson", "Johnson and Johnson filed the claim.", True),
    ("Deutsche Bank AG", "company", "Deutsche Bank", "Deutsche Bank arranged the loan.", True),
    ("Grace Liu", "person", "Ms. Liu", "Ms. Liu said the training is done.", True),
    ("Acme Corporation", "company", "Acme Labs", "Acme Labs filed a patent.", False),
    ("John Smith", "person", "Jane Smith", "Jane Smith signed the lease.", False),
    ("Apple Inc.", "company", "Apple Hospitality REIT", "Apple Hospitality REIT bought a hotel.", False),
    ("Delta Air Lines", "company", "Delta Dental", "Delta Dental raised premiums.", False),
    ("Orion Robotics, Inc.", "company", "Orion Health", "Orion Health hired a new CFO.", False),
    ("Vega Components Corp.", "company", "Vega Holdings", "Vega Holdings owns the building.", False),
    ("Robert Smith", "person", "Robert Smith Jr.", "Robert Smith Jr. inherited the shares.", False),
    ("General Motors Company", "company", "General Mills", "General Mills recalled a cereal.", False),
    ("Kestrel Foods LLC", "company", "Kestrel Aerospace", "Kestrel Aerospace won the contract.", False),
    ("Brightwater Logistics, Inc.", "company", "Brightwater Capital", "Brightwater Capital led the round.", False),
    ("Grace Liu", "person", "Grace Lee", "Grace Lee chairs the committee.", False),
    ("Massachusetts Institute of Technology", "university", "Michigan Tech", "Michigan Tech hosted the event.", False),
]

# (passage, fact, does the passage support the fact?)
GROUNDED: list[tuple[str, str, bool]] = [
    ("Tom Becker owns the security review for the Kestrel account.",
     "Tom Becker owns the security review for the Kestrel account.", True),
    ("Tom Becker owns the security review for the Kestrel account.",
     "Tom Becker decides on the Kestrel account.", False),
    ("Tom Becker owns the security review for the Kestrel account.",
     "Tom Becker is the decision maker for the Kestrel deal.", False),
    ("Priya Nair is on the buying committee.", "Priya Nair approves the purchase.", False),
    ("Priya Nair is on the buying committee.", "Priya Nair is a member of the buying committee.", True),
    ("Grace Liu raised that the second clinic's network upgrade slips to January, which moves its go-live.",
     "Grace Liu raised that the second clinic's network upgrade slips to January 2027.", False),
    ("Grace Liu raised that the second clinic's network upgrade slips to January, which moves its go-live.",
     "Grace Liu raised that the second clinic's network upgrade slips to January, putting the go-live timeline at "
     "risk of failure.", False),
    ("Grace Liu raised that the second clinic's network upgrade slips to January, which moves its go-live.",
     "Grace Liu raised that the second clinic's network upgrade slips to January, which moves the clinic's go-live.",
     True),
    ("Dana Ruiz said the pilot can start on 1 December 2026 if security signs off.",
     "Dana Ruiz said the pilot can start on 1 December 2026 if security signs off.", True),
    ("Dana Ruiz said the pilot can start on 1 December 2026 if security signs off.",
     "Dana Ruiz said the pilot will start on 1 December 2026.", False),
    ("Sam agreed to send a pilot plan by 10 November 2026.",
     "Sam agreed to send a pilot plan by 10 November 2026.", True),
    ("Sam agreed to send a pilot plan by 10 November 2026.",
     "Sam sent a pilot plan on 10 November 2026.", False),
    ("The warehouse team loses about six hours a week reconciling shipment exceptions by hand.",
     "The warehouse team spends about six hours a week reconciling shipment exceptions by hand.", True),
    ("The warehouse team loses about six hours a week reconciling shipment exceptions by hand.",
     "The warehouse team loses about six hours a week, which costs the company $50,000 a year.", False),
    ("Vega's liability to Orion is capped at $1,000,000.", "Vega's liability to Orion is capped at $1M.", True),
    ("Vega's liability to Orion is capped at $1,000,000.",
     "Vega's liability to Orion is capped at $1M, the lowest cap in Orion's contracts.", False),
]

# Notes like the one in issue #6: a true claim the extractor tends to pad with a year or a consequence.
SLIPS: list[tuple[str, str]] = [
    ("Grace Liu said the Tacoma clinic's staff training is done. Grace Liu raised that the second clinic's network "
     "upgrade slips to January, which moves its go-live.", "January"),
    ("Omar Haddad said the Fresno warehouse scanner rollout is finished. Omar Haddad raised that the Reno warehouse's "
     "scanner rollout slips to March, which moves its cutover.", "March"),
    ("Priya Nair said the Denver office's badge readers are installed. Priya Nair raised that the Austin office's "
     "badge readers slip to February, which moves its move-in.", "February"),
    ("Dana Ruiz said the first store's payment terminals are live. Dana Ruiz raised that the second store's terminal "
     "install slips to April, which moves its opening.", "April"),
    ("Sam Okoye said the east plant's sensors are calibrated. Sam Okoye raised that the west plant's sensor install "
     "slips to May, which moves its first production run.", "May"),
]


class Linking(Suite):
    name = "linking"
    description = "Near-miss names: same entity or a different one (issue #23)."

    def documents(self, limit: int | None = None):
        return []

    def score(self, app: Any, results: list[Any]) -> dict[str, Any]:
        cases = LINKS
        registered: dict[str, Entity] = {}
        for name, kind, *_ in cases:
            if name not in registered:
                registered[name] = Entity.create(name, kind=kind)
        tp = fp = fn = tn = 0
        rows = []
        asked: list[float] = []  # the link question's top probability, linked or not, to set link_threshold by
        ask = app.client.ask

        def spy(state: Any, questions: dict) -> Any:
            judgments = ask(state, questions)
            if "E0" in questions:  # the link question, not the discovery questions that may follow it
                asked.append(max(float(judgments[k]) for k in questions))
            return judgments

        app.client.ask = spy
        for i, (name, kind, mention_text, text, same) in enumerate(cases):
            fact = Fact(text, mentions=[Mention(mention_text, kind=kind, role="subject")])
            fact.document_id = f"linking_{i}"
            asked.clear()
            fact.link()
            linked = fact.mentions[0].entity_id == registered[name].id
            tp, fp = tp + (same and linked), fp + (not same and linked)
            fn, tn = fn + (same and not linked), tn + (not same and not linked)
            rows.append({"name": name, "mention": mention_text, "same": same, "linked": linked,
                         "method": fact.mentions[0].method, "p": round(asked[0], 3) if asked else None,
                         "ok": linked == same})
        app.client.ask = ask
        return {**prf(tp, fp, fn), "true_negatives": tn, "accuracy": round((tp + tn) / len(cases), 3),
                "cases": len(cases), "details": rows}


class GroundedCases(Suite):
    name = "grounded_cases"
    description = "Fact and passage pairs for the grounded question, including facts that say more (issue #19)."

    def documents(self, limit: int | None = None):
        return []

    def score(self, app: Any, results: list[Any]) -> dict[str, Any]:
        model = app.client.models.get("choose")
        floor = {**DEFAULT_FLOORS, **MODEL_FLOORS.get(getattr(model, "name", ""), {})}["grounded"]
        rows, right = [], 0
        for passage, text, supported in GROUNDED:
            state = {"fact": text, "document_date": None, "cited_passages": [{"speaker": None, "text": passage}]}
            p = float(app.client.ask(state, {"grounded": QUESTIONS["grounded"]})["grounded"])
            ok = (p >= floor) == supported
            right += ok
            rows.append({"fact": text, "supported": supported, "p": round(p, 3), "ok": ok})
        wrong_pass = sum(1 for r in rows if not r["supported"] and not r["ok"])
        return {"accuracy": round(right / len(rows), 3), "floor": floor, "cases": len(rows),
                "unsupported_passed": wrong_pass, "supported_failed": sum(1 for r in rows if r["supported"] and
                                                                          not r["ok"]), "details": rows}


class SlipNotes(Suite):
    name = "slip_notes"
    description = "Notes whose second claim the extractor tends to pad; is a fact about the slip kept (issue #6)?"
    parallel = 5

    def documents(self, limit: int | None = None):
        for i, (text, _) in enumerate(SLIPS[:limit]):
            # The base class, not a subclass: a subclass here would join the app's document classes in every suite.
            yield ProseDocument(text, id=f"slip_{i}", uri=f"slip_{i}.txt", title="Call note",
                                metadata={"source_datetime": "2026-11-04T17:00:00Z"})  # a date invites a year

    def score(self, app: Any, results: list[Any]) -> dict[str, Any]:
        rows = []
        for result, (_, month) in zip(results, SLIPS):
            slips = [f.text for f in result.facts if month in f.text]
            rows.append({"document": result.document.id, "slip_kept": bool(slips), "facts": slips,
                         "padded": [t for t in slips if "202" in t.split(month, 1)[1][:6] or "risk" in t]})
        return {"slip_kept": f"{sum(r['slip_kept'] for r in rows)}/{len(rows)}",
                "padded_kept": sum(bool(r["padded"]) for r in rows), "details": rows}
