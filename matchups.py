"""
Fantasy Football weekly matchups — one view across Sleeper and ESPN.

Proof-of-concept: pulls every league you're in on both platforms and prints
this week's matchups (your team vs. opponent, with live/current scores) all
in one place.

HOW TO USE
----------
1. Open config.txt (in this same folder) and fill in your details.
2. Run:  python matchups.py
3. To look at a different week:  python matchups.py --week 3

You only need to fill in the platforms you actually use. Leave the ESPN
section blank if you only want Sleeper, and vice versa.
"""

import argparse
import sys
from pathlib import Path

import requests

CONFIG_PATH = Path(__file__).parent / "config.txt"

SLEEPER_BASE = "https://api.sleeper.app/v1"
ESPN_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"


# --------------------------------------------------------------------------
# Config loading — reads simple key = value lines from config.txt
# --------------------------------------------------------------------------
def load_config():
    if not CONFIG_PATH.exists():
        write_config_template()
        print(f"\nI created a config file for you at:\n  {CONFIG_PATH}\n")
        print("Open it, fill in your details, then run this again.\n")
        sys.exit(0)

    cfg = {}
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        cfg[key.strip()] = value.strip()
    return cfg


def write_config_template():
    CONFIG_PATH.write_text(
        """# Fill in the sections for the platforms you use. Leave a value blank to skip it.

# ---- Season / week ----
season = 2025

# ---- SLEEPER ----
# Your Sleeper username (what you log in with). That's all Sleeper needs.
sleeper_username =

# ---- ESPN ----
# The season each ESPN league is in is set by "season" above.
# List your ESPN league IDs separated by commas. The league ID is the number
# in the URL when you're on your league page, e.g. .../leagues/123456789
espn_league_ids =

# For PRIVATE ESPN leagues (most of them), paste these two cookie values.
# Public leagues don't need them. See README for how to grab them (60 seconds).
espn_swid =
espn_s2 =
""",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Sleeper
# --------------------------------------------------------------------------
def sleeper_matchups(username, season, week):
    rows = []
    try:
        user = requests.get(f"{SLEEPER_BASE}/user/{username}", timeout=20).json()
        if not user or "user_id" not in user:
            print(f"  [Sleeper] Could not find user '{username}'. Check the username.")
            return rows
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

            # roster_id -> display name of the owner
            owner_by_roster = {}
            name_by_user = {
                u["user_id"]: (u.get("display_name") or u.get("username") or "?")
                for u in users
            }
            my_roster_id = None
            for r in rosters:
                owner_by_roster[r["roster_id"]] = name_by_user.get(
                    r.get("owner_id"), "Unknown"
                )
                if r.get("owner_id") == user_id:
                    my_roster_id = r["roster_id"]

            # Group matchup entries by matchup_id to pair opponents
            by_matchup = {}
            for m in matchups:
                by_matchup.setdefault(m.get("matchup_id"), []).append(m)

            for entries in by_matchup.values():
                roster_ids = [e["roster_id"] for e in entries]
                if my_roster_id not in roster_ids:
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
                        "my_score": round(me.get("points", 0) or 0, 1),
                        "opp_name": owner_by_roster.get(
                            opp["roster_id"], "TBD"
                        ) if opp else "BYE",
                        "opp_score": round(opp.get("points", 0) or 0, 1)
                        if opp else 0.0,
                    }
                )
    except Exception as e:
        print(f"  [Sleeper] Error: {e}")
    return rows


