# Output: Facts and events

## A fact

```json
{
  "id": "f_8k2m1",
  "text": "Dana Ruiz said Acme will renew at $115K if legal signs off by November 7, 2026.",
  "subject": "Acme",
  "slot": {"entity": "Acme", "field": "renewal_price", "value": 115000, "unit": "USD"},
  "quotes": [
    {
      "doc": "email:CAF8x2@mail.gmail.com",
      "revision": "r2",
      "passage": 3,
      "text": "We'll renew at $115K if legal signs off by Friday.",
      "speaker": {"name": "Dana Ruiz", "side": "theirs"},
      "at": "2026-11-03T16:42:00-08:00",
      "offset": [212, 262]
    }
  ],
  "said_at": "2026-11-03T16:42:00-08:00",
  "learned_at": "2026-11-03T17:01:12Z",
  "status": "current",
  "related": {"corroborated_by": ["f_77qa0"], "supersedes": ["f_a1"], "disputes": []},
  "tags": {"commercial": 0.94},
  "made_by": {"pipeline": "p_3fa9", "extract": "glm-5p3-flash", "judges": {"jev-floors": {"grounded": 0.91, "atomic": 0.88}}}
}
```

| Field | Meaning |
| --- | --- |
| `id` | Content-addressed: the same claim from the same evidence always gets the same id, so re-running is idempotent. Re-judging does not change it. |
| `text` | One complete sentence that stands on its own: names in full, dates absolute, no "he" or "that call". |
| `subject` | Who or what the fact is about, as named. Linking subjects to your own entities is a plugin, not core. |
| `slot` | Optional. A typed field value, when the fact *is* one (a price, a date, a title, a stage). Slots let `resolve` supersede by rule. |
| `quotes` | One to three. Each is an exact substring of its document's revision, with offsets. Never written by a model. |
| `said_at` | When the source said it. `learned_at`: when Factorial accepted it. They differ, and both matter. |
| `status` | `current`, `superseded`, `disputed`, or `retracted`. |
| `related` | Links to other facts made by `resolve`. Duplicates are not stored twice; they become corroboration. |
| `tags` | Optional classes with probabilities, from a `tag` strategy. |
| `made_by` | The pipeline fingerprint, the models, and the judges' scores. Provenance for every number. |

### Statuses

```
            supersede              retract
 current ───────────► superseded ◄──────── (restore reverses either)
    │
    │ contradict
    ▼
 disputed  ──► (a person or a judge settles it: one supersedes, or one is retracted)
```

`search` and `read` return `current` and `disputed` facts by default. A disputed fact always comes back with the fact it
disputes, so a reader sees both sides. Ask for others with `--status` or `?status=`.

### What is not a fact

Questions, hypotheticals, a speaker's guess presented as a decision, call metadata (title, time, attendees), raw ids, and
relative dates with no anchor ("next Friday" with no source date). A fact with a relative date gets an absolute one from
its document's `at`, or it is rejected. These rules live in the extract prompt and the judges, and the eval suites test
them.

## Events

The log is the record of truth. Each line is an event:

```json
{"seq": 188, "at": "2026-11-03T17:01:13Z", "type": "fact.superseded",
 "id": "f_a1", "by": "f_b2",
 "actor": {"kind": "rule", "name": "slot", "version": "1"},
 "reason": "same entity and field, stated later",
 "evidence": {"old_said_at": "2026-10-12", "new_said_at": "2026-11-03"}}
```

| Type | Fields | Written by |
| --- | --- | --- |
| `doc.ingested` | `doc`, `revision`, `type`, `classified_by` | ingest |
| `doc.deleted` | `doc` | a source or a person |
| `fact.added` | `fact` | the pipeline, or a person (`tell`) |
| `fact.corroborated` | `id`, `by` | `resolve` |
| `fact.superseded` | `id`, `by` | `resolve`, or a person |
| `fact.contradicted` | `a`, `b`, `score` | `resolve` |
| `fact.retracted` | `id`, `reason` | a document change, or a person |
| `fact.restored` | `id`, `undoes` (a `seq`) | anyone; reverses an earlier event |
| `candidate.rejected` | `candidate`, `stage`, `reasons` | `gate` and `judge`. Kept for evals and calibration, never served. |

`actor.kind` is one of `code`, `rule`, `model`, `judge`, or `person`. Every automatic event can be reversed by a
`fact.restored`, so nothing the machine does is final.

Rejected candidates are logged because they are what you label to calibrate a judge, and what a new judge is replayed
against.
