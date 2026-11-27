# Output samples

Structured files in, prose facts out. Each section below shows a few rows of one of this example's CSV
files, ingested on their own into a scratch store, and the facts Factoid made from them. A templated cell
becomes one sentence, with no model call, cited to its file, row, and column, and linked to the players,
teams, games, and series its identity columns name. The full record of each fact, as `factoid fact` and the
HTTP API return it, is in the `.jsonl` file of the same name.

Made by `uv run python output_samples/make.py`, from data that `fetch.py` downloads from ESPN's public site
API.

## GameLog

The Warriors' playoff games, one game per row, with the score and the series standing after it. Rows from `games.csv`:

| game | date | result | warriors_score | opponent_score | series_status |
| --- | --- | --- | --- | --- | --- |
| Game 1 of the 2022 NBA Finals | 2022-06-03T01:00:00Z | lost to | 108 | 120 | the Celtics lead the series 1-0 |
| Game 2 of the 2022 NBA Finals | 2022-06-06T00:00:00Z | beat | 107 | 88 | the series is tied 1-1 |
| Game 3 of the 2022 NBA Finals | 2022-06-09T01:00:00Z | lost to | 100 | 116 | the Celtics lead the series 2-1 |
| Game 4 of the 2022 NBA Finals | 2022-06-11T01:00:00Z | beat | 107 | 97 | the series is tied 2-2 |
| Game 5 of the 2022 NBA Finals | 2022-06-14T01:00:00Z | beat | 104 | 94 | the Warriors lead the series 3-2 |
| Game 6 of the 2022 NBA Finals | 2022-06-17T01:00:00Z | beat | 103 | 90 | the Warriors won the series 4-2 |

Facts:

| Fact | Status | Held | From | Linked to |
| --- | --- | --- | --- | --- |
| The Golden State Warriors lost to the Boston Celtics 120-108 in Game 1 of the 2022 NBA Finals. | current | 2022-06-03 to now | row 1, `result` | Game 1 of the 2022 NBA Finals (subject), Boston Celtics (about) |
| In the 2022 NBA Finals, the Celtics lead the series 1-0. | superseded | 2022-06-03 to 2022-06-06 | row 1, `series_status` | Game 1 of the 2022 NBA Finals (subject), 2022 NBA Finals (about) |
| The Golden State Warriors beat the Boston Celtics 107-88 in Game 2 of the 2022 NBA Finals. | current | 2022-06-06 to now | row 2, `result` | Game 2 of the 2022 NBA Finals (subject), Boston Celtics (about) |
| In the 2022 NBA Finals, the series is tied 1-1. | superseded | 2022-06-06 to 2022-06-09 | row 2, `series_status` | Game 2 of the 2022 NBA Finals (subject), 2022 NBA Finals (about) |
| The Golden State Warriors lost to the Boston Celtics 116-100 in Game 3 of the 2022 NBA Finals. | current | 2022-06-09 to now | row 3, `result` | Game 3 of the 2022 NBA Finals (subject), Boston Celtics (about) |
| In the 2022 NBA Finals, the Celtics lead the series 2-1. | superseded | 2022-06-09 to 2022-06-11 | row 3, `series_status` | Game 3 of the 2022 NBA Finals (subject), 2022 NBA Finals (about) |
| The Golden State Warriors beat the Boston Celtics 107-97 in Game 4 of the 2022 NBA Finals. | current | 2022-06-11 to now | row 4, `result` | Game 4 of the 2022 NBA Finals (subject), Boston Celtics (about) |
| In the 2022 NBA Finals, the series is tied 2-2. | superseded | 2022-06-11 to 2022-06-14 | row 4, `series_status` | Game 4 of the 2022 NBA Finals (subject), 2022 NBA Finals (about) |
| The Golden State Warriors beat the Boston Celtics 104-94 in Game 5 of the 2022 NBA Finals. | current | 2022-06-14 to now | row 5, `result` | Game 5 of the 2022 NBA Finals (subject), Boston Celtics (about) |
| In the 2022 NBA Finals, the Warriors lead the series 3-2. | superseded | 2022-06-14 to 2022-06-17 | row 5, `series_status` | Game 5 of the 2022 NBA Finals (subject), 2022 NBA Finals (about) |
| The Golden State Warriors beat the Boston Celtics 103-90 in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 6, `result` | Game 6 of the 2022 NBA Finals (subject), Boston Celtics (about) |
| In the 2022 NBA Finals, the Warriors won the series 4-2. | current | 2022-06-17 to now | row 6, `series_status` | Game 6 of the 2022 NBA Finals (subject), 2022 NBA Finals (about) |

