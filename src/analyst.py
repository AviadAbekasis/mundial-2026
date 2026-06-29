# -*- coding: utf-8 -*-
"""Gemini analyst layer — generates the per-match textual analysis JSON.

For each match it asks Gemini (with Google Search grounding) to research the game
and return a structured analysis (lineups, tactics, form, H2H, Opta prediction,
betting recommendations, key players, verdict) in the schema build_dashboard expects.

The API key is read from the GEMINI_API_KEY env var, or from a local '.gemini_key'
file (gitignored). The raw key never appears in code or in the chat.
"""
import json
import os
import re
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket as B          # noqa: E402
import model as M            # noqa: E402
import build_dashboard as BD  # noqa: E402  (for tournament_chaos)
from teams import HE_NAME, HOSTS, he  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
ANALYSIS_DIR = os.path.join(DATA_DIR, "analysis")
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def get_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    path = os.path.join(ROOT, ".gemini_key")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "PASTE_YOUR" not in line:
                    return line
    raise RuntimeError(
        "מפתח Gemini לא נמצא. הגדר משתנה סביבה GEMINI_API_KEY, "
        "או הדבק את המפתח בקובץ .gemini_key בתיקיית הפרויקט.")


# ---------- match facts (grounding context) ----------
def _group_standings_text(state, group):
    byg = [f for f in state["group_fixtures"]
           if f["group"] == group and f["completed"] and f.get("hg") is not None]
    members = state["groups"][group]
    tab = B.table_from_matches(members, byg)
    rows = sorted(members, key=lambda t: (tab[t]["pts"], tab[t]["gd"], tab[t]["gf"]), reverse=True)
    parts = [f"{HE_NAME.get(t, t)} {tab[t]['pts']}נק' (משחקים {tab[t]['pld']}, "
             f"הפרש {tab[t]['gd']:+d})" for t in rows]
    return " | ".join(parts)


def match_facts(state, fx):
    h, a = fx["home"], fx["away"]
    elo = state["teams"]
    grp = fx.get("group")
    adv_h = M.HOST_ADV if (h in HOSTS and grp) else 0.0
    adv_a = M.HOST_ADV if (a in HOSTS and grp) else 0.0
    lh, la, we = M.expected_goals(elo[h]["elo"], elo[a]["elo"], adv_h, adv_a)
    pH, pD, pA, score = M.match_probs(lh, la)
    t = pH + pD + pA
    chaos = BD.tournament_chaos(state)["rate"]
    si = M.surprise_index(pH/t, pD/t, pA/t, chaos)
    stage = ("בית " + grp) if grp else BD.round_label(fx["date"])
    standings = (_group_standings_text(state, grp) if grp else
                 "שלב נוקאאוט — המנצח עולה, המפסיד מודח. אין טבלה; הכל לפי היריבה (כולל הארכה ופנדלים).")
    return {
        "surprise_index": si, "surprise_level": M.surprise_level(si)[0],
        "chaos_pct": round(chaos*100),
        "id": str(fx["id"]),
        "home": h, "away": a, "stage": stage, "is_knockout": not bool(grp),
        "home_en": fx.get("home_name", h), "away_en": fx.get("away_name", a),
        "home_he": HE_NAME.get(h, h), "away_he": HE_NAME.get(a, a),
        "group": grp or "", "date": fx["date"],
        "elo_home": elo[h]["elo"], "elo_away": elo[a]["elo"],
        "standings": standings,
        "model_lh": round(lh, 2), "model_la": round(la, 2),
        "model_p": {"home": round(pH/t, 3), "draw": round(pD/t, 3), "away": round(pA/t, 3)},
        "model_score": f"{score[0]}-{score[1]}",
    }


