"""Basketball traits and fact classes.

`Reported` is what happened, from box scores, recaps, and articles. `Remark` is what a player or coach says they think,
feel, or plan, in their own words. They are different kinds of evidence: a remark cannot contradict a box score.
"""

from factoid import Fact, FactTrait


class Injury(FactTrait):
    """A player's injury, illness, or recovery, or whether a player is available to play."""


class Milestone(FactTrait):
    """A record, a first, a title, an award such as Finals MVP, or a career mark."""


class Shooting(FactTrait):
    """How a player or team shot: points, field goals, three-pointers, or free throws, made or missed."""


class Defense(FactTrait):
    """Defense: stops, steals, blocks, rebounds on defense, or a defensive scheme or matchup."""


class Result(FactTrait):
    """The outcome of a game or a series: who won, the score, or the series standing."""


class Reported(Fact):
    """What happened, as box scores, game recaps, and articles report it."""

    traits = [Injury, Milestone, Shooting, Defense, Result]


class Remark(Fact):
    """What a player or coach says they think, feel, expect, or plan, in their own words."""

    traits = [Injury, Milestone]
