# -*- coding: utf-8 -*-
"""Monte-Carlo tournament simulation.

Conditions on real results already played (they are fixed, never re-sampled);
simulates only the remaining matches. Aggregates thousands of replays into
advancement / round / title probabilities per team.
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket as B            # noqa: E402
import model as M             # noqa: E402
from teams import HOSTS       # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# furthest-stage levels
LEVELS = {"R32": 1, "R16": 2, "QF": 3, "SF": 4, "FINAL": 5, "CHAMPION": 6}
_eg_cache = {}


def eg(elo_h, elo_a, adv_h=0.0, adv_a=0.0):
    key = (elo_h, elo_a, adv_h, adv_a)
    v = _eg_cache.get(key)
    if v is None:
        v = M.expected_goals(elo_h, elo_a, adv_h, adv_a)
        _eg_cache[key] = v
    return v


def prepare(state):
    """Precompute per-group completed/unplayed fixtures (with lambdas)."""
    teams = state["teams"]
    elo = {a: t["elo"] for a, t in teams.items()}
    groups = state["groups"]
    by_group = {g: {"members": groups[g], "done": [], "todo": []} for g in groups}
    for fx in state["group_fixtures"]:
        g = fx["group"]
        if fx["completed"] and fx.get("hg") is not None:
            by_group[g]["done"].append(
                {"home": fx["home"], "away": fx["away"], "hg": fx["hg"], "ag": fx["ag"]})
        else:
            h, a = fx["home"], fx["away"]
            adv_h = M.HOST_ADV if h in HOSTS else 0.0
            adv_a = M.HOST_ADV if a in HOSTS else 0.0
            lh, la, _ = eg(elo[h], elo[a], adv_h, adv_a)
            by_group[g]["todo"].append({"home": h, "away": a, "lh": lh, "la": la})
    return elo, by_group


def simulate(state, n=50000, seed=42, progress=True):
    elo, by_group = prepare(state)
    teams = list(state["teams"].keys())
    rng = random.Random(seed)
    rnd = rng.random
    sg = M.sample_goals
    ko = M.sample_knockout

    # counters
    reach = {t: {lv: 0 for lv in LEVELS} for t in teams}
    win_group = {t: 0 for t in teams}
    runner = {t: 0 for t in teams}
    third_q = {t: 0 for t in teams}
    adv = {t: 0 for t in teams}

    all_rounds = [("R32", B.R32), ("R16", B.R16), ("QF", B.QF),
                  ("SF", B.SF), ("FINAL", B.FINAL)]

    t0 = time.time()
    for s in range(n):
        # ---- group stage ----
        rankings = {}          # group -> [1st,2nd,3rd,4th]
        third_rows = []        # (abbr, group, row)
        for g, gd in by_group.items():
            matches = gd["done"]
            if gd["todo"]:
                matches = gd["done"] + [
                    {"home": m["home"], "away": m["away"],
                     "hg": sg(m["lh"], rnd), "ag": sg(m["la"], rnd)} for m in gd["todo"]]
            order = B.rank_group(gd["members"], matches, rng)
            rankings[g] = order
            tab = B.table_from_matches(gd["members"], matches)
            win_group[order[0]] += 1
            runner[order[1]] += 1
            third_rows.append((order[2], g, tab[order[2]]))

        # ---- best 8 thirds ----
        ranked_thirds = B.rank_thirds(third_rows, rng)
        qualifying = ranked_thirds[:8]
        qual_groups = {g for _, g in qualifying}
        for ab, _g in qualifying:
            third_q[ab] += 1
        third_assign = B.assign_thirds(qual_groups)   # match_no -> group

        # teams that advanced from groups
        for g, order in rankings.items():
            adv[order[0]] += 1
            adv[order[1]] += 1
        for ab, _g in qualifying:
            adv[ab] += 1

        # ---- knockouts ----
        res = {}   # match_no -> {"w":abbr,"l":abbr}

        def resolve(slot):
            typ, ref = slot
            if typ == "W":
                return rankings[ref][0]
            if typ == "RU":
                return rankings[ref][1]
            if typ == "3RD":
                return rankings[third_assign[ref]][2]
            if typ == "WIN":
                return res[ref]["w"]
            return res[ref]["l"]

        for rname, rmatches in all_rounds:
            stage = B.WIN_REACHES[rname]      # stage reached by winning this round
            for mno, (sa, sb) in rmatches.items():
                h, a = resolve(sa), resolve(sb)
                lh, la, we = eg(elo[h], elo[a])
                w = h if ko(lh, la, we, rnd) == "h" else a
                l = a if w == h else h
                res[mno] = {"w": w, "l": l}
                reach[w][stage] += 1

        if progress and (s + 1) % 10000 == 0:
            print(f"  {s+1}/{n}  ({time.time()-t0:.1f}s)")

    # also: everyone who advanced reached at least R32
    for t in teams:
        reach[t]["R32"] = adv[t]

    out = {"n": n, "seed": seed, "teams": {}, "groups": {}}
    for t in teams:
        out["teams"][t] = {
            "elo": elo[t],
            "group": state["teams"][t]["group"],
            "p_adv": adv[t] / n,
            "p_win_group": win_group[t] / n,
            "p_runner": runner[t] / n,
            "p_third_q": third_q[t] / n,
            "p_r16": reach[t]["R16"] / n,
            "p_qf": reach[t]["QF"] / n,
            "p_sf": reach[t]["SF"] / n,
            "p_final": reach[t]["FINAL"] / n,
            "p_champion": reach[t]["CHAMPION"] / n,
        }
    for g, members in state["groups"].items():
        rows = sorted(
            [{"abbr": m, **{k: out["teams"][m][k] for k in
              ("p_win_group", "p_runner", "p_adv", "p_champion")}} for m in members],
            key=lambda r: r["p_adv"], reverse=True)
        out["groups"][g] = rows
    out["elapsed_s"] = round(time.time() - t0, 1)
    return out


_LVL_NAMES = {v: k for k, v in LEVELS.items()}


def _lvl_name(lvl):
    return _LVL_NAMES[lvl]


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    with open(os.path.join(DATA_DIR, "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    print(f"Simulating {n} tournaments ...")
    out = simulate(state, n=n)
    with open(os.path.join(DATA_DIR, "sim.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"Done in {out['elapsed_s']}s")
    champs = sorted(out["teams"].items(), key=lambda kv: kv[1]["p_champion"], reverse=True)
    print("\nTop title chances:")
    for ab, d in champs[:14]:
        print(f"  {state['teams'][ab]['name_he']:14} {d['p_champion']*100:5.1f}%  "
              f"(adv {d['p_adv']*100:4.0f}%  SF {d['p_sf']*100:4.0f}%)")
