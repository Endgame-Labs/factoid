# factoid-nba

This example runs [Factoid](https://github.com/Endgame-Labs/factoid) on the Golden State Warriors' 2022 playoff run. Box
scores, game logs, AP recaps, press conference transcripts, and encyclopedia articles go in. Facts linked to players,
teams, games, and series come out. It shows structured and prose documents side by side, a fact that changes from game
to game (the series standing), and the difference between what happened and what someone said about it.

## Layout

```text
nba/
├── settings.py    # the same models as the legal app
├── documents.py   # GameLog, BoxScore, and PlayerTotals (CSV); Interview, Recap, and Article (prose)
├── entities.py    # Player, Team, Game, Series, and Person
└── facts.py       # Reported and Remark, and five traits: Injury, Milestone, Shooting, Defense, and Result
evals/
└── playoffs.py    # the whole run, with eleven checks written from the source data before any run
fetch.py           # downloads the data into data/
```

## Data

None of the data is committed. `fetch.py` downloads it into `data/` (ignored by git) and caches every response:

- **Box scores and game logs:** Data from ESPN's public site API for the Warriors' 22 playoff games. `fetch.py` writes
  three CSV files: `games.csv` (one row per game), `box_scores.csv` (491 rows, with one row per player per game for both
  teams), and `player_totals.csv` (each Warriors player's averages over the run, computed from the box scores).
- **Game recaps:** The AP story that ESPN carries for each of the 22 games, along with its publish time.
- **Interviews:** Press conference transcripts for the Warriors from ASAP Sports. By default, `fetch.py` downloads the
  NBA Finals game days (45 pregame and postgame transcripts). `--rounds all` adds the other three series, and
  `--practice` adds practice and media days.
- **Articles:** Three Wikipedia articles (CC BY-SA 4.0) covering the 2022 NBA Finals, the 2022 NBA playoffs, and the
  Warriors' 2021-22 season.

The recaps and transcripts are copyrighted by their publishers. They are read for this example and never redistributed.

## Running it

```sh
uv sync
uv run python fetch.py                     # about 3 minutes, once
factoid struct try data/games.csv --rows 3 # the game log's sentences, with no model calls
factoid eval playoffs                      # the whole run, with its checks
factoid stats --examples 3 --data-dir runs/<time>/playoffs/default
```

## How the documents are read

- `GameLog`, `BoxScore`, and `PlayerTotals` are structured documents. ESPN IDs link players, games, and teams exactly.
  Each templated cell becomes one fact cited to its file, row, and column, with no model call.
- The game log sets `resolve_cells = True`, so each game's series standing ("In the 2022 NBA Finals, the Celtics lead
  the series 2-1.") supersedes the previous one. The template writes the standing as a current state, without
  "after Game 3", and the row's date says when it held. With "after Game 3", each standing would describe one fixed
  moment that stays true, so nothing would supersede it.
- `Interview` sets `speaker_pattern` for ASAP's "Q." and "STEPHEN CURRY:" labels, so each quote carries its speaker.
  Facts from answers are classified as `Remark` (what a player or coach says they think, feel, or plan) or `Reported`
  (what happened).
- `Recap` and `Article` produce `Reported` facts dated by their publish or revision time.

## Results (2026-11-16)

One run across all 73 documents took 36 minutes, 15,366 model calls, and 20.4 million tokens. The run passes 11 of 11
checks:

| Check | Result |
| --- | --- |
| Game log: Game 6 of the Finals, 103-90 over Boston | ok |
| Game log: earlier Finals standings replaced, the 4-2 title current | ok |
| Search: as of June 10, 2022 (after Game 3), the Celtics lead 2-1 | ok |
| Box score: Curry's 34 points in Finals Game 6, linked to the game | ok |
| Totals: Curry averaged 27.4 points | ok |
| Entities: Curry links box scores, recaps, interviews, and articles | ok |
| Entities: one Stephen Curry | ok |
| Recaps: Curry was Finals MVP, with the Milestone trait | ok |
| Interviews: a remark by Curry, quoted with him as the speaker | ok |
| Injury: a fact about an injury to Curry or Klay Thompson | ok |
| Entities: the Celtics link the game log and the recaps | ok |

Two of the checks needed fixes after the first full run. Both fixes were in the checks, not the app. The standings check
counted interview remarks that mentioned the series. The title check expected the game log's 4-2 result to stay current,
but a later article restates that result and supersedes it.

## Facts and entities

From the run above (`factoid stats --examples 3`):

| Documents | Count | Facts |
| --- | --- | --- |
| Interview | 45 | 1,033 |
| Recap | 22 | 938 |
| Article | 3 | 658 |
| BoxScore | 1 (491 rows) | 982 |
| GameLog | 1 (22 rows) | 44 |
| PlayerTotals | 1 (14 rows) | 28 |
| All | 73 | 3,683 |

Facts by status: 3,483 current, 145 superseded, 53 contradicted, and 2 ended. Facts by class: 2,654 `Reported` and
1,029 `Remark`.

| Entities | Count | Most facts |
| --- | --- | --- |
| Player | 146 | Stephen Curry (638), Draymond Green (425), Klay Thompson (326) |
| Person | 54 | Steve Kerr (376), Gary Payton (47), Michael Malone (23) |
| Untyped | 51 | 2022 NBA playoffs (98), NBA (55), Chase Center (19) |
| Team | 29 | Golden State Warriors (1,310), Boston Celtics (550), Dallas Mavericks (218) |
| Game | 28 | Game 5 of the 2022 NBA Finals (135), Game 1 of the 2022 NBA Finals (98), Game 2 of the 2022 Western Conference First Round (91) |
| Series | 13 | 2022 NBA Finals (541), 2022 Eastern Conference Finals (26), 2022 Western Conference Finals (19) |
| All | 321 | |

Sample facts:

- `Remark`: "Steve Kerr said the 2022 NBA Finals championship is Stephen Curry's crowning achievement in what has
  already been an incredible career."
- `Remark`: "Steve Kerr said that Stephen Curry went through everything at the Golden State Warriors' shootaround on the
  morning of Game 4 of the 2022 NBA Finals and told Kerr he felt good."
- `Reported`: "Stephen Curry became the first player in NBA history to surpass 500 three-pointers in the playoffs,
  finishing with 561."
- `Reported`: "In the 2022 NBA Finals, the Celtics lead the series 2-1." (from `games.csv`, row 19; superseded on
  June 11, 2022)
- `Reported`: "Stephen Curry of the Golden State Warriors had 34 points, 7 rebounds, and 7 assists in 40 minutes in Game
  6 of the 2022 NBA Finals." (from `box_scores.csv`)

## What it gets wrong

- Recaps and transcripts often use bare game names like "Game 4", and the extractor sometimes keeps them as-is. "Game 1"
  to "Game 4" became four extra Game entities (10 to 48 facts each) instead of linking to the right game. The same
  happens with series names: "NBA Finals", "Denver series", and "2022 NBA playoffs first round" stay separate from the
  series in the game log. Of the 28 Game and 13 Series entities, 22 games and 4 series are from the Warriors' run. Some
  of the others are real events outside that run, such as the 2019 Finals and the 2022 Eastern Conference Finals.
- ASAP's transcript headers list Gary Payton II as "Gary Payton", which is also his father's name. He became a Person
  rather than a Player.
- Some facts are not self-contained. For example, this fact does not say which series: "Andrew Wiggins hit a
  second-chance 3-pointer to put the Golden State Warriors ahead for good at 112-111 in Game 3."

Fixing these issues requires app-level changes, such as guidance that always names the series or passing a game's
context to the extractor. Those changes have not been tried yet.
