# Entities: beyond the v1 class

**Status: Roadmap** (Kyle, 2026-11-14). Not in v1.

The v1 entity class is deliberately small: a docstring, optional `unique_keys`, typed properties with `where()`, and
per-class tuning of the AI steps (`SPEC.md`, section 7). Factoid's job is wrapping AI work, and it should not grow into
a general data-modeling layer. These ideas may earn a place later.

## Domain methods built on reads

Plain Python methods and computed properties on an entity class that use Factoid's reads, so an app or agent can ask a
domain question without knowing about facts and labels:

```python
class ChurnRisk(FactLabel):
    """The customer said or did something suggesting they may leave or not renew."""

class Customer(Entity):
    """A company that buys from us or might."""

    @property
    def at_risk(self):
        """True if any fact from the last 30 days is labeled ChurnRisk."""
        return self.facts(labels=[ChurnRisk], since="30d").exists()
```

Python allows this already. The roadmap item is documenting it as a pattern and making sure the reads are cheap enough
for it (for example, `exists()` without loading facts).

## Lifecycle callbacks

`on_linked`, `on_merged`, and `on_split` on an entity class, to react to events, such as syncing a merge back to a CRM.

## `normalize`

A method that reduces variant mentions to one form before linking ("Northwind, Inc." to "Northwind"). Evals should show
whether the default linking ladder needs it.
