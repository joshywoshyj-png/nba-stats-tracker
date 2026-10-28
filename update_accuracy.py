
"""
COURTSIDE — NBA ACCURACY TRACKER

Saves pregame predictions, scores completed NBA games,
tracks six player stats, and excludes confirmed in-game
injuries from injury-adjusted accuracy.

Game dates use America/Chicago local time.
"""

import csv
import math
import re
import unicodedata
from collections import defaultdict
from statistics import median
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
CHICAGO = ZoneInfo("America/Chicago")
NOW = datetime.now(UTC)

STATS = (
    "points", "rebounds", "assists",
    "three_pointers", "steals", "blocks"
)

HISTORY = Path("nba_prediction_history.csv")
RESULTS = Path("nba_prediction_results.csv")
IN_GAME_INJURIES = Path("nba_in_game_injuries.csv")

HISTORY_FIELDS = [
    "game_key", "game_date", "tipoff_utc", "saved_utc",
    "player_id", "player_name", "team", "opponent",
    "projected_minutes", "position", "baseline_games", "model_version"
] + [f"pred_{s}" for s in STATS] + [
    f"baseline_{s}" for s in STATS
] + [f"range_low_{s}" for s in STATS] + [
    f"range_high_{s}" for s in STATS
]

RESULT_FIELDS = HISTORY_FIELDS + [
    "injury_excluded", "injury_note", "actual_minutes"
] + [f"actual_{s}" for s in STATS] + [
    f"error_{s}" for s in STATS
] + [f"covered_{s}" for s in STATS]

ATTEMPT_KEYS = [
    "three_pointers_attempted",
    "three_point_attempts",
    "three_point_attempted",
    "three_pointers_attempts",
    "three_point_attempts_pg",
    "three_pointers_attempted_pg",
    "three_pa",
    "three_pa_pg",
    "three_point_attempts_per_game",
    "three_pointers_attempted_per_game",
    "fg3a",
    "fg3a_pg",
    "3pa",
    "3pa_pg"
]


def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, fields, rows):
    columns = list(fields)
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=columns, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def n(value):
    try:
        if value is None or str(value).strip() == "":
            return 0.0
        x = float(value)
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def clamp(x, low, high):
    return max(low, min(high, x))


def norm(x):
    return str(x or "").strip().upper()


def name_key(x):
    text = unicodedata.normalize("NFKD", str(x or ""))
    text = "".join(
        c for c in text if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z]", "", text.lower())


def parse_time(value):
    try:
        d = datetime.fromisoformat(
            str(value or "").replace("Z", "+00:00")
        )
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return d.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def date_value(value):
    value = str(value or "").strip()
    try:
        if len(value) >= 10 and value[4] == "-":
            return datetime.strptime(
                value[:10], "%Y-%m-%d"
            ).date()

        if len(value) >= 8 and value[:8].isdigit():
            return datetime.strptime(
                value[:8], "%Y%m%d"
            ).date()
    except ValueError:
        pass
    return None


def local_date(tip):
    return tip.astimezone(CHICAGO).date()


