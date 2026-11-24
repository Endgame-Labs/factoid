"""What each release adds, deprecates, and removes, as facts a docs assistant can answer from."""

from factoid import Fact, FactTrait


class Added(FactTrait):
    """Something new in the standard library: a module, class, function, or parameter."""


class Deprecated(FactTrait):
    """Something that still works but is deprecated, often with the version that will remove it."""


class Removed(FactTrait):
    """Something taken out of the standard library, so code that uses it fails."""


class Replacement(FactTrait):
    """What to use instead of something deprecated or removed."""


class ChangeFact(Fact):
    """A change to Python's standard library in one release: what was added, deprecated, or removed, and what to use
    instead."""

    traits = [Added, Deprecated, Removed, Replacement]
    guidance = (
        "Each fact names the Python version it is about and the full dotted name of what changed, such as \"In "
        "Python 3.12, the distutils package is removed.\" Keep the version a removal is planned for (\"will be "
        "removed in Python 3.14\") and the version something was first deprecated in, when the text gives them. "
        "Leave out who contributed a change and its issue number."
    )
