"""Amendments: real contract chains from CUAD, scored on supersession, as-of search, and time.

Each chain is a base agreement and its amendments, ingested in signing order. The gold labels are ours, written by
reading the contracts:

- supersedes: a base clause an amendment replaces. Scored when the fact quoting the old clause is no longer current
  and a fact quoting the new clause superseded or ended it.
- unchanged: a clause no amendment touches. Scored when the fact quoting it is still current. This catches false
  supersession, the failure that matters most in diligence.
- as of: a search with `as_of=` must rank a fact quoting the clause in force on that date above a fact quoting the
  clause that was not.
- time: a clause with a dated window must give its fact `valid_from` or `valid_until` in the right year.

Text: CUAD (CC BY 4.0). Some text is redacted in the filings (shown as [*] or [***]).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from factoid.evals import Suite

from .cuad import DATA, URL

CHAINS: list[dict[str, Any]] = [
    {
        "name": "netgear",
        "documents": [
            {"key": "netgear-base", "title": "NETGEAR,INC_04_21_2003-EX-10.16-DISTRIBUTOR AGREEMENT",
             "end": r"AMENDMENT\s+TO THE\s+DISTRIBUTOR AGREEMENT", "signed_at": "1996-03-01T00:00:00Z",
             "name": "Distributor Agreement between Ingram Micro and NETGEAR"},
            {"key": "netgear-a1",
             "title": "NETGEAR,INC_04_21_2003-EX-10.16- AMENDMENT #2 TO THE DISTRIBUTION AGREEMENT",
             "start": r"This Amendment is entered into effective October 1,1996", "end": r"\[INGRAM MICRO LOGO\]",
             "signed_at": "1996-10-01T00:00:00Z",
             "name": "Amendment to the Distributor Agreement between Ingram Micro and NETGEAR"},
            {"key": "netgear-a2",
             "title": "NETGEAR,INC_04_21_2003-EX-10.16- AMENDMENT #2 TO THE DISTRIBUTION AGREEMENT",
             "start": r"AMENDMENT #2 TO THE", "signed_at": "1998-07-15T00:00:00Z",
             "name": "Amendment #2 to the Distribution Agreement between Ingram Micro and NETGEAR"},
        ],
        "supersedes": [
            ("netgear-base", "outside of the Territory identified herein as the United States",
             "netgear-a1", "is amended to be the United States and [*]"),
            ("netgear-a1", "is amended to be the United States and [*]",
             "netgear-a2", "Section 2, TERRITORY, is amended to be United States, [*]"),
        ],
        "unchanged": [
            ("netgear-base", "governed by the laws of the State of California"),
            ("netgear-base", "may be canceled at any time without cause, by either party upon ninety (90) days"),
        ],
        "as_of": [
            ("In what territory may Ingram Micro distribute NETGEAR products?", "1996-06-01T00:00:00Z",
             ("netgear-base", "outside of the Territory identified herein as the United States"),
             ("netgear-a1", "is amended to be the United States and [*]")),
            ("In what territory may Ingram Micro distribute NETGEAR products?", "1997-06-01T00:00:00Z",
             ("netgear-a1", "is amended to be the United States and [*]"),
             ("netgear-base", "outside of the Territory identified herein as the United States")),
            ("In what territory may Ingram Micro distribute NETGEAR products?", "2000-01-01T00:00:00Z",
             ("netgear-a2", "Section 2, TERRITORY, is amended to be United States, [*]"),
             ("netgear-a1", "is amended to be the United States and [*]")),
        ],
        "time": [
            ("netgear-a1", "During the initial one year period beginning on the Amendment Date", "valid_until", "1997"),
        ],
    },
    {
        "name": "federated",
        "documents": [
            {"key": "federated-base",
             "title": "FEDERATEDGOVERNMENTINCOMESECURITIESINC_04_28_2020-EX-99.SERV AGREE-SERVICES AGREEMENT",
             "signed_at": "2004-01-01T00:00:00Z",
             "name": "Services Agreement between Federated Investment Management Company and Federated Advisory "
                     "Services Company"},
            {"key": "federated-a1",
             "title": "FEDERATEDGOVERNMENTINCOMESECURITIESINC_04_28_2020-EX-99.SERV AGREE-SERVICES AGREEMENT_AMENDMENT",
             "signed_at": "2009-03-30T00:00:00Z",
             "name": "Amendment to the Federated Services Agreement"},
            {"key": "federated-a2",
             "title": "FEDERATEDGOVERNMENTINCOMESECURITIESINC_04_28_2020-EX-99.SERV AGREE-SERVICES "
                      "AGREEMENT_SECONDAMENDMENT",
             "signed_at": "2016-03-01T00:00:00Z",
             "name": "Second Amendment to the Federated Services Agreement"},
        ],
        "supersedes": [],
        "unchanged": [
            ("federated-base", "responsible for data integrity, creation of attribution reports"),
        ],
        "as_of": [],
        "time": [],
    },
    {
        "name": "bioamber",
        "documents": [
            {"key": "bioamber-base", "title": "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT AGREEMENT (1)",
             "end": r"AMENDMENT 1 TO DEVELOPMENT AGREEMENT", "signed_at": "2010-04-15T00:00:00Z",
             "name": "Development Agreement between Cargill and BioAmber"},
            {"key": "bioamber-a1", "title": "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT AGREEMENT - First Amendment",
             "start": r"AMENDMENT 1 TO DEVELOPMENT AGREEMENT", "end": r"AMENDMENTS TO COMMERCIAL LICENSE AGREEMENT",
             "signed_at": "2011-07-05T00:00:00Z",
             "name": "First Amendment to the Development Agreement between Cargill and BioAmber"},
        ],
        "supersedes": [],
        "unchanged": [
            ("bioamber-base", "Cargill will make available up to [***] FTE persons per year"),
        ],
        "as_of": [],
        "time": [
            ("bioamber-a1", "during the period of July 5, 2011, through September 30, 2011", "valid_until", "2011"),
        ],
    },
]


@dataclass
class Located:
    doc_id: str
    start: int
    end: int


def _pattern(snippet: str) -> re.Pattern[str]:
    words = snippet.split()
    return re.compile(r"\s+".join(re.escape(w) for w in words))


def load_full() -> dict[str, str]:
    target = DATA / "CUADv1.json"
    if not target.exists():
        import io
        import urllib.request
        import zipfile

        DATA.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL) as response:  # noqa: S310 - fixed https URL
            zipfile.ZipFile(io.BytesIO(response.read())).extract("CUADv1.json", DATA)
    return {x["title"]: x["paragraphs"][0]["context"] for x in json.loads(target.read_text())["data"]}


def _cut(text: str, start: str | None, end: str | None) -> str:
    if start:
        match = re.search(start, text)
        if match is None:
            raise ValueError(f"start marker {start!r} not found")
        text = text[match.start():]
    if end:
        match = re.search(end, text)
        if match is not None and match.start() > 0:
            text = text[:match.start()]
    return text


class Amendments(Suite):
    name = "amendments"
    description = "Real CUAD contract chains: supersession, as-of search, and time."
    parallel = 1  # a chain must be ingested in order

    def documents(self, limit: int | None = None):
        from legal.documents import Contract

        full = load_full()
        self.texts: dict[str, str] = {}
        chains = CHAINS[:limit] if limit else CHAINS
        self.chains = chains
        for chain in chains:
            for spec in chain["documents"]:
                text = _cut(full[spec["title"]], spec.get("start"), spec.get("end"))
                doc_id = f"amend_{spec['key'].replace('-', '_')}"
                self.texts[spec["key"]] = text
                yield Contract(text, id=doc_id, uri=f"cuad:{spec['title']}#{spec['key']}", title=spec["name"],
                               metadata={"signed_at": spec["signed_at"]})

    def locate(self, key: str, snippet: str) -> Located:
        match = _pattern(snippet).search(self.texts[key])
        if match is None:
            raise ValueError(f"snippet not found in {key}: {snippet!r}")
        return Located(f"amend_{key.replace('-', '_')}", match.start(), match.end())

    def quoting(self, app: Any, located: Located) -> list[Any]:
        facts = app.list_facts(document_id=located.doc_id)
        return [f for f in facts if any(q.start < located.end and located.start < q.end for q in f.quotes)]

    def score(self, app, results) -> dict[str, Any]:
        out: dict[str, Any] = {}
        hits = total = 0
        details = []
        for chain in self.chains:
            for old_key, old_snip, new_key, new_snip in chain["supersedes"]:
                total += 1
                old = self.quoting(app, self.locate(old_key, old_snip))
                new_ids = {f.id for f in self.quoting(app, self.locate(new_key, new_snip))}
                replaced = [f for f in old if f.status in ("superseded", "ended") and any(
                    r["fact_id"] in new_ids for r in app.store.relations(f.id)
                    if r["relation"] in ("supersedes", "ends") and r["other_id"] == f.id)]
                ok = bool(replaced)
                hits += ok
                details.append({"supersedes": old_snip, "ok": ok, "old_facts": len(old), "new_facts": len(new_ids)})
        out["supersede_recall"] = round(hits / total, 3) if total else None

        kept = total = 0
        for chain in self.chains:
            for key, snippet in chain["unchanged"]:
                total += 1
                facts = self.quoting(app, self.locate(key, snippet))
                ok = bool(facts) and all(f.status == "current" for f in facts)
                kept += ok
                details.append({"unchanged": snippet, "ok": ok, "facts": len(facts),
                                "statuses": [f.status for f in facts]})
        out["unchanged_kept"] = round(kept / total, 3) if total else None

        base_ids = {f"amend_{d['key'].replace('-', '_')}" for c in self.chains for d in c["documents"][:1]}
        base_facts = [f for doc_id in base_ids for f in app.list_facts(document_id=doc_id)]
        expected_old = set()
        for chain in self.chains:
            for old_key, old_snip, _, _ in chain["supersedes"]:
                expected_old |= {f.id for f in self.quoting(app, self.locate(old_key, old_snip))}
        changed = [f for f in base_facts if f.status != "current" and f.id not in expected_old]
        out["false_change_rate"] = round(len(changed) / len(base_facts), 3) if base_facts else None
        out["false_changes"] = [f"{f.status}: {f.text[:160]}" for f in changed[:8]]

        good = total = 0
        for chain in self.chains:
            for query, as_of, (want_key, want_snip), (old_key, old_snip) in chain["as_of"]:
                total += 1
                want = {f.id for f in self.quoting(app, self.locate(want_key, want_snip))}
                stale = {f.id for f in self.quoting(app, self.locate(old_key, old_snip))}
                hits_ = app.search_facts(query, as_of=as_of, top_k=5)
                ranks = [h.fact.id for h in hits_]
                first_want = next((i for i, fid in enumerate(ranks) if fid in want), None)
                first_stale = next((i for i, fid in enumerate(ranks) if fid in stale), None)
                ok = first_want is not None and (first_stale is None or first_want < first_stale)
                good += ok
                details.append({"as_of": as_of, "ok": ok, "want_rank": first_want, "stale_rank": first_stale})
        out["as_of_accuracy"] = round(good / total, 3) if total else None

        good = total = 0
        for chain in self.chains:
            for key, snippet, attribute, year in chain["time"]:
                total += 1
                facts = self.quoting(app, self.locate(key, snippet))
                ok = any(getattr(f, attribute) is not None and str(getattr(f, attribute).year) == year for f in facts)
                good += ok
                details.append({"time": snippet, "ok": ok,
                                "values": [str(getattr(f, attribute)) for f in facts]})
        out["time_captured"] = round(good / total, 3) if total else None
        out["details"] = details
        return out
