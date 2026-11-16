from factoid import Identity, Ignore, ProseDocument, StructuredDocument

from .entities import Game, Player, Series, Team
from .facts import Remark, Reported


class Interview(ProseDocument):
    """A press conference transcript: reporters' questions and a player's or coach's answers."""

    fact_classes = [Remark, Reported]
    # ASAP Sports marks turns with "Q." and "STEPHEN CURRY:".
    speaker_pattern = r"(?:(?P<speaker>Q)\.|(?P<speaker_name>[A-Z][A-Z .'\-]+):)\s"
    guidance = (
        "This is a press conference. Questions (speaker Q) give context only: take facts from the answers, and name "
        "who said each one (\"Stephen Curry said ...\"). Keep opinions, feelings, and plans as what the speaker said, "
        "not as facts about the world. Name the game and the series when the speaker refers to them."
    )

    @property
    def source_datetime(self):
        return self.metadata.get("said_at")

    def context(self):
        return {k: self.metadata[k] for k in ("speakers", "team", "occasion", "series") if self.metadata.get(k)}


class Recap(ProseDocument):
    """A game story written after a game, such as an AP recap."""

    fact_classes = [Reported]
    guidance = "Name the game (\"Game 6 of the 2022 NBA Finals\"), the teams, and the players in each fact."

    @property
    def source_datetime(self):
        return self.metadata.get("published")

    def context(self):
        return {k: self.metadata[k] for k in ("game", "source") if self.metadata.get(k)}


class Article(ProseDocument):
    """An encyclopedia article about a season, a playoff run, or a series."""

    fact_classes = [Reported]
    guidance = "Name the season, the series, and the game a fact is about, since the article covers many."

    @property
    def source_datetime(self):
        return self.metadata.get("published")


class GameLog(StructuredDocument):
    """The Warriors' playoff games, one game per row, with the score and the series standing after it."""

    fact_classes = [Reported]
    key = "game_id"
    when = "date"
    row_entity = Game
    resolve_cells = True  # the series standing after each game supersedes the one before
    columns = {
        "game_id": Identity(Game, "espn_game_id", name="{game}"),
        "game": Ignore(),
        "series": Identity(Series, "series_name"),
        "opponent": Identity(Team, "team_name"),
        "home": Ignore(),
        "result": "The Golden State Warriors {result} the {opponent} {warriors_score}-{opponent_score} in {game}.",
        "warriors_score": Ignore(),
        "opponent_score": Ignore(),
        # A state, not an event: no "after Game 3", so the next standing replaces it. The row date says when.
        "series_status": "In the {series}, {series_status}.",
    }


class BoxScore(StructuredDocument):
    """Player box scores from the Warriors' playoff games, one player in one game per row."""

    fact_classes = [Reported]
    key = "row_id"
    when = "date"
    columns = {
        "game_id": Identity(Game, "espn_game_id", name="{game}"),
        "player_id": Identity(Player, "espn_id", name="{player}"),
        "team": Identity(Team, "team_name"),
        "game": Ignore(),
        "player": Ignore(),
        "minutes": Ignore(),
        "rebounds": Ignore(),
        "assists": Ignore(),
        "points": "{player} of the {team} had {points} points, {rebounds} rebounds, and {assists} assists in "
                  "{minutes} minutes in {game}.",
        "threes": "{player} shot {threes} from three-point range in {game}.",
        "starter": Ignore(),
        "steals": Ignore(),
        "blocks": Ignore(),
        "turnovers": Ignore(),
        "field_goals": Ignore(),
        "free_throws": Ignore(),
        "plus_minus": Ignore(),
    }


class PlayerTotals(StructuredDocument):
    """Warriors players' averages over the 2022 playoffs, computed from the box scores."""

    fact_classes = [Reported]
    key = "player_id"
    when = "as_of"
    row_entity = Player
    columns = {
        "player_id": Identity(Player, "espn_id", name="{player}"),
        "player": Ignore(),
        "games": Ignore(),
        "minutes_per_game": Ignore(),
        "rebounds_per_game": Ignore(),
        "assists_per_game": Ignore(),
        "points_per_game": "{player} averaged {points_per_game} points, {rebounds_per_game} rebounds, and "
                           "{assists_per_game} assists in {games} games of the Golden State Warriors' 2022 playoffs.",
        "threes_made": "{player} made {threes_made} three-pointers in the Golden State Warriors' 2022 playoffs.",
    }