# --------------------------------------------------------------------------
# ESPN (unofficial read API)
# --------------------------------------------------------------------------
def espn_matchups(league_ids, season, week, swid, s2):
    rows = []
    cookies = {}
    if swid and s2:
        cookies = {"SWID": swid, "espn_s2": s2}

    for league_id in league_ids:
        league_id = league_id.strip()
        if not league_id:
            continue
        try:
            url = f"{ESPN_BASE}/{season}/segments/0/leagues/{league_id}"
            params = {"view": ["mMatchup", "mTeam", "mSettings"]}
            resp = requests.get(url, params=params, cookies=cookies, timeout=20)
            if resp.status_code == 401:
                print(
                    f"  [ESPN] League {league_id}: access denied — it's private, "
                    "so I need espn_swid and espn_s2 in config.txt."
                )
                continue
            if resp.status_code != 200:
                print(f"  [ESPN] League {league_id}: HTTP {resp.status_code}")
                continue
            data = resp.json()

            league_name = (
                data.get("settings", {}).get("name") or f"ESPN League {league_id}"
            )
            team_name = {}
            my_team_ids = set()
            for t in data.get("teams", []):
                name = (
                    t.get("name")
                    or f"{t.get('location','')} {t.get('nickname','')}".strip()
                    or f"Team {t.get('id')}"
                )
                team_name[t["id"]] = name
                # A team owned by the cookie's user is flagged as current user
                for owner in t.get("owners", []) or []:
                    if swid and owner and swid.strip("{}") in str(owner):
                        my_team_ids.add(t["id"])

            for game in data.get("schedule", []):
                if game.get("matchupPeriodId") != week:
                    continue
                home = game.get("home", {})
                away = game.get("away", {})
                home_id = home.get("teamId")
                away_id = away.get("teamId")

                # If we know which team is "mine", only show my matchups;
                # otherwise show all (public league without cookies).
                if my_team_ids and not (
                    home_id in my_team_ids or away_id in my_team_ids
                ):
                    continue

                mine_is_home = home_id in my_team_ids or not my_team_ids
                me_id, opp_id = (
                    (home_id, away_id) if mine_is_home else (away_id, home_id)
                )
                me_score = (home if mine_is_home else away).get(
                    "totalPoints", 0
                )
                opp_score = (away if mine_is_home else home).get(
                    "totalPoints", 0
                )
                rows.append(
                    {
                        "platform": "ESPN",
                        "league": league_name,
                        "my_name": team_name.get(me_id, "My Team"),
                        "my_score": round(me_score or 0, 1),
                        "opp_name": team_name.get(opp_id, "TBD"),
                        "opp_score": round(opp_score or 0, 1),
                    }
                )
        except Exception as e:
            print(f"  [ESPN] League {league_id}: Error: {e}")
    return rows


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def print_matchups(rows, week):
    print("\n" + "=" * 64)
    print(f"  YOUR WEEK {week} MATCHUPS — ALL LEAGUES, BOTH PLATFORMS")
    print("=" * 64)

    if not rows:
        print("\n  No matchups found. Check config.txt and the week number.\n")
        return

    for r in rows:
        lead = ""
        if r["my_score"] > r["opp_score"]:
            lead = "  (you're ahead)"
        elif r["my_score"] < r["opp_score"]:
            lead = "  (you're behind)"
        print(f"\n  [{r['platform']}] {r['league']}")
        print(f"     {r['my_name']:<24} {r['my_score']:>6}")
        print(f"     {r['opp_name']:<24} {r['opp_score']:>6}{lead}")

    print("\n" + "=" * 64)
    print(f"  {len(rows)} matchup(s) across {len(set(r['league'] for r in rows))} league(s)")
    print("=" * 64 + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=1, help="NFL week number")
    args = parser.parse_args()

    cfg = load_config()
    season = int(cfg.get("season", "2025") or "2025")
    week = args.week

    all_rows = []

    if cfg.get("sleeper_username"):
        print("Fetching from Sleeper...")
        all_rows += sleeper_matchups(cfg["sleeper_username"], season, week)

    if cfg.get("espn_league_ids"):
        print("Fetching from ESPN...")
        all_rows += espn_matchups(
            cfg["espn_league_ids"].split(","),
            season,
            week,
            cfg.get("espn_swid", ""),
            cfg.get("espn_s2", ""),
        )

    print_matchups(all_rows, week)


if __name__ == "__main__":
    main()
