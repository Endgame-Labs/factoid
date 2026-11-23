"""Variants for `factoid eval --vary`."""


# Issue #24: a rule that keeps a reference the text leaves open, in the repair prompt's references block. Run with
# --vary repair_prompt=@evals.variants:DEFAULT_REPAIR,@evals.variants:KEEP_OPEN to score both on the same code.
DEFAULT_REPAIR = '{% extends "factoid/repair.md.j2" %}'
KEEP_OPEN = (
    '{% extends "factoid/repair.md.j2" %}{% block references %}{{ super() }}Keep a reference the text leaves open as '
    'worded, such as "its" when the text does not say which thing it means. Never guess what it refers to.\n'
    '{% endblock %}'
)