## BoxScore

Player box scores from the Warriors' playoff games, one player in one game per row. Rows from `box_scores.csv`:

| player | team | minutes | points | rebounds | assists | threes |
| --- | --- | --- | --- | --- | --- | --- |
| Draymond Green | Golden State Warriors | 42 | 12 | 12 | 8 | 2-5 |
| Andrew Wiggins | Golden State Warriors | 44 | 18 | 6 | 5 | 4-9 |
| Otto Porter Jr. | Golden State Warriors | 13 | 6 | 1 | 0 | 2-3 |
| Stephen Curry | Golden State Warriors | 40 | 34 | 7 | 7 | 6-11 |
| Klay Thompson | Golden State Warriors | 41 | 12 | 5 | 2 | 2-8 |
| Jayson Tatum | Boston Celtics | 40 | 13 | 3 | 7 | 1-4 |
| Al Horford | Boston Celtics | 39 | 19 | 14 | 2 | 4-5 |
| Robert Williams III | Boston Celtics | 33 | 10 | 7 | 2 | 0-0 |
| Marcus Smart | Boston Celtics | 38 | 9 | 6 | 9 | 1-2 |
| Jaylen Brown | Boston Celtics | 44 | 34 | 7 | 3 | 5-11 |

Facts:

| Fact | Status | Held | From | Linked to |
| --- | --- | --- | --- | --- |
| Draymond Green of the Golden State Warriors had 12 points, 12 rebounds, and 8 assists in 42 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 1, `points` | Game 6 of the 2022 NBA Finals (about), Draymond Green (about), Golden State Warriors (about) |
| Draymond Green shot 2-5 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 1, `threes` | Game 6 of the 2022 NBA Finals (about), Draymond Green (about) |
| Andrew Wiggins of the Golden State Warriors had 18 points, 6 rebounds, and 5 assists in 44 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 2, `points` | Game 6 of the 2022 NBA Finals (about), Andrew Wiggins (about), Golden State Warriors (about) |
| Andrew Wiggins shot 4-9 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 2, `threes` | Game 6 of the 2022 NBA Finals (about), Andrew Wiggins (about) |
| Otto Porter Jr. of the Golden State Warriors had 6 points, 1 rebound, and 0 assists in 13 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 3, `points` | Game 6 of the 2022 NBA Finals (about), Otto Porter Jr. (about), Golden State Warriors (about) |
| Otto Porter Jr. shot 2-3 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 3, `threes` | Game 6 of the 2022 NBA Finals (about), Otto Porter Jr. (about) |
| Stephen Curry of the Golden State Warriors had 34 points, 7 rebounds, and 7 assists in 40 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 4, `points` | Game 6 of the 2022 NBA Finals (about), Stephen Curry (about), Golden State Warriors (about) |
| Stephen Curry shot 6-11 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 4, `threes` | Game 6 of the 2022 NBA Finals (about), Stephen Curry (about) |
| Klay Thompson of the Golden State Warriors had 12 points, 5 rebounds, and 2 assists in 41 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 5, `points` | Game 6 of the 2022 NBA Finals (about), Klay Thompson (about), Golden State Warriors (about) |
| Klay Thompson shot 2-8 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 5, `threes` | Game 6 of the 2022 NBA Finals (about), Klay Thompson (about) |
| Jayson Tatum of the Boston Celtics had 13 points, 3 rebounds, and 7 assists in 40 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 6, `points` | Game 6 of the 2022 NBA Finals (about), Jayson Tatum (about), Boston Celtics (about) |
| Jayson Tatum shot 1-4 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 6, `threes` | Game 6 of the 2022 NBA Finals (about), Jayson Tatum (about) |
| Al Horford of the Boston Celtics had 19 points, 14 rebounds, and 2 assists in 39 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 7, `points` | Game 6 of the 2022 NBA Finals (about), Al Horford (about), Boston Celtics (about) |
| Al Horford shot 4-5 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 7, `threes` | Game 6 of the 2022 NBA Finals (about), Al Horford (about) |
| Robert Williams III of the Boston Celtics had 10 points, 7 rebounds, and 2 assists in 33 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 8, `points` | Game 6 of the 2022 NBA Finals (about), Robert Williams III (about), Boston Celtics (about) |
| Marcus Smart of the Boston Celtics had 9 points, 6 rebounds, and 9 assists in 38 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 9, `points` | Game 6 of the 2022 NBA Finals (about), Marcus Smart (about), Boston Celtics (about) |
| Marcus Smart shot 1-2 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 9, `threes` | Game 6 of the 2022 NBA Finals (about), Marcus Smart (about) |
| Jaylen Brown of the Boston Celtics had 34 points, 7 rebounds, and 3 assists in 44 minutes in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 10, `points` | Game 6 of the 2022 NBA Finals (about), Jaylen Brown (about), Boston Celtics (about) |
| Jaylen Brown shot 5-11 from three-point range in Game 6 of the 2022 NBA Finals. | current | 2022-06-17 to now | row 10, `threes` | Game 6 of the 2022 NBA Finals (about), Jaylen Brown (about) |

