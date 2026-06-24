# -*- coding: utf-8 -*-
"""Fetch & normalize all live data into data/state.json.

Sources (all free, no API key):
  - eloratings.net/2026_World_Cup.tsv    -> current Elo per team
  - ESPN hidden API (fifa.world)         -> groups, fixtures, live results
"""
import io
import json
import os
import sys
import datetime as dt
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from teams import ELO_CODE_TO_ABBR, HE_NAME, he  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WC2026Tool/0.1"}
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
ESPN_STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings?season=2026"
ELO_URL = "https://www.eloratings.net/2026_World_Cup.tsv"


def fetch_elo():
    r = requests.get(ELO_URL, headers=HEADERS, timeout=30)
    r.encoding = "utf-8"
    out = {}
    for ln in r.text.splitlines():
        c = ln.split("\t")
        if len(c) > 3 and c[2] in ELO_CODE_TO_ABBR:
            out[ELO_CODE_TO_ABBR[c[2]]] = int(c[3])
    return out


def fetch_groups():
    """Return {abbr: group_letter} and ordered group->[abbr]."""
    j = requests.get(ESPN_STANDINGS, headers=HEADERS, timeout=30).json()
    team_group, groups = {}, {}
    for ch in j.get("children", []):
        letter = ch["name"].replace("Group ", "").strip()
        members = []
        for e in ch["standings"]["entries"]:
            ab = e["team"]["abbreviation"]
            team_group[ab] = letter
            members.append(ab)
        groups[letter] = members
    return team_group, groups


def fetch_events():
    url = f"{ESPN}/scoreboard?dates=20260611-20260719&limit=400"
    return requests.get(url, headers=HEADERS, timeout=40).json().get("events", [])


def parse_events(events, team_group, logos):
    """Split into group fixtures (with results) and raw knockout events.
    Also harvest team logo URLs into the `logos` dict."""
    group_fx, ko_events = [], []
    for ev in events:
        comp = ev["competitions"][0]
        st = comp["status"]["type"]
        completed = bool(st.get("completed"))
        cs = comp["competitors"]
        home = next(c for c in cs if c["homeAway"] == "home")
        away = next(c for c in cs if c["homeAway"] == "away")
        h_ab, a_ab = home["team"]["abbreviation"], away["team"]["abbreviation"]
        for c in (home, away):
            ab = c["team"]["abbreviation"]
            if ab in team_group and c["team"].get("logo"):
                logos[ab] = c["team"]["logo"]
        rec = {
            "id": ev["id"],
            "date": ev["date"],
            "home_name": home["team"]["displayName"],
            "away_name": away["team"]["displayName"],
            "home": h_ab, "away": a_ab,
            "completed": completed,
            "state": st.get("state"),  # pre / in / post
            "status": st.get("description"),
        }
        if completed:
            try:
                rec["hg"] = int(home.get("score"))
                rec["ag"] = int(away.get("score"))
            except (TypeError, ValueError):
                rec["hg"] = rec["ag"] = None
        # group match iff both sides are real group teams in the SAME group
        if h_ab in team_group and a_ab in team_group and team_group[h_ab] == team_group[a_ab]:
            rec["group"] = team_group[h_ab]
            group_fx.append(rec)
        else:
            ko_events.append(rec)
    return group_fx, ko_events


def main():
    print("Fetching Elo ...")
    elo = fetch_elo()
    print(f"  {len(elo)} teams")
    print("Fetching groups/standings ...")
    team_group, groups = fetch_groups()
    print(f"  {len(team_group)} teams in {len(groups)} groups")
    print("Fetching events ...")
    events = fetch_events()
    print(f"  {len(events)} events")
    logos = {}
    group_fx, ko_events = parse_events(events, team_group, logos)
    done = sum(1 for f in group_fx if f["completed"])
    print(f"  group fixtures: {len(group_fx)} ({done} completed)")
    print(f"  knockout events: {len(ko_events)}")

    teams = {}
    for ab, g in team_group.items():
        teams[ab] = {
            "abbr": ab, "group": g,
            "name_he": HE_NAME.get(ab, ab),
            "elo": elo.get(ab),
            "logo": logos.get(ab),
        }
    missing_elo = [ab for ab, t in teams.items() if t["elo"] is None]
    if missing_elo:
        print("  WARNING missing Elo for:", missing_elo)

    state = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "teams": teams,
        "groups": groups,
        "group_fixtures": group_fx,
        "knockout_events": ko_events,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "state.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"Wrote {path}")
    return state


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
