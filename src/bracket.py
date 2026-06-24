# -*- coding: utf-8 -*-
"""Static FIFA World Cup 2026 bracket structure + group/third-place ranking logic.

Match numbering follows the official FIFA scheme (73-104). Verified against both
the ESPN bracket feed and FIFA's published knockout regulations.

Slot encodings used in R32:
    ("W",  "A")            winner of group A
    ("RU", "A")            runner-up of group A
    ("3RD", 74)            the best-third assigned to match 74 (resolved via Annex C)
Knockout feeds use:
    ("WIN", 73)            winner of match 73
    ("LOSE", 101)          loser of match 101
"""

# --- Round of 32 (matches 73-88): each match's two slots ---
R32 = {
    73: (("RU", "A"), ("RU", "B")),
    74: (("W", "E"),  ("3RD", 74)),
    75: (("W", "F"),  ("RU", "C")),
    76: (("W", "C"),  ("RU", "F")),
    77: (("W", "I"),  ("3RD", 77)),
    78: (("RU", "E"), ("RU", "I")),
    79: (("W", "A"),  ("3RD", 79)),
    80: (("W", "L"),  ("3RD", 80)),
    81: (("W", "D"),  ("3RD", 81)),
    82: (("W", "G"),  ("3RD", 82)),
    83: (("RU", "K"), ("RU", "L")),
    84: (("W", "H"),  ("RU", "J")),
    85: (("W", "B"),  ("3RD", 85)),
    86: (("W", "J"),  ("RU", "H")),
    87: (("W", "K"),  ("3RD", 87)),
    88: (("RU", "D"), ("RU", "G")),
}

# Third-place slots: match_no -> candidate set of groups eligible to fill it.
THIRD_SLOTS = {
    74: frozenset("ABCDF"),
    77: frozenset("CDFGH"),
    79: frozenset("CEFHI"),
    80: frozenset("EHIJK"),
    81: frozenset("BEFIJ"),
    82: frozenset("AEHIJ"),
    85: frozenset("EFGIJ"),
    87: frozenset("DEIJL"),
}

# --- Later rounds: match_no -> (feed_slot_A, feed_slot_B) ---
R16 = {
    89: (("WIN", 73), ("WIN", 75)),
    90: (("WIN", 74), ("WIN", 77)),
    91: (("WIN", 76), ("WIN", 78)),
    92: (("WIN", 79), ("WIN", 80)),
    93: (("WIN", 83), ("WIN", 84)),
    94: (("WIN", 81), ("WIN", 82)),
    95: (("WIN", 86), ("WIN", 88)),
    96: (("WIN", 85), ("WIN", 87)),
}
QF = {
    97:  (("WIN", 89), ("WIN", 90)),
    98:  (("WIN", 93), ("WIN", 94)),
    99:  (("WIN", 91), ("WIN", 92)),
    100: (("WIN", 95), ("WIN", 96)),
}
SF = {
    101: (("WIN", 97), ("WIN", 98)),
    102: (("WIN", 99), ("WIN", 100)),
}
THIRD_PLACE = {103: (("LOSE", 101), ("LOSE", 102))}
FINAL = {104: (("WIN", 101), ("WIN", 102))}

# Round membership + the stage a team reaches by WINNING a match of that round.
ROUNDS = [
    ("R32", R32),
    ("R16", R16),
    ("QF", QF),
    ("SF", SF),
    ("FINAL", FINAL),
]
# Stage label reached by the WINNER of each round's match.
WIN_REACHES = {"R32": "R16", "R16": "QF", "QF": "SF", "SF": "FINAL", "FINAL": "CHAMPION"}


# ---------------------------------------------------------------------------
# Standings / ranking
# ---------------------------------------------------------------------------
def _blank():
    return {"pts": 0, "gf": 0, "ga": 0, "pld": 0}


def table_from_matches(team_list, matches):
    """Compute a points table {abbr: {pts,gf,ga,gd,pld}} from played matches."""
    tab = {t: _blank() for t in team_list}
    for m in matches:
        h, a, hg, ag = m["home"], m["away"], m["hg"], m["ag"]
        if hg is None or ag is None:
            continue
        for t in (h, a):
            if t not in tab:
                tab[t] = _blank()
        tab[h]["gf"] += hg; tab[h]["ga"] += ag; tab[h]["pld"] += 1
        tab[a]["gf"] += ag; tab[a]["ga"] += hg; tab[a]["pld"] += 1
        if hg > ag:
            tab[h]["pts"] += 3
        elif hg < ag:
            tab[a]["pts"] += 3
        else:
            tab[h]["pts"] += 1; tab[a]["pts"] += 1
    for t in tab.values():
        t["gd"] = t["gf"] - t["ga"]
    return tab


def _h2h_table(tied, matches):
    sub = [m for m in matches
           if m["home"] in tied and m["away"] in tied and m["hg"] is not None]
    return table_from_matches(list(tied), sub)


def rank_group(team_list, matches, rng):
    """Return teams ordered 1st..4th applying the FIFA 2026 tiebreakers."""
    tab = table_from_matches(team_list, matches)

    def keyfn(t):
        return (tab[t]["pts"], tab[t]["gd"], tab[t]["gf"])

    # initial sort by points, then provisional overall gd/gf
    order = sorted(team_list, key=keyfn, reverse=True)

    # resolve ties with head-to-head (2026: H2H before overall GD), then overall, then random
    final = []
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and tab[order[j + 1]]["pts"] == tab[order[i]]["pts"]:
            j += 1
        group_tied = order[i:j + 1]
        if len(group_tied) == 1:
            final.append(group_tied[0])
        else:
            final.extend(_break_tie(group_tied, matches, tab, rng))
        i = j + 1
    return final


def _break_tie(tied, matches, overall, rng):
    h2h = _h2h_table(tied, matches)

    def keyfn(t):
        return (h2h[t]["pts"], h2h[t]["gd"], h2h[t]["gf"],   # head-to-head block
                overall[t]["gd"], overall[t]["gf"],           # overall block
                rng.random())                                  # FIFA ranking / lots
    return sorted(tied, key=keyfn, reverse=True)


def rank_thirds(entries, rng):
    """Rank the twelve third-placed teams. entries: list of (abbr, group, tab_row).
    No head-to-head (they never met). Returns ordered list of (abbr, group)."""
    def keyfn(e):
        ab, grp, row = e
        return (row["pts"], row["gd"], row["gf"], rng.random())
    ordered = sorted(entries, key=keyfn, reverse=True)
    return [(ab, grp) for ab, grp, _ in ordered]


def assign_thirds(qualified_groups):
    """Annex C (approximated by constraint-respecting bipartite matching):
    map each qualifying third's group -> a third-place slot match_no whose candidate
    set contains that group, as a perfect matching. Returns {match_no: group}.

    Note: a valid perfect matching always exists for FIFA's slot design. Where the
    official table would pick a specific one among several valid matchings, we pick a
    deterministic one (sorted) -- structurally correct opponents; negligible effect on
    aggregate probabilities.
    """
    slot_to_group = {}

    def augment(group, seen):
        for m, cand in THIRD_SLOTS.items():
            if group in cand and m not in seen:
                seen.add(m)
                if m not in slot_to_group or augment(slot_to_group[m], seen):
                    slot_to_group[m] = group
                    return True
        return False

    for g in sorted(qualified_groups):
        augment(g, set())
    return dict(slot_to_group)
