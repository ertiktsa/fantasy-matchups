"""
Shared data layer for the FF dashboard.

Pulls weekly matchups from Sleeper and ESPN and returns them as plain
dictionaries, so both the text tool (matchups.py) and the website (app.py)
use the exact same logic.
"""

import os
from pathlib import Path
import requests

CONFIG_PATH = Path(__file__).parent / "config.txt"

# Keys the app understands. On Render these come from environment variables;
# on your laptop they come from config.txt.
CONFIG_KEYS = [
    "login_user", "login_password", "season",
    "sleeper_username", "espn_league_ids", "espn_swid", "espn_s2",
]

SLEEPER_BASE = "https://api.sleeper.app/v1"
ESPN_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"


def load_config():
    """Load settings. Environment variables win (that's how Render stores
    secrets); anything not set there falls back to the local config.txt."""
    cfg = {}
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip()

    # Environment variables override the file (uppercased key names).
    for key in CONFIG_KEYS:
        env_val = os.environ.get(key.upper())
        if env_val is not None and env_val != "":
            cfg[key] = env_val
    return cfg


def _num(v):
    try:
        return round(float(v or 0), 1)
    except (TypeError, ValueError):
        return 0.0


def sleeper_matchups(username, season, week):
    rows, errors = [], []
    try:
        user = requests.get(f"{SLEEPER_BASE}/user/{username}", timeout=20).json()
        if not user or "user_id" not in user:
            errors.append(f"Sleeper: user '{username}' not found.")
            return rows, errors
        user_id = user["user_id"]
        leagues = requests.get(
            f"{SLEEPER_BASE}/user/{user_id}/leagues/nfl/{season}", timeout=20
        ).json() or []

        for lg in leagues:
            league_id = lg["league_id"]
            league_name = lg.get("name", "Sleeper League")
            users = requests.get(
                f"{SLEEPER_BASE}/league/{league_id}/users", timeout=20
            ).json() or []
            rosters = requests.get(
                f"{SLEEPER_BASE}/league/{league_id}/rosters", timeout=20
            ).json() or []
            matchups = requests.get(
                f"{SLEEPER_BASE}/league/{league_id}/matchups/{week}", timeout=20
            ).json() or []

            name_by_user = {
                u["user_id"]: (u.get("display_name") or u.get("username") or "?")
                for u in users
            }
            owner_by_roster, my_roster_id = {}, None
            for r in rosters:
                owner_by_roster[r["roster_id"]] = name_by_user.get(
                    r.get("owner_id"), "Unknown"
                )
                if r.get("owner_id") == user_id:
                    my_roster_id = r["roster_id"]

            by_matchup = {}
            for m in matchups:
                by_matchup.setdefault(m.get("matchup_id"), []).append(m)

            for entries in by_matchup.values():
                ids = [e["roster_id"] for e in entries]
                if my_roster_id not in ids:
                    continue
                me = next(e for e in entries if e["roster_id"] == my_roster_id)
                opp = next(
                    (e for e in entries if e["roster_id"] != my_roster_id), None
                )
                rows.append(
                    {
                        "platform": "Sleeper",
                        "league": league_name,
                        "my_name": owner_by_roster.get(my_roster_id, "Me"),
                        "my_score": _num(me.get("points")),
                        "opp_name": owner_by_roster.get(opp["roster_id"], "TBD")
                        if opp else "BYE",
                        "opp_score": _num(opp.get("points")) if opp else 0.0,
                    }
                )
    except Exception as e:
        errors.append(f"Sleeper error: {e}")
    return rows, errors


def espn_matchups(league_ids, season, week, swid, s2):
    rows, errors = [], []
    cookies = {"SWID": swid, "espn_s2": s2} if swid and s2 else {}

    for league_id in league_ids:
        league_id = league_id.strip()
        if not league_id:
            continue
        try:
            url = f"{ESPN_BASE}/{season}/segments/0/leagues/{league_id}"
            resp = requests.get(
                url,
                params={"view": ["mMatchup", "mTeam", "mSettings"]},
                cookies=cookies,
                timeout=20,
            )
            if resp.status_code == 401:
                errors.append(
                    f"ESPN league {league_id}: access denied — private league "
                    "needs valid SWID/espn_s2 cookies (they may have expired)."
                )
                continue
            if resp.status_code != 200:
                errors.append(f"ESPN league {league_id}: HTTP {resp.status_code}")
                continue
            data = resp.json()

            league_name = (
                data.get("settings", {}).get("name") or f"ESPN League {league_id}"
            )
            team_name, my_team_ids = {}, set()
            for t in data.get("teams", []):
                name = (
                    t.get("name")
                    or f"{t.get('location','')} {t.get('nickname','')}".strip()
                    or f"Team {t.get('id')}"
                )
                team_name[t["id"]] = name
                for owner in t.get("owners", []) or []:
                    if swid and owner and swid.strip("{}") in str(owner):
                        my_team_ids.add(t["id"])

            for game in data.get("schedule", []):
                if game.get("matchupPeriodId") != week:
                    continue
                home, away = game.get("home", {}), game.get("away", {})
                home_id, away_id = home.get("teamId"), away.get("teamId")
                if my_team_ids and not (
                    home_id in my_team_ids or away_id in my_team_ids
                ):
                    continue
                mine_is_home = home_id in my_team_ids or not my_team_ids
                me_id, opp_id = (
                    (home_id, away_id) if mine_is_home else (away_id, home_id)
                )
                me_score = (home if mine_is_home else away).get("totalPoints", 0)
                opp_score = (away if mine_is_home else home).get("totalPoints", 0)
                rows.append(
                    {
                        "platform": "ESPN",
                        "league": league_name,
                        "my_name": team_name.get(me_id, "My Team"),
                        "my_score": _num(me_score),
                        "opp_name": team_name.get(opp_id, "TBD"),
                        "opp_score": _num(opp_score),
                    }
                )
        except Exception as e:
            errors.append(f"ESPN league {league_id}: {e}")
    return rows, errors


def get_all_matchups(week):
    """Return (rows, errors, season) using values from config.txt."""
    cfg = load_config()
    season = int(cfg.get("season", "2025") or "2025")
    rows, errors = [], []

    if cfg.get("sleeper_username"):
        r, e = sleeper_matchups(cfg["sleeper_username"], season, week)
        rows += r
        errors += e
    if cfg.get("espn_league_ids"):
        r, e = espn_matchups(
            cfg["espn_league_ids"].split(","),
            season,
            week,
            cfg.get("espn_swid", ""),
            cfg.get("espn_s2", ""),
        )
        rows += r
        errors += e

    for row in rows:
        if row["my_score"] > row["opp_score"]:
            row["status"] = "winning"
        elif row["my_score"] < row["opp_score"]:
            row["status"] = "losing"
        else:
            row["status"] = "tied"
    return rows, errors, season
