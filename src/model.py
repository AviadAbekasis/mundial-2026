# -*- coding: utf-8 -*-
"""Match model: Elo -> expected goals (lambda) -> Dixon-Coles scorelines, plus
knockout resolution (extra time + penalties).

Calibration (from the international-football methodology research):
  - Win expectancy:  We = 1 / (1 + 10^(-dr/400))
  - Elo->goals:      neutral-venue quartic fit ("Football rankings 2020")
  - Scorelines:      independent Poisson + Dixon-Coles low-score correction (rho)
Monte-Carlo sampling uses independent Poisson (fast); the DC matrix is used for the
displayed 1X2 / scoreline probabilities. This split is a standard, documented tradeoff.
"""
import math

RHO = -0.13          # Dixon-Coles low-score correction
HOST_ADV = 70        # Elo bump for a host nation playing at home (group stage)
MAXGOALS = 8         # score matrix dimension for displayed probabilities
ET_SCALE = 1.0 / 3   # extra time ~30 min vs 90
PEN_BLEND = 0.5      # shootout: blend 50% coin-flip with 50% Elo win-expectancy


def win_expectancy(elo_h, elo_a, adv_h=0.0, adv_a=0.0):
    dr = (elo_h + adv_h) - (elo_a + adv_a)
    return 1.0 / (1.0 + 10 ** (-dr / 400.0))


def _lambda_neutral(w):
    """Expected goals for a team with neutral-venue win-expectancy w."""
    if w <= 0.9:
        return (3.90388 * w**4 - 0.58486 * w**3 - 2.98315 * w**2
                + 3.13160 * w + 0.33193)
    d = w - 0.9
    return (308097.45501 * d**4 - 42803.04696 * d**3 + 2116.35304 * d**2
            - 9.61869 * d + 2.86899)


def expected_goals(elo_h, elo_a, adv_h=0.0, adv_a=0.0):
    """Return (lambda_home, lambda_away, We_home)."""
    we = win_expectancy(elo_h, elo_a, adv_h, adv_a)
    lh = max(0.05, _lambda_neutral(we))
    la = max(0.05, _lambda_neutral(1.0 - we))
    return lh, la, we


# --- Displayed probabilities (Dixon-Coles matrix) ---
def _pois_pmf(lam, k):
    return math.exp(-lam) * lam**k / math.factorial(k)


def _tau(a, b, lh, la, rho):
    if a == 0 and b == 0:
        return 1.0 - lh * la * rho
    if a == 0 and b == 1:
        return 1.0 + lh * rho
    if a == 1 and b == 0:
        return 1.0 + la * rho
    if a == 1 and b == 1:
        return 1.0 - rho
    return 1.0


def dc_matrix(lh, la, rho=RHO, n=MAXGOALS):
    ph = [_pois_pmf(lh, k) for k in range(n + 1)]
    pa = [_pois_pmf(la, k) for k in range(n + 1)]
    m = [[ph[a] * pa[b] * _tau(a, b, lh, la, rho) for b in range(n + 1)]
         for a in range(n + 1)]
    s = sum(sum(row) for row in m)
    return [[v / s for v in row] for row in m]


def match_probs(lh, la, rho=RHO):
    """Return (p_home, p_draw, p_away) and most-likely scoreline from the DC matrix."""
    m = dc_matrix(lh, la, rho)
    ph = pd = pa = 0.0
    best, best_p = (0, 0), -1.0
    for a, row in enumerate(m):
        for b, v in enumerate(row):
            if a > b:
                ph += v
            elif a == b:
                pd += v
            else:
                pa += v
            if v > best_p:
                best_p, best = v, (a, b)
    return ph, pd, pa, best


# --- Monte-Carlo sampling (independent Poisson, Knuth) ---
def surprise_index(pH, pD, pA, chaos=0.0):
    """0-100 'upset-prone' index: blends the match's unpredictability (chance the
    model favourite fails to win) with how upset-heavy the tournament has been."""
    p_fav = max(pH, pA)
    raw = 0.75 * (1.0 - p_fav) + 0.25 * chaos
    return int(round(max(1.0, min(99.0, raw * 100))))


def surprise_level(si):
    if si >= 55:
        return "גבוה", "hi"
    if si >= 35:
        return "בינוני", "mid"
    return "נמוך", "lo"


def sample_goals(lam, rnd):
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rnd()
        if p <= L:
            return k
        k += 1


def sample_match(lh, la, rnd):
    return sample_goals(lh, rnd), sample_goals(la, rnd)


def sample_knockout(lh, la, we_home, rnd):
    """Return 'h' or 'a' for the winner (90' -> ET -> penalties)."""
    gh, ga = sample_match(lh, la, rnd)
    if gh != ga:
        return "h" if gh > ga else "a"
    # extra time
    eh, ea = sample_match(lh * ET_SCALE, la * ET_SCALE, rnd)
    if eh != ea:
        return "h" if eh > ea else "a"
    # penalties: mild Elo tilt
    p_home = (1 - PEN_BLEND) * 0.5 + PEN_BLEND * we_home
    return "h" if rnd() < p_home else "a"
