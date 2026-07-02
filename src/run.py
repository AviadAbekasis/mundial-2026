# -*- coding: utf-8 -*-
"""Orchestrator: fetch live data -> Monte-Carlo simulate -> build dashboard.

Usage:  python src/run.py [num_simulations]
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data          # noqa: E402
import simulate            # noqa: E402
import build_dashboard     # noqa: E402
import analyst             # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def main(n=50000, force_analysis=False):
    t0 = time.time()
    print("=" * 56)
    print("STEP 1/4  Fetching live data (ESPN + eloratings) ...")
    state = fetch_data.main()

    print("=" * 56)
    print(f"STEP 2/4  Simulating {n:,} tournaments ...")
    sim = simulate.simulate(state, n=n, progress=True)
    with open(os.path.join(DATA_DIR, "sim.json"), "w", encoding="utf-8") as f:
        json.dump(sim, f, ensure_ascii=False, indent=1)

    print("=" * 56)
    print("STEP 3/4  Generating Gemini analyses (today + tomorrow) ...")
    key_ok = False
    try:
        analyst.get_key()
        key_ok = True
    except Exception as ex:
        print(f"  (no Gemini key — skipping analyses: {ex})")
    if key_ok:
        done, failed = analyst.generate_upcoming(state, days=2, force=force_analysis)
        print(f"  analyses: {len(done)} new, {len(failed)} failed")
        # if a key IS present but EVERY analysis failed, it's systemic (bad key / BOM /
        # quota) — fail the build loudly instead of silently deploying without analyses.
        if failed and not done:
            raise RuntimeError(
                f"ALL {len(failed)} analyses failed — systemic issue. Failing the build "
                f"so it's visible rather than silently shipping without analysis.")

    print("=" * 56)
    print("STEP 4/4  Building dashboard ...")
    path = build_dashboard.render(state, sim)

    print("=" * 56)
    champs = sorted(sim["teams"].items(), key=lambda kv: kv[1]["p_champion"], reverse=True)
    print("Top title chances:")
    for ab, d in champs[:5]:
        print(f"   {state['teams'][ab]['name_he']:12} {d['p_champion']*100:4.1f}%")
    print(f"\nDone in {time.time()-t0:.1f}s")
    print(f"Dashboard: {path}")
    return path


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    n = next((int(a) for a in sys.argv[1:] if a.isdigit()), 50000)
    main(n, force_analysis="--force" in sys.argv)
