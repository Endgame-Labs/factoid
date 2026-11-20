"""The README's deal, end to end: a contract, an amendment, and an email from our lawyers.

The documents in `sample_docs/` are made up: Acme is buying Orion, and Acme's lawyers review Orion's supply agreement
with Vega. The suite checks what CUAD cannot: fact classes, traits on counsel's views, a supersede with a future
effective date, as-of search, and entities that connect the three documents.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from factoid.evals import Suite

DOCS = Path(__file__).resolve().parent.parent / "sample_docs"
ORDER = [("supply_agreement.txt", "Contract"), ("amendment_2.txt", "Contract"), ("counsel_email.txt", "CounselEmail"),
         ("contract_register.csv", "ContractRegister")]


class Diligence(Suite):
    name = "diligence"
    description = "The README's Orion and Vega deal: classes, traits, supersede, as-of search, and entities."

    def documents(self, limit: int | None = None):
        from app import documents

        for name, class_name in ORDER[:limit]:
            sidecar = DOCS / f"{name}.meta.json"
            meta = json.loads(sidecar.read_text()) if sidecar.exists() else {"title": "Data room contract register"}
            klass = getattr(documents, class_name)
            yield klass((DOCS / name).read_text(), metadata=meta, uri=f"sample_docs/{name}", title=meta["title"])

    def score(self, app, results) -> dict[str, Any]:
        from app.entities import Agreement, Company
        from app.facts import (
            AssignmentRestriction,
            ChangeOfControl,
            ClosingRisk,
            CounselFact,
            LiabilityCap,
            SourceFact,
        )

        by_doc = {Path(r.document.uri).name: r.facts for r in results}
        contract = by_doc.get("supply_agreement.txt", [])
        amendment = by_doc.get("amendment_2.txt", [])
        email = by_doc.get("counsel_email.txt", [])
        register = by_doc.get("contract_register.csv", [])
        checks: dict[str, bool] = {}

        def has(facts, trait, cls=None, text=None):
            return any(f.has(trait) and (cls is None or isinstance(f, cls)) and (text is None or text in f.text)
                       for f in facts)

        checks["contract: change of control"] = has(contract, ChangeOfControl)
        checks["contract: assignment restriction"] = has(contract, AssignmentRestriction)
        checks["contract: liability cap"] = has(contract, LiabilityCap, text="1,000,000") or \
            has(contract, LiabilityCap, text="$1M") or has(contract, LiabilityCap, text="$1 million")
        checks["contract: every fact is a SourceFact"] = bool(contract) and all(isinstance(f, SourceFact)
                                                                               for f in contract)
        new_cap = [f for f in amendment if f.has(LiabilityCap)]
        checks["amendment: cap fact valid from 2027-01-01"] = any(
            f.valid_from is not None and f.valid_from.date().isoformat() == "2027-01-01" for f in new_cap)
        old_caps = [app.load_fact(f.id) for f in contract if f.has(LiabilityCap)]
        checks["amendment: old cap superseded"] = any(f.status == "superseded" for f in old_caps)
        others = [app.load_fact(f.id) for f in contract if not f.has(LiabilityCap)]
        checks["amendment: no other contract fact changed"] = bool(others) and all(f.status == "current" for f in others)
        checks["email: a CounselFact with ClosingRisk"] = has(email, ClosingRisk, cls=CounselFact)
        # The email states the 15-day period only inside counsel's recommendation, so any fact class will do.
        checks["email: the recommendation keeps Vega's 15-day answer period"] = any("15" in f.text for f in email)

        before = app.search_facts("Vega liability cap", as_of="2026-06-01T00:00:00Z", top_k=3)
        after = app.search_facts("Vega liability cap", as_of="2027-02-01T00:00:00Z", top_k=3)
        checks["search: cap as of 2026-06-01 is $1M"] = (bool(before) and "1,000,000" in before[0].fact.text) \
            or (bool(before) and "$1M" in before[0].fact.text)
        checks["search: cap as of 2027-02-01 is $2M"] = bool(after) and ("2,000,000" in after[0].fact.text
                                                                         or "$2M" in after[0].fact.text)
        vega = Company.find("Vega Components Corp.") or Company.find("Vega")
        docs_linked = set()
        if vega is not None:
            docs_linked = {f.document_id for f in vega.facts(include_retired=True)}
        checks["entities: Vega links all four documents"] = len(docs_linked) == 4
        value = [f for f in register if "ORI-014" in f.text and "1800000" in f.text]
        checks["register: a fact per value, linked to the contract's Vega"] = bool(value) and vega is not None and any(
            m.entity_id == vega.id for m in value[0].mentions)
        supply = Agreement.find("ORI-014")
        checks["register: governing law set on the agreement"] = supply is not None and \
            supply.governing_law == "Delaware"
        checks["register: the notes cell becomes a fact"] = any("reprice" in f.text.lower() for f in register)
        passed = sum(checks.values())
        return {"passed": f"{passed}/{len(checks)}", "score": round(passed / len(checks), 3),
                "checks": {k: "ok" if v else "FAIL" for k, v in checks.items()}}