## PlayerTotals

Warriors players' averages over the 2022 playoffs, computed from the box scores. Rows from `player_totals.csv`:

| player | games | points_per_game | rebounds_per_game | assists_per_game | threes_made |
| --- | --- | --- | --- | --- | --- |
| Stephen Curry | 22 | 27.4 | 5.2 | 5.9 | 91 |
| Klay Thompson | 22 | 19.0 | 3.9 | 2.3 | 77 |
| Draymond Green | 22 | 8.0 | 7.2 | 6.3 | 8 |

Facts:

| Fact | Status | Held | From | Linked to |
| --- | --- | --- | --- | --- |
| Stephen Curry averaged 27.4 points, 5.2 rebounds, and 5.9 assists in 22 games of the Golden State Warriors' 2022 playoffs. | current | 2022-06-17 to now | row 1, `points_per_game` | Stephen Curry (subject) |
| Stephen Curry made 91 three-pointers in the Golden State Warriors' 2022 playoffs. | current | 2022-06-17 to now | row 1, `threes_made` | Stephen Curry (subject) |
| Klay Thompson averaged 19.0 points, 3.9 rebounds, and 2.3 assists in 22 games of the Golden State Warriors' 2022 playoffs. | current | 2022-06-17 to now | row 2, `points_per_game` | Klay Thompson (subject) |
| Klay Thompson made 77 three-pointers in the Golden State Warriors' 2022 playoffs. | current | 2022-06-17 to now | row 2, `threes_made` | Klay Thompson (subject) |
| Draymond Green averaged 8.0 points, 7.2 rebounds, and 6.3 assists in 22 games of the Golden State Warriors' 2022 playoffs. | current | 2022-06-17 to now | row 3, `points_per_game` | Draymond Green (subject) |
| Draymond Green made 8 three-pointers in the Golden State Warriors' 2022 playoffs. | current | 2022-06-17 to now | row 3, `threes_made` | Draymond Green (subject) |