def minutes(row):
    for key in ("minutes", "minutes_played", "minutes_pg"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return n(value)
    return 0.0


def attempts(row):
    for key in ATTEMPT_KEYS:
        if key in row and str(row[key] or "").strip() != "":
            return n(row[key])
    return None


def position_group(position):
    p = norm(position)
    if p in ("PG", "SG", "G"):
        return "G"
    if p in ("SF", "PF", "F"):
        return "F"
    return "C" if p == "C" else ""


def sample_rate(logs, stat, fallback):
    valid = [
        row for row in logs
        if minutes(row) > 0
        and str(row.get(stat, "")).strip() != ""
    ]
    total = sum(minutes(row) for row in valid)
    if total <= 0:
        return fallback
    return sum(n(row.get(stat)) for row in valid) / total


def attempt_rate(logs, fallback):
    valid = [
        row for row in logs
        if minutes(row) > 0 and attempts(row) is not None
    ]
    total = sum(minutes(row) for row in valid)
    if total <= 0:
        return fallback
    return sum(attempts(row) for row in valid) / total


def predict_three(player, recent, projected, df, pf, boost):
    season_minutes = n(player.get("minutes_pg"))
    season_makes = n(player.get("three_pointers_pg"))
    season_attempts = attempts(player)

    def fallback():
        sr = (
            season_makes / season_minutes
            if season_minutes > 0 else 0
        )
        l10 = sample_rate(
            recent[:10], "three_pointers", sr
        )
        valid = [
            row for row in recent
            if minutes(row) > 0
            and str(row.get("three_pointers", "")).strip() != ""
        ]
        games = n(player.get("games_played"))
        sw = games / (games + 12)
        stable = sw * sr + (1 - sw) * l10
        rw = len(valid) / (len(valid) + 10)
        return (
            projected * ((1 - rw) * stable + rw * l10)
            * df * pf * (1 + boost)
        )

    if (
        season_attempts is None
        or season_attempts <= 0
        or season_minutes <= 0
    ):
        return max(0, fallback())

    if not any(
        minutes(row) > 0 and attempts(row) is not None
        for row in recent
    ):
        return max(0, fallback())

    season_attempt_rate = season_attempts / season_minutes

    l10 = attempt_rate(recent[:10], season_attempt_rate)
    l5 = attempt_rate(recent[:5], season_attempt_rate)

    projected_attempts = projected * (
        .50 * season_attempt_rate
        + .30 * l10
        + .20 * l5
    )

    season_pct = clamp(
        season_makes / season_attempts, 0, 1
    )

    valid = [
        row for row in recent[:10]
        if minutes(row) > 0
        and attempts(row) is not None
        and str(row.get("three_pointers", "")).strip() != ""
    ]

    recent_attempts = sum(attempts(row) for row in valid)
    recent_makes = sum(
        n(row.get("three_pointers")) for row in valid
    )

    expected_pct = clamp(
        (recent_makes + 60 * season_pct)
        / (recent_attempts + 60),
        0, 1
    )

    return max(
        0,
        projected_attempts * expected_pct
        * df * pf * (1 + boost)
    )


def quantile(values, q=.8):
    if not values:
        return None
    values = sorted(values)
    idx = min(
        len(values) - 1,
        max(0, math.ceil(q * (len(values) + 1)) - 1)
    )
    return values[idx]


def player_variability(stat, recent, player, projected, prediction):
    vals = [
        n(row.get(stat)) * projected / minutes(row)
        for row in recent[:20]
        if minutes(row) > 0
        and str(row.get(stat, "")).strip() != ""
    ]

    mean = sum(vals) / len(vals) if vals else 0

    sd = (
        math.sqrt(
            sum((v - mean) ** 2 for v in vals)
            / (len(vals) - 1)
        )
        if len(vals) >= 3
        else math.sqrt(max(1, prediction))
    )

    prior = max(.5, math.sqrt(max(1, prediction)))

    return max(
        .5,
        math.sqrt(
            (len(vals) * sd * sd + 8 * prior * prior)
            / (len(vals) + 8)
        )
    )


def calibrated_half_width(
    stat, player, recent, projected,
    prediction, past_results, tip
):
    eligible = [
        r for r in past_results
        if (
            parse_time(r.get("tipoff_utc"))
            or datetime.max.replace(tzinfo=UTC)
        ) < tip
        and str(r.get("error_" + stat, "")).strip() != ""
    ]

    if len(eligible) < 30:
        return None

    pooled = quantile([
        n(r.get("error_" + stat))
        for r in eligible
    ])

    personal = [
        n(r.get("error_" + stat))
        for r in eligible
        if str(r.get("player_id"))
        == str(player.get("player_id"))
    ]

    individual = (
        quantile(personal)
        if len(personal) >= 8 else pooled
    )

    blend = len(personal) / (len(personal) + 25)
    prior = max(.5, math.sqrt(max(1, prediction)))

    scale = clamp(
        player_variability(
            stat, recent, player, projected, prediction
        ) / prior,
        .65, 1.8
    )

    return max(
        .25,
        (pooled * (1 - blend) + individual * blend) * scale
    )


def prior_rest_factor(recent, game_day):
    """Small, conservative adjustment when the player's prior game was yesterday."""
    days = [(game_day - d).days for row in recent
            if (d := date_value(row.get("date"))) and d < game_day]
    if not days:
        return 1.0
    return 0.985 if min(days) == 1 else 1.0


def historical_bias(stat, player_id, past_results, tip):
    """Shrink signed pregame residuals toward zero; never train on future games."""
    eligible = [r for r in past_results
                if (t := parse_time(r.get("tipoff_utc"))) and t < tip
                and str(r.get("injury_excluded", "0")).lower() not in ("1", "true", "yes")
                and str(r.get("actual_" + stat, "")).strip()
                and str(r.get("pred_" + stat, "")).strip()]
    if len(eligible) < 40:
        return 0.0
    pool = [n(r["actual_" + stat]) - n(r["pred_" + stat]) for r in eligible]
    personal = [n(r["actual_" + stat]) - n(r["pred_" + stat]) for r in eligible
                if str(r.get("player_id")) == str(player_id)]
    pooled = sum(pool) / len(pool)
    own = sum(personal) / len(personal) if personal else pooled
    shrink = len(personal) / (len(personal) + 30)
    return clamp(.20 * pooled + .30 * shrink * (own - pooled), -1.5, 1.5)


def optimized_blend(stat, past_results, tip):
    """Conservative pregame-only MAE optimization, with chronological validation.

    Uses immutable, previously saved forecasts and season baselines. Only games
    completed before tipoff are eligible. Avoids fitting on the holdout period.
    """
    samples = []
    for row in past_results:
        t = parse_time(row.get("tipoff_utc"))
        if not t or t >= tip or str(row.get("injury_excluded", "0")).lower() in ("1", "true", "yes"):
            continue
        keys = ["pred_" + stat, "baseline_" + stat, "actual_" + stat]
        if any(not str(row.get(k, "")).strip() for k in keys):
            continue
        vals = [n(row[k]) for k in keys]
        if not all(math.isfinite(v) for v in vals):
            continue
        samples.append((t, *vals))
    samples.sort(key=lambda row: row[0])
    if len(samples) < 100:
        return 1.0
    # Entire dates stay together, so same-day outcomes cannot leak across splits.
    dates = sorted({local_date(row[0]) for row in samples})
    if len(dates) < 6:
        return 1.0
    boundary = dates[max(1, int(len(dates) * .75))]
    train = [row for row in samples if local_date(row[0]) < boundary]
    holdout = [row for row in samples if local_date(row[0]) >= boundary]
    if len(train) < 70 or len(holdout) < 25:
        return 1.0
    def mae(rows, weight):
        return sum(abs(weight*p + (1-weight)*b - a) for _,p,b,a in rows) / len(rows)
    candidates = (0.0, .25, .5, .75, 1.0)
    best = min(candidates, key=lambda w: mae(train, w))
    # Only enable the adjustment if it improves on BOTH saved forecast and
    # season-average on later unseen games, by at least 1%.
    score = mae(holdout, best)
    if score >= .99 * min(mae(holdout, 1.0), mae(holdout, 0.0)):
        return 1.0
    # Shrink optimization toward the original model to reduce overfitting.
    return round(.75 * best + .25, 3)


def main():
    players = read_csv("nba_stats.csv")
    logs = read_csv("nba_game_logs.csv")
    schedule = read_csv("nba_schedule.csv")
    defense = read_csv("nba_opponent_defense.csv")
    pace = read_csv("nba_team_pace.csv")
    injuries = read_csv("nba_injuries.csv")

    history = read_csv(HISTORY)
    previous_results = read_csv(RESULTS)

    # FIX: Correct historical dates to Chicago local time.
    corrected_dates = 0

    for record in history:
        tip = parse_time(record.get("tipoff_utc"))

        if tip is None:
            continue

        correct_date = local_date(tip).isoformat()

        if record.get("game_date") != correct_date:
            record["game_date"] = correct_date
            corrected_dates += 1

    print("Historical game dates corrected:", corrected_dates)

    # Confirmed in-game injuries are excluded
    # from injury-adjusted MAE.
    confirmed_injuries = {}

    for entry in read_csv(IN_GAME_INJURIES):
        if norm(entry.get("confirmed")) not in {
            "YES", "TRUE", "1"
        }:
            continue

        key = (
            str(entry.get("game_key", "")).strip(),
            str(entry.get("player_id", "")).strip()
        )

        if all(key):
            confirmed_injuries[key] = entry.get("note", "")

    print("COURTSIDE ACCURACY UPDATE")
    print("Players:", len(players))
    print("Game logs:", len(logs))
    print("Schedule games:", len(schedule))
    print("Existing snapshots:", len(history))

    logs_by_player = defaultdict(list)

    for log in logs:
        pid = str(log.get("player_id", ""))
        if pid:
            logs_by_player[pid].append(log)

    for entries in logs_by_player.values():
        entries.sort(
            key=lambda row: (
                date_value(row.get("date"))
                or datetime.min.date()
            ),
            reverse=True
        )

    pace_map = {
        norm(row.get("team")): row
        for row in pace
    }

    defense_baselines = defaultdict(lambda: [0.0, 0.0])

    for row in defense:
        count = n(row.get("player_games"))
        if count <= 0:
            continue

        for stat in STATS:
            key = (
                row.get("position_type", ""),
                row.get("position", ""),
                stat
            )

            baseline = defense_baselines[key]
            baseline[0] += (
                count * n(row.get(stat + "_allowed_pg"))
            )
            baseline[1] += count

    def pace_factor(team, opponent):
        own = pace_map.get(norm(team))
        other = pace_map.get(norm(opponent))

        if not own or not other:
            return 1.0

        a = n(own.get("adjusted_pace"))
        b = n(other.get("adjusted_pace"))

        if a <= 0 or b <= 0:
            return 1.0

        return clamp(
            ((a + b) / 2) / a, .90, 1.10
        )

    def defense_pace(opponent):
        row = pace_map.get(norm(opponent))

        if not row:
            return 1.0

        league = n(row.get("league_average_pace"))
        opp = n(row.get("adjusted_pace"))

        if league <= 0 or opp <= 0:
            return 1.0

        return clamp(league / opp, .85, 1.15)

    def defense_factor(row, stat, opponent, game_day):
        if not row:
            return 1.0

        key = (
            row.get("position_type", ""),
            row.get("position", ""),
            stat
        )

        total, games = defense_baselines[key]

        if games <= 0 or total <= 0:
            return 1.0

        season_allowed = n(
            row.get(stat + "_allowed_pg")
        )

        recent_samples = [
            log for log in logs
            if norm(log.get("opponent")) == norm(opponent)
            and date_value(log.get("date"))
            and date_value(log.get("date")) < game_day
            and minutes(log) > 0
            and str(log.get(stat, "")).strip() != ""
            and (
                norm(log.get("position"))
                == norm(row.get("position"))
                if row.get("position_type") == "position"
                else position_group(log.get("position"))
                == norm(row.get("position"))
            )
        ]

        recent_samples.sort(
            key=lambda log: date_value(log.get("date")),
            reverse=True
        )

        recent_samples = recent_samples[:25]

        recent_allowed = (
            sum(n(log.get(stat)) for log in recent_samples)
            / len(recent_samples)
            if recent_samples else season_allowed
        )

        recent_weight = min(
            .25, len(recent_samples) / 100
        )

        blended = (
            season_allowed * (1 - recent_weight)
            + recent_allowed * recent_weight
        )

        raw = blended / (total / games)

        raw *= defense_pace(opponent)

        sample = n(row.get("player_games"))

        return clamp(
            1 + (sample / (sample + 20)) * .5 * (raw - 1),
            .85, 1.15
        )

    out_ids = set()
    out_names = set()

    for injury in injuries:
        if norm(injury.get("status")) not in {
            "OUT", "INACTIVE", "INJURED RESERVE",
            "SUSPENDED", "NOT WITH TEAM"
        }:
            continue

        if injury.get("player_id"):
            out_ids.add(str(injury["player_id"]))

        out_names.add((
            name_key(injury.get("player_name")),
            norm(injury.get("team"))
        ))

    def is_out(player):
        return (
            str(player.get("player_id", "")) in out_ids
            or (
                name_key(player.get("player_name")),
                norm(player.get("team"))
            ) in out_names
        )

    existing = {
        (
            row.get("game_key"),
            str(row.get("player_id", ""))
        )
        for row in history
    }

    new_snapshots = 0


    # Save predictions for upcoming games only.
    for game in schedule:
        tip = parse_time(game.get("date_utc"))

        if tip is None or not (
            NOW < tip <= NOW + timedelta(hours=48)
        ):
            continue

        home = norm(game.get("home"))
        away = norm(game.get("away"))

        if not home or not away:
            continue

        game_day = local_date(tip)
        game_key = f"{tip.isoformat()}|{away}|{home}"

        boosts = {}

        for team in (home, away):
            roster = [
                p for p in players
                if norm(p.get("team")) == team
                and n(p.get("games_played")) > 0
            ]

            absent = sum(
                n(p.get("minutes_pg"))
                for p in roster if is_out(p)
            )

            healthy_minutes = sum(
                n(p.get("minutes_pg"))
                for p in roster if not is_out(p)
            )

            boosts[team] = (
                absent,
                healthy_minutes,
                len(roster)
            )

        for player in players:
            team = norm(player.get("team"))

            if team not in (home, away):
                continue

            pid = str(player.get("player_id", ""))

            if not pid or is_out(player):
                continue

            if (game_key, pid) in existing:
                continue

            games = n(player.get("games_played"))
            season_minutes = n(player.get("minutes_pg"))

            if games <= 0 or season_minutes <= 0:
                continue

            opponent = away if team == home else home

            recent = [
                row for row in logs_by_player[pid]
                if date_value(row.get("date"))
                and date_value(row.get("date")) < game_day
            ][:10]

            played = [
                minutes(row) for row in recent
                if minutes(row) > 0
            ]

            recent_average = (
                sum(played) / len(played)
                if played else season_minutes
            )

            last5_minutes = played[:5]

            recent5_average = (
                sum(last5_minutes) / len(last5_minutes)
                if last5_minutes else season_minutes
            )

            base_projected = (
                .45 * season_minutes
                + .35 * recent_average
                + .20 * recent5_average
            )

            base_projected += clamp(
                recent5_average - recent_average,
                -3, 3
            ) * .25

            absent, healthy_minutes, roster_count = boosts[team]

            share = (
                season_minutes / healthy_minutes
                if healthy_minutes > 0 else 0
            )

            extra_minutes = min(
                base_projected * .12,
                absent * share * .35
            )

            projected = clamp(
                (base_projected + extra_minutes) * prior_rest_factor(recent, game_day), 0, 48
            )

            boost = (
                min(
                    .04,
                    (absent / 240) * .10 *
                    (
                        season_minutes /
                        max(
                            1,
                            healthy_minutes /
                            max(1, roster_count)
                        )
                    )
                )
                if absent > 0 and healthy_minutes > 0
                else 0
            )

            position = next(
                (
                    row.get("position")
                    for row in recent
                    if row.get("position")
                ),
                ""
            )

            defense_row = next(
                (
                    row for row in defense
                    if norm(row.get("opponent")) == opponent
                    and norm(row.get("position"))
                    == norm(position)
                    and row.get("position_type") == "position"
                ),
                None
            )

            if defense_row is None:
                grouped = position_group(position)

                defense_row = next(
                    (
                        row for row in defense
                        if norm(row.get("opponent")) == opponent
                        and norm(row.get("position")) == grouped
                        and row.get("position_type")
                        == "position_group"
                    ),
                    None
                )

            record = {
                "game_key": game_key,
                "game_date": game_day.isoformat(),
                "tipoff_utc": tip.isoformat(),
                "saved_utc": NOW.isoformat(),
                "player_id": pid,
                "player_name": player.get("player_name", ""),
                "team": team,
                "opponent": opponent,
                "projected_minutes": round(projected, 2),
                "position": position,
                "baseline_games": games,
                "model_version": "optimized-v2"
            }

            for stat in STATS:
                baseline = n(player.get(stat + "_pg"))
                season_rate = baseline / season_minutes

                l10 = sample_rate(
                    recent[:10], stat, season_rate
                )

                l5 = sample_rate(
                    recent[:5], stat, season_rate
                )

                df = defense_factor(
                    defense_row,
                    stat,
                    opponent,
                    game_day
                )

                pf = pace_factor(team, opponent)

                if stat == "three_pointers":
                    prediction = predict_three(
                        player,
                        recent,
                        projected,
                        df,
                        pf,
                        boost
                    )
                else:
                    if stat == "points":
                        weighted_rate = (
                            .55 * season_rate
                            + .30 * l10
                            + .15 * l5
                        )
                    elif stat == "rebounds":
                        weighted_rate = (
                            .50 * season_rate
                            + .30 * l10
                            + .20 * l5
                        )
                    elif stat == "assists":
                        weighted_rate = (
                            .45 * season_rate
                            + .35 * l10
                            + .20 * l5
                        )
                    elif stat in ("steals", "blocks"):
                        weighted_rate = (
                            .60 * season_rate
                            + .25 * l10
                            + .15 * l5
                        )
                    else:
                        weighted_rate = season_rate

                    prediction = max(
                        0,
                        projected * weighted_rate
                        * df * pf * (1 + boost)
                    )

                blend_weight = optimized_blend(stat, previous_results, tip)
                prediction = (blend_weight * prediction
                              + (1 - blend_weight) * baseline)
                prediction = max(0, prediction + historical_bias(
                    stat, pid, previous_results, tip))
                record["pred_" + stat] = round(
                    prediction, 3
                )

                record["baseline_" + stat] = round(
                    baseline, 3
                )

                width = calibrated_half_width(
                    stat,
                    player,
                    recent,
                    projected,
                    prediction,
                    previous_results,
                    tip
                )

                record["range_low_" + stat] = (
                    round(max(0, prediction - width), 3)
                    if width is not None else ""
                )

                record["range_high_" + stat] = (
                    round(prediction + width, 3)
                    if width is not None else ""
                )

            history.append(record)
            existing.add((game_key, pid))
            new_snapshots += 1

    # Save corrected historical dates and new predictions.
    write_csv(HISTORY, HISTORY_FIELDS, history)

    # Score completed games.
    results = []
    missing_logs = 0
    incomplete = 0
    waiting = 0
    late = 0
    invalid = 0

    for record in history:
        tip = parse_time(record.get("tipoff_utc"))

        if tip is None:
            invalid += 1
            continue

        saved = parse_time(record.get("saved_utc"))

        if saved is None or saved >= tip:
            late += 1
            continue

        if NOW < tip + timedelta(hours=2):
            waiting += 1
            continue

        pid = str(record.get("player_id", ""))
        opponent = norm(record.get("opponent"))
        game_day = local_date(tip)

        acceptable_dates = {
            game_day - timedelta(days=1),
            game_day,
            game_day + timedelta(days=1)
        }

        candidates = [
            row for row in logs_by_player.get(pid, [])
            if date_value(row.get("date")) in acceptable_dates
            and norm(row.get("opponent")) == opponent
            and minutes(row) > 0
        ]

        if not candidates:
            missing_logs += 1
            continue

        candidates.sort(
            key=lambda row: abs(
                (
                    date_value(row.get("date"))
                    - game_day
                ).days
            )
        )

        if len(candidates) > 1:
            first = abs(
                (
                    date_value(candidates[0].get("date"))
                    - game_day
                ).days
            )

            second = abs(
                (
                    date_value(candidates[1].get("date"))
                    - game_day
                ).days
            )

            if first == second:
                missing_logs += 1
                continue

        actual = candidates[0]

        if any(
            str(actual.get(stat, "")).strip() == ""
            for stat in STATS
        ):
            incomplete += 1
            continue

        result = dict(record)

        injury_key = (
            str(record.get("game_key", "")).strip(),
            str(record.get("player_id", "")).strip()
        )

        result["injury_excluded"] = int(
            injury_key in confirmed_injuries
        )

        result["injury_note"] = confirmed_injuries.get(
            injury_key, ""
        )

        result["actual_minutes"] = round(
            minutes(actual), 2
        )

        for stat in STATS:
            actual_value = n(actual.get(stat))
            predicted_value = n(
                record.get("pred_" + stat)
            )

            result["actual_" + stat] = actual_value

            result["error_" + stat] = round(
                abs(predicted_value - actual_value),
                3
            )

            low = record.get("range_low_" + stat, "")
            high = record.get("range_high_" + stat, "")

            result["covered_" + stat] = (
                int(n(low) <= actual_value <= n(high))
                if str(low).strip() and str(high).strip()
                else ""
            )

        results.append(result)

    # Results inherit the corrected Chicago dates.
    write_csv(RESULTS, RESULT_FIELDS, results)

    print()
    print("COURTSIDE ACCURACY RESULTS")
    print("-------------------------")
    print("Saved predictions:", len(history))
    print("New pregame predictions:", new_snapshots)
    print("Scored results:", len(results))
    print("Waiting for logs:", missing_logs)
    print("Incomplete box scores:", incomplete)
    print("Games not ready:", waiting)
    print("Invalid or late snapshots:", late + invalid)

    if results:
        print()
        print("MEAN ABSOLUTE ERROR")

        for stat in STATS:
            errors = [
                n(row.get("error_" + stat))
                for row in results
            ]

            print(
                f"{stat}: {sum(errors) / len(errors):.2f}"
            )


if __name__ == "__main__":
    main()
