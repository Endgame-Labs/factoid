# Demo: a sales call and two emails

A small Factoid project you can run in a minute, for about a cent. A vendor, Northstar Data, has a call with a
customer, Kestrel Health, and then the two trade emails. Factoid turns each one into short facts that cite their
words, and changes the facts it holds when a later document changes them. The companies and people are made up.

| File | What it is |
| --- | --- |
| `docs/2026-10-14-kestrel-call.txt` | The call: pain points, a cutover date that moves, seat counts, pricing, and security needs |
| `docs/2026-10-15-seat-count.txt` | Elena's email: 30 seats, not 45 |
| `docs/2026-10-16-pricing.txt` | Maya's email: the price for 30 seats, and the SOC 2 report sent |
| `app/` | The classes: `CallTranscript` and `Email`, `CustomerFact` and `VendorFact`, five traits, and three entity kinds |
| `evals/demo.py` | Checks each fact's status after all three documents |

## Run it

From this folder, with keys for TypeSafe and Fireworks (`uv run factoid keys set`):

```sh
uv sync
uv run factoid ingest docs/2026-10-14-kestrel-call.txt   # the call first
uv run factoid ingest docs/2026-10-15-seat-count.txt     # then the emails, in order
uv run factoid ingest docs/2026-10-16-pricing.txt
uv run factoid facts list                                # current facts, with their traits
uv run factoid facts list --status superseded            # what changed
uv run factoid search "how many seats"
uv run factoid read <fact id>                            # one fact, its quotes, and its history
uv run factoid eval demo                                 # the checks
```

## What to look for

- **Speakers and quotes.** Each fact says who said it ("Samir Patel said that Kestrel Health requires ...") and
  cites the words it came from. `factoid read` shows them.
- **A change within the call.** Elena first targets December 1, 2026, then moves the cutover to January 18, 2027.
  The December fact is superseded, and stays in the store with the date it stopped holding.
- **Traits.** Facts carry `pain_point`, `timeline`, `pricing`, `security_requirement`, or `commitment`, so
  `factoid facts list --trait pricing` gives the pricing facts.
- **What it costs.** The model calls line after each ingest gives the cost at list prices. All three documents cost
  under a cent.

## A change in a later email

Elena's email says the rollout starts with 30 seats, "not the 45 I mentioned on the call". Its fact repeats Samir's
remark that finance approved 30, and it also retires the 45-seat plan, which is superseded as of October 15.
`factoid eval demo` passes all 5 of its checks. Before 0.1.27, a repeat dropped the change it carried (issue #25).
