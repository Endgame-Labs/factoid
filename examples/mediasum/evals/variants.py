"""Fact eval variants for `--vary fact_evals=@evals.variants:NAME`: wordings of the self-contained question."""

from factoid import DecisionFloors, Nli, Noul

OLD = Noul(
    "Can a reader understand the fact on its own? It must name its subject and the people, companies, and "
    "documents it refers to, with no unresolved pronouns and no references like 'this Agreement' or 'the Party'. "
    "Text the source itself omits or redacts, such as [***], does not count against the fact.",
    true="The fact is understandable alone.",
    false="The fact needs context it does not give.",
)
MID = Noul(
    "Can a reader who has not seen the source understand the fact on its own? It must name its subject and the "
    "people, organizations, and documents it refers to. It fails if it has a pronoun that does not refer to something "
    "named in the fact, a reference like 'this Agreement' or 'the Party', or a time relative to an unstated date "
    "('yesterday', 'last week'). A description that the rest of the sentence makes clear is fine. Text the source "
    "itself omits or redacts, such as [***], does not count against the fact.",
    true="The fact is understandable alone.",
    false="The fact needs context it does not give.",
)

OLD_40 = [Nli(), DecisionFloors(questions={"self_contained": OLD}, self_contained=0.4)]
MID_40 = [Nli(), DecisionFloors(questions={"self_contained": MID}, self_contained=0.4)]
MID_50 = [Nli(), DecisionFloors(questions={"self_contained": MID}, self_contained=0.5)]
STRICT_40 = [Nli(), DecisionFloors(self_contained=0.4)]

STRICT = Noul(
    "Can a reader who has not seen the source understand the fact on its own? The fact must name or describe, well "
    "enough to identify, every person, organization, place, document, and event it refers to. It fails if it has a "
    "pronoun or a description ('he', 'the company', 'the president', 'this Agreement', 'the case') whose referent the "
    "fact itself does not give, or a time relative to an unstated date ('yesterday', 'last week'). Text the source "
    "itself omits or redacts, such as [***], does not count against the fact.",
    true="Every reference is resolved.",
    false="Some reference is left unresolved.",
)
# The mid question rejects; the strict one only asks for a repair, and the fact keeps its wording if the repair misses.
MID_40_EXPLICIT_50 = [Nli(), DecisionFloors(questions={"self_contained": MID, "explicit": STRICT}, self_contained=0.4,
                                       explicit=0.0, targets={"explicit": 0.5})]
STRICT_10_T50 = [Nli(), DecisionFloors(self_contained=0.1, targets={"self_contained": 0.5})]

from app.settings import Project  # noqa: E402

from factoid import Model  # noqa: E402

REPAIR_MEDIUM = {**Project.models, "repair": Model("fireworks/glm-5p3-flash", reasoning_effort="medium")}


# Decision models for `--vary models=@evals.variants:RUNE`: the project's models with Rune for `choose`.
from app.settings import Project  # noqa: E402

from factoid import Model  # noqa: E402

RUNE = {**Project.models, "choose": Model("fireworks/rune")}


# Decision 87's experiment (issue #6): a fact that fails "grounded" is trimmed to what its passages say, not dropped.
GROUNDED_REPAIR = [Nli(), DecisionFloors(repair_grounded=True)]


# Issue #24: a rule that keeps a reference the text leaves open, in the repair prompt's references block. Run with
# --vary repair_prompt=@evals.variants:DEFAULT_REPAIR,@evals.variants:KEEP_OPEN to score both on the same code.
DEFAULT_REPAIR = '{% extends "factoid/repair.md.j2" %}'
KEEP_OPEN = (
    '{% extends "factoid/repair.md.j2" %}{% block references %}{{ super() }}Keep a reference the text leaves open as '
    'worded, such as "its" when the text does not say which thing it means. Never guess what it refers to.\n'
    '{% endblock %}'
)


# Decision models side by side (decision 135's follow-up): Jev 1.13 (the default), Jev 1.14, and Rune, which makes the
# project Fireworks only. Run with --vary models=@evals.variants:JEV_113,@evals.variants:JEV_114,@evals.variants:RUNE.
from app.settings import Project as _Project  # noqa: E402

from factoid import Model as _Model  # noqa: E402

JEV_113 = {**_Project.models, "choose": _Model("typesafe/jev-1.13.0")}
JEV_114 = {**_Project.models, "choose": _Model("typesafe/jev-1.14.0")}
