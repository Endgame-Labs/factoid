from factoid import Entity


class Player(Entity):
    """A basketball player, on the Warriors or an opponent."""

    unique_keys = ["espn_id"]


class Team(Entity):
    """An NBA team, such as the Golden State Warriors or the Boston Celtics."""

    unique_keys = ["team_name"]


class Game(Entity):
    """One playoff game, such as Game 6 of the 2022 NBA Finals."""

    unique_keys = ["espn_game_id"]


class Series(Entity):
    """A playoff series between two teams, such as the 2022 NBA Finals or the 2022 Western Conference Finals."""

    unique_keys = ["series_name"]


class Person(Entity):
    """A named person who is not a player: a coach, an executive, a reporter, or a family member."""
