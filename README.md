# Fantasy Football — All My Matchups in One Place (Proof-of-Concept)

This is a small tool that pulls your leagues from **Sleeper** and **ESPN** and
prints this week's matchups all together, so you don't have to bounce between
apps.

This first version prints to the screen (text). Once you confirm the data looks
right, we turn it into an actual webpage.

## One-time setup (about 2 minutes)

### 1. Open the config file
There's a file called `config.txt` in this folder. Open it in Notepad and fill
in your details. You only fill in the platforms you use.

### 2. Sleeper (easy)
Just put your Sleeper username after `sleeper_username =`. That's it — Sleeper
needs nothing else. It will automatically find every Sleeper league you're in.

### 3. ESPN
- Put the season year after `season =` (e.g. `2025`).
- Find each ESPN league's ID: open the league in your browser and look at the
  web address. The long number in it is the league ID
  (e.g. `.../leagues/123456789` → `123456789`). List them after
  `espn_league_ids =`, separated by commas.

**If your ESPN leagues are private** (most are), you need two values from your
browser so ESPN knows it's you. Here's how to grab them once:

1. Log in to ESPN Fantasy in Chrome.
2. Press `F12` to open the developer tools, click the **Application** tab.
3. On the left, expand **Cookies** → click `https://fantasy.espn.com`.
4. Find the row named **SWID** — copy its value into `espn_swid =` in config.txt
   (include the curly braces).
5. Find the row named **espn_s2** — copy its (long) value into `espn_s2 =`.

That's the whole setup. These two values expire every so often; when the tool
stops finding your ESPN leagues, just re-copy them.

## Run it

Open a terminal in this folder and run:

```
python matchups.py --week 1
```

Change the number to see a different week. It prints every matchup from both
platforms in one list, with scores and who's ahead.

## Notes
- Sleeper's API is official and free. ESPN's read API is unofficial but is the
  standard tool people rely on; it can occasionally change.
- Nothing is shared anywhere — this runs on your machine and only reads your
  own leagues.