# ---------- prompt ----------
SCHEMA_HINT = """{
 "headline": "כותרת אחת מסקרנת בעברית",
 "context": "מה על הכף: מצב הבית והתרחישים. בנוקאאוט - לפי היריבה.",
 "lineups": {"<HOME_ABBR>": {"formation":"4-3-3","xi":["שם","..."(11)],"news":"חדשות/פציעות"},
             "<AWAY_ABBR>": {"formation":"...","xi":["..."],"news":"..."}},
 "tactics": "טקטיקה צפויה לכל קבוצה - לפי סגנון המאמן ומצב המשחק.",
 "form": {"<HOME_ABBR>":"כושר 10 משחקים אחרונים","<AWAY_ABBR>":"..."},
 "h2h": "היסטוריית ראש בראש.",
 "matchup": "ניתוח המאצ'אפ וגולים צפויים.",
 "opta": {"home":"12.9%","draw":"19%","away":"68.1%","sims":"25,000 סימולציות"},
 "betting": {"odds":{"home":{"dec":"7.8","imp":"13%"},"draw":{"dec":"5.5","imp":"18%"},"away":{"dec":"1.4","imp":"73%"}},
             "ou":"קו 2.5 שערים","handicap":"הפרש שערים צפוי","predicted_scores":[{"src":"מקור","score":"2-0"}],
             "value":"הימור ערך","tip":"המלצה קצרה","sources":["url"]},
 "key_players": [{"team":"<ABBR>","name":"שם","why":"למה"}],
 "surprise_why": "משפט-שניים: למה המשחק עלול להפתיע (פציעות במועדפת, כושר ירוד, לחץ, יריבה שכבר הפתיעה השנה) — או למה דווקא צפוי. עקבי עם מדד ההפתעה שניתן.",
 "prediction": "שורה תחתונה + תוצאה צפויה.",
 "score_hint": "0-2",
 "sources": ["url1","url2"]
}"""


def build_prompt(f):
    ko = "  זהו משחק נוקאאוט — אין תיקו: הארכה ופנדלים אם צריך, המפסיד מודח." if f["is_knockout"] else ""
    return f"""אתה אנליסט כדורגל מקצועי. חקור לעומק את משחק גביע העולם 2026:
{f['home_en']} ({f['home_he']}, קוד {f['home']}) נגד {f['away_en']} ({f['away_he']}, קוד {f['away']}),
{f['stage']}, בתאריך {f['date'][:10]}.{ko}

חפש באינטרנט מידע עדכני: הרכבים צפויים ופורמציה, פציעות/השעיות, כושר אחרון,
ראש-בראש, תחזית Opta (theanalyst.com — אחוזי ניצחון), והמלצות הימורים מהאתרים
המובילים (יחסי 1X2, הפרש שערים/הנדיקפ, תחזיות תוצאה סופית, הימור ערך).

נתוני רקע (אמיתיים):
- דירוג כוח (Elo): {f['home_he']} {f['elo_home']} | {f['away_he']} {f['elo_away']}
- מצב הבית כרגע: {f['standings']}
- תחזית המודל שלי: גולים צפויים {f['home_he']} {f['model_lh']} - {f['model_la']} {f['away_he']};
  הסתברות ניצחון בית {f['model_p']['home']:.0%} / תיקו {f['model_p']['draw']:.0%} / ניצחון חוץ {f['model_p']['away']:.0%};
  תוצאה סבירה {f['model_score']}.
- מדד הפתעה של המשחק (לפי המודל): {f['surprise_index']}/100 ({f['surprise_level']}).
  השנה הטורניר מלא הפתעות — המוחלשת לא הפסידה ב-{f['chaos_pct']}% מהמשחקים שנשחקו.
  ב-surprise_why הסבר קצר ועקבי עם המדד: אם גבוה — למה דווקא כאן ייתכן אפסט; אם נמוך — למה צפוי.

החזר אך ורק אובייקט JSON תקין (בלי טקסט נוסף, בלי ```), בדיוק במבנה הבא.
התוכן בעברית; שמות שחקנים באנגלית. השתמש בקודים המדויקים {f['home']} ו-{f['away']} כמפתחות ב-lineups וב-form.
אם מידע מסוים לא נמצא — כתוב הערכה סבירה וציין שהיא הערכה, אל תמציא עובדות.
ב-"sources" החזר עד 5 קישורים עיקריים ואיכותיים בלבד (לא יוטיוב). אם Opta לא פרסמה תחזית ספציפית למשחק — ציין זאת קצר ב-"sims" ותן הערכה.

מבנה (schema):
{SCHEMA_HINT}"""


