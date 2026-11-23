"""The demo's checks: what each fact's status should be after the call and the two emails.

`factoid eval demo` runs them. The 45-seat check fails today (issue #25): the email that moves the rollout to 30 seats
is resolved as a duplicate of Samir's remark, which drops its change to the 45-seat plan.
"""

import json
from pathlib import Path

from factoid import Raw
from factoid.evals import Suite

DOCS = Path(__file__).parent.parent / "docs"


class Demo(Suite):
    name = "demo"

    def documents(self, limit=None):
        # In date order, one at a time, so each email is resolved against what the call left.
        for path in sorted(DOCS.glob("*.txt"))[:limit]:
            meta = json.loads(path.with_name(path.name + ".meta.json").read_text())
            yield Raw(path.read_text(), meta, uri=f"docs/{path.name}", title=meta["title"])

    def score(self, app, results):
        rows = app.store.query("select text, status from facts")

        def status(*words):
            found = [r["status"] for r in rows if all(w in r["text"] for w in words)]
            return found[0] if found else None

        checks = {
            "december_1_superseded": status("December 1, 2026") == "superseded",
            "january_18_current": status("January 18, 2027") == "current",
            "plan_for_45_seats_retired": status("45 analyst seats", "planned") not in (None, "current"),
            "price_for_30_seats_current": status("$72,000") == "current",
            "soc_2_required": status("SOC 2 Type II", "requires") == "current",
        }
        return {"checks": {k: int(v) for k, v in checks.items()}, "passed": sum(checks.values()) / len(checks)}
