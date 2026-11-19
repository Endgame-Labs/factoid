"""CUAD: lawyer-labeled clauses in 102 test contracts, scored against Factoid's facts.

Data: the Contract Understanding Atticus Dataset (CC BY 4.0), https://www.atticusprojectai.org/cuad. The scorer is our
own; it borrows CUAD's idea of matching by word overlap so numbers are comparable in spirit to the paper's.

What is scored, per CUAD category that maps to one of our traits:

- clause detection, per contract: does any fact carry the trait (precision, recall, F1), and the best trait
  probability among the contract's facts as a confidence (AUPR, precision at 80% recall).
- span recall: the share of gold clauses quoted by a fact that carries the trait. A fact's quotes are whole
  sentences, so a gold clause counts when a quoted sentence overlaps it.
- span precision: the share of facts with the trait that quote at least one gold clause of that category.
- extraction coverage: the share of gold clauses quoted by any kept fact, whatever its traits. When coverage is low,
  the extractor missed the clause; when coverage is high and span recall is low, the trait judgment missed it.

And for time: the share of contracts with a gold Effective Date or Expiration Date where a fact quoting it carries
`valid_from` or `valid_until` with the same year.
"""

from __future__ import annotations

import io
import json
import random
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from factoid.evals import Suite, aupr, precision_at_recall, prf

DATA = Path(__file__).resolve().parent.parent / "data" / "cuad"
URL = "https://github.com/TheAtticusProject/cuad/raw/main/data.zip"

TIME_CATEGORIES = {"Agreement Date": "valid_from", "Effective Date": "valid_from", "Expiration Date": "valid_until"}


def fetch() -> Path:
    """Download CUAD's test split once."""
    target = DATA / "test.json"
    if not target.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        target.write_bytes(archive.read("test.json"))
    return target


def load_contracts() -> list[dict[str, Any]]:
    data = json.loads(fetch().read_text())["data"]
    contracts = []
    for item in data:
        para = item["paragraphs"][0]
        gold: dict[str, list[tuple[int, int, str]]] = {}
        for qa in para["qas"]:
            category = qa["id"].split("__")[-1]
            gold[category] = [(a["answer_start"], a["answer_start"] + len(a["text"]), a["text"])
                              for a in qa["answers"]]
        contracts.append({"title": item["title"], "text": para["context"], "gold": gold})
    random.Random(7).shuffle(contracts)  # a stable, representative order for --limit
    return contracts


_WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def jaccard(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


class Cuad(Suite):
    name = "cuad"
    description = "CUAD test split: clause traits and contract dates."
    parallel = 4
    offset = 0
    count: int | None = None  # how many contracts from offset; None means every one

    def documents(self, limit: int | None = None):
        from legal.documents import Contract

        self.contracts = {}
        contracts = load_contracts()[self.offset:][:self.count]
        for contract in contracts[:limit]:
            doc_id = "cuad_" + re.sub(r"[^a-z0-9]+", "_", contract["title"].lower())[:80]
            self.contracts[doc_id] = contract
            yield Contract(contract["text"], uri=f"cuad:{contract['title']}", id=doc_id, title=contract["title"])

    def score(self, app, results) -> dict[str, Any]:
        from legal.facts import CUAD_TRAITS

        per_trait: dict[str, Any] = {}
        totals = {"tp": 0, "fp": 0, "fn": 0, "span_hit": 0, "span_total": 0, "covered": 0, "fact_hit": 0,
                  "fact_total": 0, "jaccard_hit": 0}
        doc_facts = {r.document.id: r.facts for r in results}
        for trait, category in CUAD_TRAITS.items():
            key = trait.key()
            tp = fp = fn = 0
            scores, labels = [], []
            span_hit = span_total = covered = fact_hit = fact_total = jaccard_hit = 0
            for doc_id, facts in doc_facts.items():
                gold = self.contracts[doc_id]["gold"].get(category, [])
                carriers = [f for f in facts if f.has(key)]
                predicted, actual = bool(carriers), bool(gold)
                tp += predicted and actual
                fp += predicted and not actual
                fn += actual and not predicted
                scores.append(max((f.trait_scores.get(key, 0.0) for f in facts), default=0.0))
                labels.append(actual)
                for start, end, text in gold:
                    span_total += 1
                    if any(overlaps((q.start, q.end), (start, end)) for f in carriers for q in f.quotes):
                        span_hit += 1
                    if any(overlaps((q.start, q.end), (start, end)) for f in facts for q in f.quotes):
                        covered += 1
                    if any(jaccard(q.text, text) >= 0.5 for f in carriers for q in f.quotes):
                        jaccard_hit += 1
                for fact in carriers:
                    fact_total += 1
                    if any(overlaps((q.start, q.end), (s, e)) for q in fact.quotes for s, e, _ in gold):
                        fact_hit += 1
            per_trait[key] = {
                **{k: v for k, v in prf(tp, fp, fn).items() if k in ("precision", "recall", "f1")},
                "aupr": aupr(scores, labels),
                "p_at_r80": precision_at_recall(scores, labels, 0.8),
                "span_recall": round(span_hit / span_total, 3) if span_total else None,
                "span_precision": round(fact_hit / fact_total, 3) if fact_total else None,
                "coverage": round(covered / span_total, 3) if span_total else None,
                "positives": sum(labels),
            }
            for name, value in (("tp", tp), ("fp", fp), ("fn", fn), ("span_hit", span_hit),
                                ("span_total", span_total), ("covered", covered), ("fact_hit", fact_hit),
                                ("fact_total", fact_total), ("jaccard_hit", jaccard_hit)):
                totals[name] += value
        auprs = [v["aupr"] for v in per_trait.values() if v["positives"]]
        overall = {
            **prf(totals["tp"], totals["fp"], totals["fn"]),
            "mean_aupr": round(sum(auprs) / len(auprs), 4) if auprs else 0.0,
            "span_recall": round(totals["span_hit"] / totals["span_total"], 4) if totals["span_total"] else 0.0,
            "span_jaccard_recall": round(totals["jaccard_hit"] / totals["span_total"], 4)
            if totals["span_total"] else 0.0,
            "span_precision": round(totals["fact_hit"] / totals["fact_total"], 4) if totals["fact_total"] else 0.0,
            "coverage": round(totals["covered"] / totals["span_total"], 4) if totals["span_total"] else 0.0,
        }
        return {"overall": overall, "time": self._time(doc_facts), "traits": per_trait}

    def _time(self, doc_facts: dict[str, list[Any]]) -> dict[str, Any]:
        out = {}
        for category, attribute in TIME_CATEGORIES.items():
            hit = total = 0
            for doc_id, facts in doc_facts.items():
                gold = self.contracts[doc_id]["gold"].get(category, [])
                years = {y for _, _, text in gold for y in re.findall(r"\b(19\d\d|20\d\d)\b", text)}
                if not years:
                    continue
                total += 1
                quoting = [f for f in facts for q in f.quotes for s, e, _ in gold if overlaps((q.start, q.end), (s, e))]
                # An end given as a length of time ("24 months from January 10, 2019") ends after the years shown.
                computed = attribute == "valid_until" and re.search(r"\b(months?|years?)\b", " ".join(
                    text for _, _, text in gold), re.I) is not None
                if any(getattr(f, attribute) is not None and (
                        str(getattr(f, attribute).year) in years
                        or (computed and getattr(f, attribute).year > max(int(y) for y in years)))
                       for f in quoting):
                    hit += 1
            out[category] = {"field": attribute, "contracts": total,
                             "captured": round(hit / total, 3) if total else None}
        return out


class CuadHeldOut(Cuad):
    """Contracts 21 to 40 of the same shuffled test split. Never used while tuning floors, thresholds, or prompts
    (tuning used contracts 1 to 20)."""

    name = "cuad_heldout"
    description = "CUAD test contracts 21 to 40, held out from tuning."
    offset = 20
    count = 20


class CuadFresh(Cuad):
    """Contracts 41 to 60: first scored after the last change to floors, thresholds, and prompts."""

    name = "cuad_fresh"
    description = "CUAD test contracts 41 to 60, never seen before the final run."
    offset = 40
    count = 20