# ---------- gemini call ----------
def gemini_generate(prompt, model=DEFAULT_MODEL, retries=2):
    key = get_key()
    url = ENDPOINT.format(model=model)
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingBudget": 0},  # free the budget for output
        },
    }
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, headers={"x-goog-api-key": key},
                              json=body, timeout=90)
            if r.status_code != 200:
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                time.sleep(2 * (attempt + 1))
                continue
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except Exception as ex:
            last = str(ex)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini call failed: {last}")


def extract_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(t[i:j + 1])


REQUIRED = ("headline", "context", "lineups", "tactics", "form", "h2h",
            "matchup", "key_players", "prediction")


def generate_match(state, fx, model=DEFAULT_MODEL, attempts=3):
    f = match_facts(state, fx)
    prompt = build_prompt(f)
    a, last = None, None
    for _ in range(attempts):
        try:
            a = extract_json(gemini_generate(prompt, model=model))
            break
        except Exception as ex:           # malformed JSON → retry (resampling fixes it)
            last = ex
    if a is None:
        raise RuntimeError(f"no valid JSON after {attempts} attempts: {last}")
    a["match_id"] = f["id"]
    a["home"], a["away"], a["group"] = f["home"], f["away"], f["group"]
    a["generated_by"] = f"gemini ({model})"
    missing = [k for k in REQUIRED if k not in a]
    if missing:
        raise ValueError(f"analysis missing keys: {missing}")
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    path = os.path.join(ANALYSIS_DIR, f"{f['id']}.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(a, fp, ensure_ascii=False, indent=1)
    return path


import datetime as _dt
_IL = _dt.timezone(_dt.timedelta(hours=3))


def _fday(iso):
    return BD.matchday(iso)


def upcoming_fixtures(state, days=2):
    """(now_day, fixtures) for the next `days` matchdays that have games."""
    now_day = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=5)).date()
    byday = {}
    for fx in BD.all_fixtures(state):
        byday.setdefault(_fday(fx["date"]), []).append(fx)
    target = sorted(d for d in byday if d >= now_day)[:days]
    if not target:
        target = sorted(byday)[-days:]
    out = []
    for d in target:
        out.extend(sorted(byday[d], key=lambda f: f["date"]))
    return now_day, out


def generate_upcoming(state, days=2, model=DEFAULT_MODEL, force=False):
    """Refresh TODAY's analyses (force) and pre-generate the NEXT day's if missing."""
    now_day, fxs = upcoming_fixtures(state, days)
    done, failed = [], []
    for fx in fxs:
        is_today = _fday(fx["date"]) == now_day
        path = os.path.join(ANALYSIS_DIR, f"{fx['id']}.json")
        if os.path.exists(path) and not (force and is_today):
            continue
        try:
            generate_match(state, fx, model=model)
            done.append(fx["id"])
            print(f"  ✓ {fx['home']}–{fx['away']}{'' if is_today else ' (מחר)'}")
        except Exception as ex:
            failed.append((fx["id"], str(ex)))
            print(f"  ✗ {fx['home']}–{fx['away']}: {ex}")
    return done, failed


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    with open(os.path.join(DATA_DIR, "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    force = "--force" in sys.argv
    # optional single match id
    mid = next((a for a in sys.argv[1:] if a.isdigit()), None)
    if mid:
        fx = next(x for x in state["group_fixtures"] if str(x["id"]) == mid)
        print("Generating", mid, "...")
        print("Wrote", generate_match(state, fx))
    else:
        print("Generating analyses (today + tomorrow) ...")
        done, failed = generate_upcoming(state, days=2, force=force)
        print(f"Done: {len(done)} generated, {len(failed)} failed")
