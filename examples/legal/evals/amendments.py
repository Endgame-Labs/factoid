"""Amendments: real contract chains from CUAD, scored on supersession, as-of search, and time.

Each chain is a base agreement and its amendments, ingested in signing order. The gold labels are mine, written by
reading the contracts:

- supersedes: a base clause an amendment replaces. Scored (`supersede_recall`) when a fact quoting the old clause is
  no longer current and a fact quoting the new clause superseded or ended it. `supersede_recall_any` also counts a
  fact replaced by any fact of the amending document, since an amendment that rewrites a whole section can replace
  the old clause with a fact of that section other than the one the label names.
- unchanged: a clause no amendment touches. Scored when the fact quoting it is still current. This catches false
  supersession, the failure that matters most in diligence.
- false changes: of every fact in a chain's documents that no label expects to change, the share that is not current
  (`false_change_rate`). `false_change_rate_base` reads only the base agreements, as the first runs did.
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
from .qa import qa_scores

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
            # Added 2026-11-16, labeled before any run: a paraphrase.
            ("Where is Ingram Micro allowed to resell NETGEAR gear?", "1997-06-01T00:00:00Z",
             ("netgear-a1", "is amended to be the United States and [*]"),
             ("netgear-base", "outside of the Territory identified herein as the United States")),
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


# Held out: never looked at while tuning floors, thresholds, or prompts. Scored by `AmendmentsHeldOut`.
HELD_OUT: list[dict[str, Any]] = [
    {
        "name": "neon",
        "documents": [
            {"key": "neon-base", "title": "NEONSYSTEMSINC_03_01_1999-EX-10.5-DISTRIBUTOR AGREEMENT_New",
             "signed_at": "1996-01-01T00:00:00Z",
             "name": "Distributor Agreement between Peregrine/Bridge Transfer Corporation and NEON Systems"},
            {"key": "neon-a1", "title": "NEONSYSTEMSINC_03_01_1999-EX-10.5-DISTRIBUTOR AGREEMENT_Amendment",
             "start": r"FIRST AMENDMENT TO DISTRIBUTOR AGREEMENT", "signed_at": "1999-01-01T00:00:00Z",
             "name": "First Amendment to the Distributor Agreement between Peregrine/Bridge and NEON Systems"},
        ],
        "supersedes": [
            ("neon-base", "a licensee fee equal to 50% of all revenues received",
             "neon-a1", "a royalty equal to the Specified Royalty Percentage of all revenues received"),
            ("neon-base", "during the first year of the term hereof will be payable one hundred and twenty (120) days",
             "neon-a1", "sixty (60) days after the date of the applicable invoice"),
        ],
        "unchanged": [
            ("neon-base", "Licensee represents and warrants that it has all requisite power and authority to execute"),
        ],
        "as_of": [
            ("How many days after the invoice must NEON Systems pay Peregrine/Bridge?", "1997-06-01T00:00:00Z",
             ("neon-base", "during the first year of the term hereof will be payable one hundred and twenty (120) days"),
             ("neon-a1", "sixty (60) days after the date of the applicable invoice")),
            ("How many days after the invoice must NEON Systems pay Peregrine/Bridge?", "2000-01-01T00:00:00Z",
             ("neon-a1", "sixty (60) days after the date of the applicable invoice"),
             ("neon-base", "during the first year of the term hereof will be payable one hundred and twenty (120) days")),
            # Added 2026-11-16, labeled before any run.
            ("What royalty does NEON Systems owe Peregrine/Bridge on revenue from licensed products?",
             "1997-06-01T00:00:00Z",
             ("neon-base", "a licensee fee equal to 50% of all revenues received"),
             ("neon-a1", "a royalty equal to the Specified Royalty Percentage of all revenues received")),
            ("What royalty does NEON Systems owe Peregrine/Bridge on revenue from licensed products?",
             "2000-01-01T00:00:00Z",
             ("neon-a1", "a royalty equal to the Specified Royalty Percentage of all revenues received"),
             ("neon-base", "a licensee fee equal to 50% of all revenues received")),
            ("When does the term of the NEON Systems distributor agreement end?", "1997-06-01T00:00:00Z",
             ("neon-base", "the date that is two (2) years after the date of this Agreement"),
             ("neon-a1", "This Agreement shall be effective through and including March 31, 2004")),
            ("When does the term of the NEON Systems distributor agreement end?", "2000-01-01T00:00:00Z",
             ("neon-a1", "This Agreement shall be effective through and including March 31, 2004"),
             ("neon-base", "the date that is two (2) years after the date of this Agreement")),
        ],
        "time": [],
    },
]


# Fresh: labeled from the contract text before any run, and first scored after the last change to the framework and
# the app (2026-11-15). They have been rescored since, after later changes, and their misses were read to find bugs,
# so they are held out from tuning, not unseen. Scored by `AmendmentsFresh`.
FRESH: list[dict[str, Any]] = [
    {
        "name": "glu-fox",
        "documents": [
            {"key": "glu-base", "title": "GluMobileInc_20070319_S-1A_EX-10.09_436630_EX-10.09_Content License Agreement1",
             "signed_at": "2004-12-16T00:00:00Z", "name": "Wireless Content License Agreement between Fox and Glu Mobile"},
            {"key": "glu-a1", "title": "GluMobileInc_20070319_S-1A_EX-10.09_436630_EX-10.09_Content License Agreement2",
             "signed_at": "2005-11-11T00:00:00Z", "name": "Amendment No. 1 to the Fox and Glu Mobile License Agreement"},
            {"key": "glu-a2", "title": "GluMobileInc_20070319_S-1A_EX-10.09_436630_EX-10.09_Content License Agreement3",
             "signed_at": "2006-03-27T00:00:00Z", "name": "Amendment No. 2 to the Fox and Glu Mobile License Agreement"},
            {"key": "glu-a3", "title": "GluMobileInc_20070319_S-1A_EX-10.09_436630_EX-10.09_Content License Agreement4",
             "signed_at": "2007-02-19T00:00:00Z", "name": "Amendment No. 3 to the Fox and Glu Mobile License Agreement"},
        ],
        "supersedes": [
            ("glu-base", "continue in full force and effect for a period of eighteen (18) months after the initial "
                         "theatrical release",
             "glu-a3", "continue in full force and effect until March 31, 2008"),
        ],
        "unchanged": [],
        "as_of": [
            ("How long do the licenses for each Property last under the Fox and Glu Mobile license agreement?",
             "2006-06-01T00:00:00Z",
             ("glu-base", "continue in full force and effect for a period of eighteen (18) months after the initial "
                          "theatrical release"),
             ("glu-a3", "continue in full force and effect until March 31, 2008")),
            ("How long do the licenses for each Property last under the Fox and Glu Mobile license agreement?",
             "2007-06-01T00:00:00Z",
             ("glu-a3", "continue in full force and effect until March 31, 2008"),
             ("glu-base", "continue in full force and effect for a period of eighteen (18) months after the initial "
                          "theatrical release")),
            # Added 2026-11-16, labeled before any run.
            ("To whose attention must notices to Glu Mobile be sent under the Fox license agreement?",
             "2006-06-01T00:00:00Z",
             ("glu-base", "Attention: Paul Zuzelo"),
             ("glu-a3", "\"Paul Zuzelo\" is deleted and replaced with \"General Counsel\"")),
            ("To whose attention must notices to Glu Mobile be sent under the Fox license agreement?",
             "2007-06-01T00:00:00Z",
             ("glu-a3", "\"Paul Zuzelo\" is deleted and replaced with \"General Counsel\""),
             ("glu-base", "Attention: Paul Zuzelo")),
            ("Which company acts as \"Fox\" in the Glu Mobile wireless content license agreement?",
             "2005-06-01T00:00:00Z",
             ("glu-base", "TWENTIETH CENTURY FOX LICENSING & MERCHANDISING, a division of Fox Entertainment Group"),
             ("glu-a1", "Fox Mobile Entertainment, Inc. is hereby substituted for Twentieth Century Fox Licensing")),
            ("Which company acts as \"Fox\" in the Glu Mobile wireless content license agreement?",
             "2006-06-01T00:00:00Z",
             ("glu-a1", "Fox Mobile Entertainment, Inc. is hereby substituted for Twentieth Century Fox Licensing"),
             ("glu-base", "TWENTIETH CENTURY FOX LICENSING & MERCHANDISING, a division of Fox Entertainment Group")),
        ],
        "time": [("glu-a3", "continue in full force and effect until March 31, 2008", "valid_until", "2008")],
    },
    {
        "name": "scansource-cisco",
        "documents": [
            {"key": "scan-base",
             "title": "ScansourceInc_20190822_10-K_EX-10.38_11793958_EX-10.38_Distributor Agreement1",
             "signed_at": "2007-01-22T00:00:00Z",
             "name": "Nonexclusive Value Added Distributor Agreement between Cisco and ScanSource"},
            {"key": "scan-a3",
             "title": "ScansourceInc_20190822_10-K_EX-10.39_11793959_EX-10.39_Distributor Agreement",
             "signed_at": "2010-08-04T00:00:00Z",
             "name": "Amendment No. 3 to the Cisco and ScanSource Distributor Agreement"},
        ],
        "supersedes": [
            ("scan-base", "Distributor may submit the inventory balance claim between the first and",
             "scan-a3", "Distributor shall be entitled to return Product once per quarter"),
            ("scan-base", "continue thereafter for a period of two (2) years",
             "scan-a3", "The Term of the Agreement is hereby extended to January 20, 2012"),
        ],
        "unchanged": [
            ("scan-base", "Distributor's use of Software is governed by the terms contained in Exhibit C"),
        ],
        "as_of": [
            ("When does the Cisco and ScanSource distributor agreement end?", "2008-01-01T00:00:00Z",
             ("scan-base", "continue thereafter for a period of two (2) years"),
             ("scan-a3", "The Term of the Agreement is hereby extended to January 20, 2012")),
            ("When does the Cisco and ScanSource distributor agreement end?", "2011-01-01T00:00:00Z",
             ("scan-a3", "The Term of the Agreement is hereby extended to January 20, 2012"),
             ("scan-base", "continue thereafter for a period of two (2) years")),
            # Added 2026-11-16, labeled before any run.
            ("How often may ScanSource return inventory to Cisco for credit?", "2008-01-01T00:00:00Z",
             ("scan-base", "Distributor may submit the inventory balance claim between the first and"),
             ("scan-a3", "Distributor shall be entitled to return Product once per quarter")),
            ("How often may ScanSource return inventory to Cisco for credit?", "2011-01-01T00:00:00Z",
             ("scan-a3", "Distributor shall be entitled to return Product once per quarter"),
             ("scan-base", "Distributor may submit the inventory balance claim between the first and")),
            ("Until what date is ScanSource appointed as a Cisco distributor?", "2011-01-01T00:00:00Z",
             ("scan-a3", "The Term of the Agreement is hereby extended to January 20, 2012"),
             ("scan-base", "continue thereafter for a period of two (2) years")),
        ],
        "time": [("scan-a3", "The Term of the Agreement is hereby extended to January 20, 2012", "valid_until",
                  "2012")],
    },
    {
        "name": "pcquote-abw",
        "documents": [
            {"key": "pcq-base", "title": "PcquoteComInc_19990721_S-1A_EX-10.11_6377149_EX-10.11_Co-Branding Agreement1",
             "signed_at": "1996-10-11T00:00:00Z", "name": "Co-Branding Agreement between PC Quote and A.B. Watley"},
            {"key": "pcq-a1", "title": "PcquoteComInc_19990721_S-1A_EX-10.11_6377149_EX-10.11_Co-Branding Agreement2",
             "signed_at": "1996-12-09T00:00:00Z", "name": "Amendment to Section 2 of the PC Quote Co-Branding Agreement"},
            {"key": "pcq-a2", "title": "PcquoteComInc_19990721_S-1A_EX-10.11_6377149_EX-10.11_Co-Branding Agreement3",
             "signed_at": "1998-02-23T00:00:00Z",
             "name": "Second Amendment to the PC Quote and A.B. Watley Co-Branding Agreement"},
        ],
        "supersedes": [
            ("pcq-base", "Notice expressing a desire to terminate this Agreement will be sent by certified mail",
             "pcq-a2", "The text of Section 2. A. and B. of the Agreement is hereby deleted in its entirety"),
        ],
        "unchanged": [
            ("pcq-base", "enforced in all respects in accordance with the laws of the State of Illinois"),
        ],
        "as_of": [],
        "time": [],
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
        with urllib.request.urlopen(URL) as response:
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
    held_out = False
    fresh = False

    def documents(self, limit: int | None = None):
        from legal.documents import Contract

        full = load_full()
        self.texts: dict[str, str] = {}
        source = FRESH if self.fresh else HELD_OUT if self.held_out else CHAINS
        chains = source[:limit] if limit else source
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
        hits = loose = total = 0
        details = []
        for chain in self.chains:
            for old_key, old_snip, new_key, new_snip in chain["supersedes"]:
                total += 1
                old = self.quoting(app, self.locate(old_key, old_snip))
                new_ids = {f.id for f in self.quoting(app, self.locate(new_key, new_snip))}
                new_doc = self.locate(new_key, new_snip).doc_id
                replacers = [(f, r["fact_id"]) for f in old if f.status in ("superseded", "ended")
                             for r in app.store.relations(f.id)
                             if r["relation"] in ("supersedes", "ends") and r["other_id"] == f.id]
                ok = any(by in new_ids for _, by in replacers)
                any_fact = ok or any((app.load_fact(by) or f).document_id == new_doc for f, by in replacers)
                hits += ok
                loose += any_fact
                details.append({"supersedes": old_snip, "ok": ok, "any_fact": any_fact, "old_facts": len(old),
                                "new_facts": len(new_ids)})
        out["supersede_recall"] = round(hits / total, 3) if total else None
        out["supersede_recall_any"] = round(loose / total, 3) if total else None

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

        expected_old = set()
        for chain in self.chains:
            for old_key, old_snip, _, _ in chain["supersedes"]:
                expected_old |= {f.id for f in self.quoting(app, self.locate(old_key, old_snip))}
        for key, documents in (("false_change_rate", None), ("false_change_rate_base", 1)):
            doc_ids = {f"amend_{d['key'].replace('-', '_')}" for c in self.chains for d in c["documents"][:documents]}
            facts = [f for f in (f for doc_id in doc_ids for f in app.list_facts(document_id=doc_id))
                     if f.id not in expected_old]
            changed = [f for f in facts if f.status != "current"]
            out[key] = round(len(changed) / len(facts), 3) if facts else None
            if documents is None:
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
        out.update(qa_scores(self, app))  # the same questions answered from facts and from plain chunks

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


class AmendmentsHeldOut(Amendments):
    name = "amendments_heldout"
    description = "A contract chain never used while tuning: the NEON Systems distributor agreement."
    held_out = True


class AmendmentsFresh(Amendments):
    name = "amendments_fresh"
    description = "Three chains labeled before any run: Glu and Fox, ScanSource and Cisco, PC Quote."
    fresh = True



# SEC chains: base agreements and amendments from public EDGAR exhibits (the MIT-licensed SEC_Exhibit_10 dataset,
# 2005 to 2007), each amending a covenant "in its entirety". Labeled from the text before any run (2026-11-15) and kept
# out of every tuning step. The texts are in data/sec/ (not in git).
SEC: list[dict[str, Any]] = [
    {
        "name": "tyson",
        "documents": [
            {"key": "tyson-base", "file": "tyson-base.txt", "signed_at": "2005-09-28T00:00:00Z",
             "name": "Five-Year Credit Agreement of Tyson Foods"},
            {"key": "tyson-a2", "file": "tyson-a2.txt", "signed_at": "2006-04-28T00:00:00Z",
             "name": "Amendment No. 2 to the Tyson Foods Five-Year Credit Agreement"},
        ],
        "supersedes": [
            ("tyson-base", "The Borrower shall not permit the Leverage Ratio at any time to exceed 3.00:1.00",
             "tyson-a2", "at any time during any of the periods set forth below to exceed the ratio set forth opposite"),
            ("tyson-base", "for any period of four consecutive fiscal quarters to be less than 3.50:1.00",
             "tyson-a2", "for any period of four consecutive fiscal quarters to be less than 3.00:1.00"),
        ],
        "unchanged": [
            ("tyson-base", "GOVERNED BY, AND CONSTRUED IN ACCORDANCE WITH, THE LAWS OF THE STATE OF NEW YORK"),
        ],
        "as_of": [
            ("What is the maximum Leverage Ratio Tyson Foods may have under its Five-Year Credit Agreement?",
             "2006-01-15T00:00:00Z",
             ("tyson-base", "The Borrower shall not permit the Leverage Ratio at any time to exceed 3.00:1.00"),
             ("tyson-a2", "at any time during any of the periods set forth below to exceed the ratio set forth opposite")),
            ("What is the maximum Leverage Ratio Tyson Foods may have under its Five-Year Credit Agreement?",
             "2006-09-01T00:00:00Z",
             ("tyson-a2", "at any time during any of the periods set forth below to exceed the ratio set forth opposite"),
             ("tyson-base", "The Borrower shall not permit the Leverage Ratio at any time to exceed 3.00:1.00")),
            # Added 2026-11-16, labeled before any run.
            ("What is the minimum interest expense coverage ratio under Tyson Foods' Five-Year Credit Agreement?",
             "2006-01-15T00:00:00Z",
             ("tyson-base", "for any period of four consecutive fiscal quarters to be less than 3.50:1.00"),
             ("tyson-a2", "for any period of four consecutive fiscal quarters to be less than 3.00:1.00")),
            ("What is the minimum interest expense coverage ratio under Tyson Foods' Five-Year Credit Agreement?",
             "2006-09-01T00:00:00Z",
             ("tyson-a2", "for any period of four consecutive fiscal quarters to be less than 3.00:1.00"),
             ("tyson-base", "for any period of four consecutive fiscal quarters to be less than 3.50:1.00")),
            ("What leverage covenant does Tyson's credit facility set?", "2006-09-01T00:00:00Z",
             ("tyson-a2", "at any time during any of the periods set forth below to exceed the ratio set forth opposite"),
             ("tyson-base", "The Borrower shall not permit the Leverage Ratio at any time to exceed 3.00:1.00")),
        ],
        "time": [],
    },
    {
        "name": "furniture-brands",
        "documents": [
            {"key": "furniture-base", "file": "furniture-base.txt", "signed_at": "2006-05-17T00:00:00Z",
             "name": "Note Purchase Agreement of Furniture Brands International"},
            {"key": "furniture-a1", "file": "furniture-a1.txt", "signed_at": "2007-04-16T00:00:00Z",
             "name": "Amendment 1 to the Furniture Brands Note Purchase Agreement"},
        ],
        "supersedes": [
            ("furniture-base", "to be greater than 3.50 to 1.00 at any time",
             "furniture-a1", "to be greater than or equal to 3.25 to 1.00 at any time"),
        ],
        "unchanged": [
            ("furniture-base", "The Company will not permit Priority Debt to exceed 20% of Consolidated Net Worth"),
        ],
        "as_of": [
            ("What is the highest ratio of Consolidated Debt to Consolidated EBITDA that Furniture Brands' note purchase "
             "agreement allows?", "2006-10-01T00:00:00Z",
             ("furniture-base", "to be greater than 3.50 to 1.00 at any time"),
             ("furniture-a1", "to be greater than or equal to 3.25 to 1.00 at any time")),
            ("What is the highest ratio of Consolidated Debt to Consolidated EBITDA that Furniture Brands' note purchase "
             "agreement allows?", "2007-09-01T00:00:00Z",
             ("furniture-a1", "to be greater than or equal to 3.25 to 1.00 at any time"),
             ("furniture-base", "to be greater than 3.50 to 1.00 at any time")),
            # Added 2026-11-16, labeled before any run: a paraphrase.
            ("How much debt relative to EBITDA may Furniture Brands carry under its notes?", "2007-09-01T00:00:00Z",
             ("furniture-a1", "to be greater than or equal to 3.25 to 1.00 at any time"),
             ("furniture-base", "to be greater than 3.50 to 1.00 at any time")),
        ],
        "time": [("furniture-a1", "through and including June 29, 2007", "valid_until", "2007")],
    },
    {
        "name": "life-sciences-research",
        "documents": [
            {"key": "lsr-base", "file": "lsr-base.txt", "signed_at": "2006-03-01T00:00:00Z",
             "name": "Financing Agreement of Life Sciences Research"},
            {"key": "lsr-a1", "file": "lsr-a1.txt", "signed_at": "2007-08-01T00:00:00Z",
             "name": "First Amendment to the Life Sciences Research Financing Agreement"},
        ],
        "supersedes": [
            ("lsr-base", "on or prior to the first anniversary of the Effective Date. After the first anniversary",
             "lsr-a1", "on or prior to July 31, 2008"),
        ],
        "unchanged": [],
        "as_of": [
            ("Until when may the Borrowers not prepay the Term Loan under the Life Sciences Research Financing "
             "Agreement?", "2006-06-01T00:00:00Z",
             ("lsr-base", "on or prior to the first anniversary of the Effective Date. After the first anniversary"),
             ("lsr-a1", "on or prior to July 31, 2008")),
            ("Until when may the Borrowers not prepay the Term Loan under the Life Sciences Research Financing "
             "Agreement?", "2007-10-01T00:00:00Z",
             ("lsr-a1", "on or prior to July 31, 2008"),
             ("lsr-base", "on or prior to the first anniversary of the Effective Date. After the first anniversary")),
            # Added 2026-11-16, labeled before any run: a paraphrase.
            ("When does the no-prepayment period on the Life Sciences Research term loan end?", "2007-10-01T00:00:00Z",
             ("lsr-a1", "on or prior to July 31, 2008"),
             ("lsr-base", "on or prior to the first anniversary of the Effective Date. After the first anniversary")),
        ],
        "time": [],
    },
]


# Term extensions: one SEC chain where each amendment pushes a date further out (Navistar's certificate purchase
# agreement, 2003 to 2007, from the same SEC_Exhibit_10 dataset). A dev set for tuning how a later extension
# supersedes the earlier date, built 2026-11-16 so the held-out chains stay untouched. Texts in data/sec/.
EXTENSIONS: list[dict[str, Any]] = [
    {
        "name": "navistar",
        "documents": [
            {"key": "navistar-a1", "file": "navistar-a1.txt", "signed_at": "2003-01-22T00:00:00Z",
             "name": "First Amendment to the Navistar Certificate Purchase Agreement"},
            {"key": "navistar-x1", "file": "navistar-x1.txt", "signed_at": "2004-02-20T00:00:00Z",
             "name": "Extension to the Navistar Certificate Purchase Agreement"},
            {"key": "navistar-x2", "file": "navistar-x2.txt", "signed_at": "2005-12-19T00:00:00Z",
             "name": "Extension to the Navistar Amended and Restated Certificate Purchase Agreement"},
            {"key": "navistar-x3", "file": "navistar-x3.txt", "signed_at": "2006-03-24T00:00:00Z",
             "name": "March 2006 Amendment, Waiver and Extension to the Navistar Amended and Restated Certificate "
                     "Purchase Agreement"},
            {"key": "navistar-x4", "file": "navistar-x4.txt", "signed_at": "2006-05-26T00:00:00Z",
             "name": "May 2006 Amendment, Waiver and Extension to the Navistar Amended and Restated Certificate "
                     "Purchase Agreement"},
            {"key": "navistar-x5", "file": "navistar-x5.txt", "signed_at": "2007-01-31T00:00:00Z",
             "name": "January 2007 Amendment, Waiver and Extension to the Navistar Amended and Restated Certificate "
                     "Purchase Agreement"},
        ],
        "supersedes": [
            ("navistar-a1", "extension of the Purchase Expiration Date out to January 21, 2004",
             "navistar-x1", "The Purchase Expiration Date is extended to February 17, 2005"),
            ("navistar-x2", "The Purchase Expiration Date is extended to March 26, 2006",
             "navistar-x3", "The Purchase Expiration Date is extended to May 26, 2006"),
            ("navistar-x3", "The Purchase Expiration Date is extended to May 26, 2006",
             "navistar-x4", "The Purchase Expiration Date is extended to May 24, 2007"),
            ("navistar-x4", "The Purchase Expiration Date is extended to May 24, 2007",
             "navistar-x5", "The Purchase Expiration Date is extended to January 30, 2008"),
        ],
        "unchanged": [],
        "as_of": [
            ("What is the Purchase Expiration Date under Navistar's certificate purchase agreement?",
             "2006-04-15T00:00:00Z",
             ("navistar-x3", "The Purchase Expiration Date is extended to May 26, 2006"),
             ("navistar-x2", "The Purchase Expiration Date is extended to March 26, 2006")),
            ("What is the Purchase Expiration Date under Navistar's certificate purchase agreement?",
             "2007-06-01T00:00:00Z",
             ("navistar-x5", "The Purchase Expiration Date is extended to January 30, 2008"),
             ("navistar-x4", "The Purchase Expiration Date is extended to May 24, 2007")),
            # Added 2026-11-16, labeled before any run.
            ("What is the Purchase Expiration Date under Navistar's certificate purchase agreement?",
             "2004-06-01T00:00:00Z",
             ("navistar-x1", "The Purchase Expiration Date is extended to February 17, 2005"),
             ("navistar-a1", "extension of the Purchase Expiration Date out to January 21, 2004")),
            ("When does Navistar's certificate purchase facility stop taking purchases?", "2006-08-01T00:00:00Z",
             ("navistar-x4", "The Purchase Expiration Date is extended to May 24, 2007"),
             ("navistar-x3", "The Purchase Expiration Date is extended to May 26, 2006")),
        ],
        "time": [],
    },
]

class AmendmentsSec(Amendments):
    name = "amendments_sec"
    description = "Three SEC credit-agreement chains with covenants amended in their entirety, labeled before any run."

    def documents(self, limit: int | None = None):
        from legal.documents import Contract

        folder = DATA.parent / "sec"
        self.texts = {}
        self.chains = SEC[:limit] if limit else SEC
        for chain in self.chains:
            for spec in chain["documents"]:
                text = (folder / spec["file"]).read_text()
                self.texts[spec["key"]] = text
                yield Contract(text, id=f"amend_{spec['key'].replace('-', '_')}", uri=f"sec:{spec['file']}",
                               title=spec["name"], metadata={"signed_at": spec["signed_at"]})


class WindowsDev(Suite):
    """Development set for dated windows: 20 contracts from 2010 SEC filings with a term that runs "through and
    including <date>". A fact quoting that clause should end in the right year. Used to tune date capture; never
    the SEC amendment chains."""

    name = "windows_dev"
    description = "20 contracts with a dated window, for tuning end-date capture."
    parallel = 4

    def documents(self, limit: int | None = None):
        from legal.documents import Contract

        folder = DATA.parent / "windows"
        self.gold = json.loads((folder / "gold.json").read_text())[:limit]
        self.texts = {}
        for row in self.gold:
            text = (folder / row["file"]).read_text()
            key = row["file"].removesuffix(".txt")
            self.texts[key] = text
            yield Contract(text, id=f"win_{key}", uri=f"sec:{row['source']}", title=row["source"])

    def score(self, app, results) -> dict[str, Any]:
        hit, missing, details = 0, 0, []
        for row in self.gold:
            key = row["file"].removesuffix(".txt")
            try:
                located = self.locate_in(key, row["snippet"])
            except ValueError:
                continue
            facts = [f for f in app.list_facts(document_id=f"win_{key}")
                     if any(q.start < located[1] and located[0] < q.end for q in f.quotes)]
            if not facts:
                missing += 1
            ok = any(f.valid_until is not None and str(f.valid_until.year) == row["year"] for f in facts)
            hit += ok
            details.append({"file": row["file"], "ok": ok, "facts": len(facts),
                            "values": [str(f.valid_until) for f in facts][:4]})
        return {"captured": round(hit / len(details), 3) if details else None, "no_fact": missing,
                "windows": len(details), "details": details}

    def locate_in(self, key: str, snippet: str) -> tuple[int, int]:
        match = _pattern(snippet).search(self.texts[key])
        if match is None:
            raise ValueError(snippet)
        return match.start(), match.end()


class ExtensionsDev(AmendmentsSec):
    name = "extensions_dev"
    description = "A dev chain of term extensions, for tuning supersession of an extended date."

    def documents(self, limit: int | None = None):
        from legal.documents import Contract

        folder = DATA.parent / "sec"
        self.texts = {}
        self.chains = EXTENSIONS
        for chain in self.chains:
            for spec in chain["documents"]:
                text = (folder / spec["file"]).read_text()
                self.texts[spec["key"]] = text
                yield Contract(text, id=f"amend_{spec['key'].replace('-', '_')}", uri=f"sec:{spec['file']}",
                               title=spec["name"], metadata={"signed_at": spec["signed_at"]})
