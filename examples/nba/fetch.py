"""Download the Warriors' 2022 playoff run into data/: box scores, game recaps, interviews, and articles.

    uv run python fetch.py                 # Finals game-day interviews (the default)
    uv run python fetch.py --rounds all    # game-day interviews from all four series
    uv run python fetch.py --practice      # also practice and media days

Sources (none of it is committed; see the README):
- ESPN's public site API: the schedule, each game's box score, and the AP recap ESPN carries for the game.
- ASAP Sports: press conference transcripts. Only the Warriors' own (players and coaches).
- Wikipedia: articles on the 2022 Finals, the 2022 playoffs, and the Warriors' 2021-22 season (CC BY-SA 4.0).

Raw responses are cached in data/raw/, so a second run makes no requests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
RAW = DATA / "raw"
AGENT = "factoid-example/0.1 (research; one request per second)"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ROUNDS = {"West 1st Round": "Western Conference First Round", "West Semifinals": "Western Conference Semifinals",
          "West Finals": "Western Conference Finals", "NBA Finals": "NBA Finals"}
SERIES = {"first": "2022 Western Conference First Round", "semis": "2022 Western Conference Semifinals",
          "west": "2022 Western Conference Finals", "finals": "2022 NBA Finals"}
ASAP_EVENTS = {  # event pages for the Warriors' four series, from asapsports.com's 2022 basketball archive
    "first": "event_id=175728&category=11&year=2022&title=NBA+WESTERN+CONFERENCE+FIRST+ROUND%3A+NUGGETS+VS+WARRIORS",
    "semis": "event_id=176024&category=11&year=2022&title=NBA+WESTERN+CONFERENCE+SEMIFINALS%3A+WARRIORS+VS+GRIZZLIES",
    "west": "event_id=176543&category=11&year=2022&title=NBA+WESTERN+CONFERENCE+FINALS%3A+MAVERICKS+VS.+WARRIORS",
    "finals": "event_id=177451&category=11&year=2022&title=NBA+FINALS%3A+CELTICS+VS.+WARRIORS",
}
WIKIPEDIA = ["2022 NBA Finals", "2022 NBA playoffs", "2021–22 Golden State Warriors season"]


def get(url: str, polite: bool = False) -> str:
    """A cached GET."""
    RAW.mkdir(parents=True, exist_ok=True)
    cached = RAW / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".txt")
    if cached.exists():
        return cached.read_text()
    if polite:
        time.sleep(1.0)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8", errors="replace")
    cached.write_text(text)
    return text


def write(path: Path, text: str, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.with_name(path.name + ".meta.json").write_text(json.dumps(meta, indent=2) + "\n")


# -- ESPN: games, box scores, and recaps ----------------------------------------------------------------------------


def espn() -> None:
    schedule = json.loads(get(f"{ESPN}/teams/gs/schedule?season=2022&seasontype=3"))
    games, box, wins = [], [], defaultdict(lambda: {"GS": 0, "OPP": 0})
    totals: dict[str, dict] = {}
    for event in schedule["events"]:
        competition = event["competitions"][0]
        headline = competition["notes"][0]["headline"]  # "NBA Finals - Game 6"
        round_short, number = headline.rsplit(" - Game ", 1)
        series = f"2022 {ROUNDS[round_short]}"
        sides = {c["team"]["abbreviation"]: c for c in competition["competitors"]}
        opponent = next(c for abbr, c in sides.items() if abbr != "GS")
        ours, theirs = int(float(sides["GS"]["score"]["value"])), int(float(opponent["score"]["value"]))
        tally = wins[series]
        tally["GS" if ours > theirs else "OPP"] += 1
        name = opponent["team"]["displayName"]
        nickname = name.split()[-1]
        if 4 in tally.values():
            status = f"the Warriors won the series {tally['GS']}-{tally['OPP']}" if tally["GS"] == 4 else \
                f"the {nickname} won the series {tally['OPP']}-{tally['GS']}"
        elif tally["GS"] == tally["OPP"]:
            status = f"the series is tied {tally['GS']}-{tally['OPP']}"
        elif tally["GS"] > tally["OPP"]:
            status = f"the Warriors lead the series {tally['GS']}-{tally['OPP']}"
        else:
            status = f"the {nickname} lead the series {tally['OPP']}-{tally['GS']}"
        game = f"Game {number} of the {series}"
        date = event["date"].replace("Z", ":00Z") if event["date"].count(":") == 1 else event["date"]
        games.append({"game_id": event["id"], "game": game, "date": date, "series": series,
                      "opponent": name, "home": "Warriors" if sides["GS"]["homeAway"] == "home" else nickname,
                      "result": "beat" if ours > theirs else "lost to", "warriors_score": ours,
                      "opponent_score": theirs, "series_status": status})
        summary = json.loads(get(f"{ESPN}/summary?event={event['id']}"))
        for team in summary["boxscore"]["players"]:
            team_name = team["team"]["displayName"]
            stats = team["statistics"][0]
            labels = stats.get("labels") or stats.get("names")
            for athlete in stats["athletes"]:
                if athlete.get("didNotPlay") or not athlete.get("stats"):
                    continue
                values = dict(zip(labels, athlete["stats"]))
                if values.get("MIN") in (None, "", "0", "--"):
                    continue
                player, pid = athlete["athlete"]["displayName"], athlete["athlete"]["id"]
                row = {"row_id": f"{event['id']}-{pid}", "game_id": event["id"], "game": game, "date": date,
                       "player_id": pid, "player": player, "team": team_name,
                       "starter": "yes" if athlete.get("starter") else "no", "minutes": values["MIN"],
                       "points": values["PTS"], "rebounds": values["REB"], "assists": values["AST"],
                       "steals": values["STL"], "blocks": values["BLK"], "turnovers": values["TO"],
                       "field_goals": values["FG"], "threes": values["3PT"], "free_throws": values["FT"],
                       "plus_minus": values["+/-"]}
                box.append(row)
                if team_name == "Golden State Warriors":
                    t = totals.setdefault(pid, {"player_id": pid, "player": player, "games": 0, "minutes": 0,
                                                "points": 0, "rebounds": 0, "assists": 0, "threes_made": 0})
                    t["games"] += 1
                    for key, label in (("minutes", "MIN"), ("points", "PTS"), ("rebounds", "REB"), ("assists", "AST")):
                        t[key] += int(values[label])
                    t["threes_made"] += int(values["3PT"].split("-")[0])
        article = summary.get("article") or {}
        if article.get("story"):
            story = re.sub(r"(?i)<br\s*/?>|</p>", "\n\n", article["story"])
            story = html.unescape(re.sub(r"<[^>]+>", "", story))
            story = "\n\n".join(" ".join(p.split()) for p in story.split("\n\n") if p.strip())
            write(DATA / "recaps" / f"{event['id']}.txt", story,
                  {"title": article.get("headline"), "published": article.get("published"),
                   "source": f"{article.get('source') or 'ESPN'} via ESPN", "game": game})
    _csv(DATA / "games.csv", games)
    _csv(DATA / "box_scores.csv", box)
    end = (datetime.fromisoformat(games[-1]["date"].replace("Z", "+00:00")) + timedelta(hours=4)).isoformat()
    rows = []
    for t in totals.values():
        g = t["games"]
        rows.append({"player_id": t["player_id"], "player": t["player"], "games": g, "as_of": end,
                     "minutes_per_game": f"{t['minutes'] / g:.1f}", "points_per_game": f"{t['points'] / g:.1f}",
                     "rebounds_per_game": f"{t['rebounds'] / g:.1f}", "assists_per_game": f"{t['assists'] / g:.1f}",
                     "threes_made": t["threes_made"]})
    _csv(DATA / "player_totals.csv", sorted(rows, key=lambda r: -float(r["points_per_game"])))
    print(f"espn: {len(games)} games, {len(box)} box score rows, {len(rows)} Warriors players")


def _csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


# -- ASAP Sports: the Warriors' press conferences -------------------------------------------------------------------


def asap(rounds: list[str], practice: bool = False) -> None:
    count = 0
    for key in rounds:
        event = get(f"http://www.asapsports.com/show_events.php?{ASAP_EVENTS[key]}", polite=True)
        days = sorted(set(re.findall(r'href="?(http://www\.asapsports\.com/show_event\.php\?[^" >]+)', event)))
        for day in days:
            page = get(html.unescape(day), polite=True)
            for interview_id, people in re.findall(r'show_interview\.php\?id=(\d+)"?[^>]*>([^<]+)<', page):
                text = _transcript(get(f"http://www.asapsports.com/show_interview.php?id={interview_id}", polite=True))
                if text is None or "Golden State Warriors" not in text["team"]:
                    continue
                if not practice and not text["occasion"].lower().startswith("game"):
                    continue  # practice and media days: --practice
                write(DATA / "interviews" / f"{interview_id}.txt", text["body"], {
                    "title": f"{people.strip()}, {text['occasion']}, {SERIES[key]}", "series": SERIES[key],
                    "said_at": text["said_at"], "speakers": people.strip(), "team": text["team"],
                    "occasion": text["occasion"], "event": text["event"], "source": "ASAP Sports"})
                count += 1
    print(f"asap: {count} Warriors transcripts")


def _transcript(page: str) -> dict | None:
    """The header and the question-and-answer turns of one ASAP Sports transcript."""
    text = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", page)
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"(?i)<br\s*/?>|</p>", "\n", text)))
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    start = next((i for i, line in enumerate(lines) if re.fullmatch(r"[A-Z][a-z]+ \d{1,2}, \d{4}", line)), None)
    if start is None:
        return None
    first_turn = next((i for i in range(start, len(lines)) if lines[i].startswith("Q.") or
                       re.match(r"^[A-Z][A-Z .'\-]+:", lines[i])), None)
    end = next((i for i in range(len(lines) - 1, start, -1) if lines[i].startswith("FastScripts")), len(lines))
    if first_turn is None:
        return None
    header = lines[start + 1:first_turn]
    day = datetime.strptime(lines[start], "%B %d, %Y")
    occasion = next((h for h in header if re.match(r"(?i)^(game \d|practice|media|pre|post)", h)), "Press conference")
    # ASAP gives the local date. Postgame press conferences run about 11:30 p.m. Eastern; the rest about 4 p.m.
    late = "postgame" in occasion.lower()
    said_at = (day + timedelta(hours=27, minutes=30) if late else day + timedelta(hours=20)).strftime(
        "%Y-%m-%dT%H:%M:00Z")
    team = next((h for h in header if "Warriors" in h or "Celtics" in h or "Mavericks" in h or "Grizzlies" in h
                 or "Nuggets" in h), "")
    body = "\n\n".join(lines[first_turn:end])
    return {"event": lines[start - 1], "said_at": said_at, "occasion": occasion, "team": team,
            "body": "\n\n".join([*header, body])}


# -- Wikipedia --------------------------------------------------------------------------------------------------------


def wikipedia() -> None:
    for title in WIKIPEDIA:
        query = urllib.parse.urlencode({"action": "query", "prop": "extracts|revisions", "explaintext": 1,
                                        "rvprop": "timestamp", "titles": title, "format": "json", "redirects": 1})
        page = next(iter(json.loads(get(f"https://en.wikipedia.org/w/api.php?{query}"))["query"]["pages"].values()))
        text = re.sub(r"\n{3,}", "\n\n", page["extract"]).strip()
        text = text.split("\n\n== See also ==")[0].split("\n\n== References ==")[0]
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        write(DATA / "articles" / f"{slug}.txt", text, {
            "title": page["title"], "published": page["revisions"][0]["timestamp"], "source": "Wikipedia",
            "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_")),
            "license": "CC BY-SA 4.0"})
    print(f"wikipedia: {len(WIKIPEDIA)} articles")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--practice", action="store_true", help="Also practice and media days")
    parser.add_argument("--rounds", default="finals", help="Interview rounds: finals (default), all, or a list "
                                                           "such as west,finals")
    args = parser.parse_args()
    espn()
    wikipedia()
    asap(list(ASAP_EVENTS) if args.rounds == "all" else args.rounds.split(","), practice=args.practice)
