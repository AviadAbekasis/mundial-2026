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
    adv_h = M.HOST_ADV if h in HOSTS else 0.0
    adv_a = M.HOST_ADV if a in HOSTS else 0.0
    lh, la, we = M.expected_goals(elo[h]["elo"], elo[a]["elo"], adv_h, adv_a)
    pH, pD, pA, score = M.match_probs(lh, la)
    t = pH + pD + pA
    return {
        "id": str(fx["id"]),
        "home": h, "away": a,
        "home_en": fx.get("home_name", h), "away_en": fx.get("away_name", a),
        "home_he": HE_NAME.get(h, h), "away_he": HE_NAME.get(a, a),
        "group": fx["group"], "date": fx["date"],
        "elo_home": elo[h]["elo"], "elo_away": elo[a]["elo"],
        "standings": _group_standings_text(state, fx["group"]),
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
 "prediction": "שורה תחתונה + תוצאה צפויה.",
 "score_hint": "0-2",
 "sources": ["url1","url2"]
}"""


def build_prompt(f):
    return f"""אתה אנליסט כדורגל מקצועי. חקור לעומק את משחק גביע העולם 2026:
{f['home_en']} ({f['home_he']}, קוד {f['home']}) נגד {f['away_en']} ({f['away_he']}, קוד {f['away']}),
בית {f['group']}, בתאריך {f['date'][:10]}.

חפש באינטרנט מידע עדכני: הרכבים צפויים ופורמציה, פציעות/השעיות, כושר אחרון,
ראש-בראש, תחזית Opta (theanalyst.com — אחוזי ניצחון), והמלצות הימורים מהאתרים
המובילים (יחסי 1X2, הפרש שערים/הנדיקפ, תחזיות תוצאה סופית, הימור ערך).

נתוני רקע (אמיתיים):
- דירוג כוח (Elo): {f['home_he']} {f['elo_home']} | {f['away_he']} {f['elo_away']}
- מצב הבית כרגע: {f['standings']}
- תחזית המודל שלי: גולים צפויים {f['home_he']} {f['model_lh']} - {f['model_la']} {f['away_he']};
  הסתברות ניצחון בית {f['model_p']['home']:.0%} / תיקו {f['model_p']['draw']:.0%} / ניצחון חוץ {f['model_p']['away']:.0%};
  תוצאה סבירה {f['model_score']}.

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


def generate_match(state, fx, model=DEFAULT_MODEL):
    f = match_facts(state, fx)
    text = gemini_generate(build_prompt(f), model=model)
    a = extract_json(text)
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


def today_fixtures(state):
    import datetime as dt
    IL = dt.timezone(dt.timedelta(hours=3))
    def fday(iso):
        d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IL)
        return (d - dt.timedelta(hours=6)).date()
    now_day = (dt.datetime.now(IL) - dt.timedelta(hours=6)).date()
    byday = {}
    for fx in state["group_fixtures"]:
        byday.setdefault(fday(fx["date"]), []).append(fx)
    day = now_day if now_day in byday else min((d for d in byday if d >= now_day), default=min(byday))
    return sorted(byday[day], key=lambda f: f["date"])


def generate_today(state, model=DEFAULT_MODEL, force=False):
    done, failed = [], []
    for fx in today_fixtures(state):
        path = os.path.join(ANALYSIS_DIR, f"{fx['id']}.json")
        if os.path.exists(path) and not force:
            continue
        try:
            generate_match(state, fx, model=model)
            done.append(fx["id"])
            print(f"  ✓ {fx['home']}–{fx['away']}")
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
        print("Generating today's analyses ...")
        done, failed = generate_today(state, force=force)
        print(f"Done: {len(done)} generated, {len(failed)} failed")
