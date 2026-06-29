# -*- coding: utf-8 -*-
"""Render the dashboard:
   output/index.html        landing — today's matches + refresh + link to odds
   output/match-<id>.html   per-match text analysis (from data/analysis/<id>.json)
   output/odds.html         tournament probabilities (champion / groups / deep-run)
All Hebrew RTL, mobile-first.
"""
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bracket as B          # noqa: E402
import model as M            # noqa: E402
from teams import HE_NAME, FLAG, HOSTS, he, flag  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "output")
IL = dt.timezone(dt.timedelta(hours=3))
_LOGOS = {}
_CHAOS = {"rate": 0.0, "big": 0, "n": 0}


# ---------- helpers ----------
def il_dt(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IL)


def il_time(iso):
    try:
        return il_dt(iso).strftime("%d/%m %H:%M")
    except Exception:
        return iso[:10]


def matchday(iso):
    """US-style matchday key: all games of one slate group under one date. Boundary at
    05:00 UTC = 08:00 Israel time, so the day rolls over at 08:00 IL each morning and by
    then the user sees the UPCOMING 24h slate. The no-match gap is 05:00-15:00 UTC and the
    latest kickoff is 04:00 UTC, so no game is ever split. Times shown in Israel time."""
    u = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    return (u - dt.timedelta(hours=5)).date()


def pct(x, d=0):
    return f"{x*100:.{d}f}%"


def heat(p, hue=150):
    return f"hsla({hue},65%,45%,{0.06 + 0.6*p:.2f})"


def team_chip(ab, big=False):
    cls = "chip big" if big else "chip"
    logo = _LOGOS.get(ab)
    badge = (f'<img class="fl" src="{logo}" alt="" loading="lazy">' if logo
             else f'<span class="fl">{flag(ab)}</span>')
    return f'<span class="{cls}">{badge}{he(ab)}</span>'


def predict(state, fx):
    elo = state["teams"]
    h, a = fx["home"], fx["away"]
    grp = bool(fx.get("group"))   # host advantage applies only in the group stage
    adv_h = M.HOST_ADV if (h in HOSTS and grp) else 0.0
    adv_a = M.HOST_ADV if (a in HOSTS and grp) else 0.0
    lh, la, we = M.expected_goals(elo[h]["elo"], elo[a]["elo"], adv_h, adv_a)
    pH, pD, pA, score = M.match_probs(lh, la)
    t = pH + pD + pA
    return {"lh": lh, "la": la, "pH": pH/t, "pD": pD/t, "pA": pA/t, "score": score}


def tournament_chaos(state):
    """How upset-heavy the tournament has been: among completed group matches, how
    often the lower-Elo team avoided defeat, plus the count of outright underdog wins."""
    elo = state["teams"]
    n = 0
    not_lost = 0
    big = 0
    for fx in state["group_fixtures"]:
        if not (fx["completed"] and fx.get("hg") is not None):
            continue
        h, a = fx["home"], fx["away"]
        eh, ea = elo[h]["elo"], elo[a]["elo"]
        if eh == ea:
            continue
        n += 1
        und = h if eh < ea else a
        hg, ag = fx["hg"], fx["ag"]
        und_won = (und == h and hg > ag) or (und == a and ag > hg)
        if hg == ag or und_won:
            not_lost += 1
        if und_won:
            big += 1
    return {"rate": (not_lost / n) if n else 0.0, "big": big, "n": n}


def surprise_pill(pr):
    si = M.surprise_index(pr["pH"], pr["pD"], pr["pA"], _CHAOS["rate"])
    label, cls = M.surprise_level(si)
    return f'<span class="si {cls}" title="מדד הפתעה">🎲 הפתעה {si} · {label}</span>'


KO_ROUNDS = [
    ("2026-06-28", "2026-07-03", "שלב 32 האחרונות"),
    ("2026-07-04", "2026-07-08", "שמינית הגמר"),
    ("2026-07-09", "2026-07-13", "רבע גמר"),
    ("2026-07-14", "2026-07-17", "חצי גמר"),
    ("2026-07-18", "2026-07-18", "מקום שלישי"),
    ("2026-07-19", "2026-07-25", "גמר"),
]


def round_label(iso):
    d = iso[:10]
    for a, b, lbl in KO_ROUNDS:
        if a <= d <= b:
            return lbl
    return "נוקאאוט"


def all_fixtures(state):
    """Group matches + RESOLVED knockout matches (both teams known) for the daily view."""
    teams = state["teams"]
    out = list(state["group_fixtures"])
    for k in state.get("knockout_events", []):
        if k.get("home") in teams and k.get("away") in teams:
            kk = dict(k)
            kk["round"] = round_label(k["date"])
            out.append(kk)
    return out


def stage_label(fx):
    return ("בית " + fx["group"]) if fx.get("group") else fx.get("round", "נוקאאוט")


def window_matches(state, days=2):
    """Fixtures for the next `days` matchdays that have games (today + tomorrow).
    Baking two matchdays lets the browser switch instantly at the rollover."""
    by_day = {}
    for fx in all_fixtures(state):
        by_day.setdefault(matchday(fx["date"]), []).append(fx)
    now_day = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)).date()
    target = sorted(d for d in by_day if d >= now_day)[:days]
    if not target:
        target = sorted(by_day)[-days:]
    out = []
    for d in target:
        out.extend(sorted(by_day[d], key=lambda f: f["date"]))
    return out


def load_analyses():
    out = {}
    for p in glob.glob(os.path.join(DATA_DIR, "analysis", "*.json")):
        with open(p, encoding="utf-8") as f:
            a = json.load(f)
        out[str(a["match_id"])] = a
    return out


# ---------- landing: today's matches ----------
def match_card(state, fx):
    pr = predict(state, fx)
    h, a = fx["home"], fx["away"]
    fday = matchday(fx["date"]).isoformat()
    wh, wd, wa = pr["pH"]*100, pr["pD"]*100, pr["pA"]*100
    completed = fx["completed"] and fx.get("hg") is not None
    if completed:
        score_html = f'<span class="mscore">{fx["hg"]}–{fx["ag"]}</span><span class="badge done">הסתיים</span>'
    else:
        score_html = (f'<span class="mscore pred">{pr["score"][0]}–{pr["score"][1]}</span>'
                      f'<span class="badge soon">{il_time(fx["date"])}</span>')
    btn = (f'<a class="abtn" href="match-{fx["id"]}.html">ניתוח מלא ←</a>')
    return f'''<div class="match" data-mid="{fx['id']}" data-fday="{fday}">
      <div class="mtop"><span class="mgrp">{stage_label(fx)}</span><span class="mstat">{score_html}</span></div>
      <div class="mteams">
        <div class="mt">{team_chip(h)}<span class="xg" data-side="h">{pr['lh']:.1f}</span></div>
        <div class="vs">xG</div>
        <div class="mt"><span class="xg" data-side="a">{pr['la']:.1f}</span>{team_chip(a)}</div>
      </div>
      <div class="probbar"><div class="ph" style="width:{wh:.0f}%">{wh:.0f}%</div>
        <div class="pd" style="width:{wd:.0f}%">{wd:.0f}%</div>
        <div class="pa" style="width:{wa:.0f}%">{wa:.0f}%</div></div>
      <div class="problbl"><span>{he(h)}</span><span>תיקו</span><span>{he(a)}</span></div>
      <div class="sirow">{surprise_pill(pr)}</div>
      {btn}</div>'''


def render_landing(state, analyses):
    fxs = window_matches(state, days=2)
    daylabel = matchday(fxs[0]["date"]).strftime("%d/%m/%Y")
    cards = "".join(match_card(state, fx) for fx in fxs)
    # date range for client-side live score refresh (covers the whole window)
    ds = min(il_dt(f["date"]).astimezone(dt.timezone.utc) for f in fxs).strftime("%Y%m%d")
    de = (max(il_dt(f["date"]).astimezone(dt.timezone.utc) for f in fxs)
          + dt.timedelta(days=1)).strftime("%Y%m%d")
    upd = il_time(state["fetched_at"])
    c = _CHAOS
    banner = (f'<div class="chaos">🎲 <b>מדד ההפתעות של הטורניר:</b> '
              f'{c["big"]} ניצחונות מוחלשת · המוחלשת לא הפסידה ב-{c["rate"]*100:.0f}% '
              f'מ-{c["n"]} המשחקים שנשחקו</div>') if c["n"] else ""
    return f'''<!DOCTYPE html><html lang="he" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>חיזוי מונדיאל 2026 — משחקי היום</title><style>{CSS}</style></head>
<body><div class="wrap">
<header><h1>🏆 חיזוי מונדיאל 2026</h1>
<div class="sub">משחקי היום · <span id="daylabel">{daylabel}</span></div>
<div class="navbtns">
  <button class="nav" onclick="refresh()">🔄 רענן</button>
  <a class="nav" href="odds.html">📊 סיכויי הטורניר</a></div>
<div class="upd" id="updated">עודכן: {upd}</div></header>
{banner}
<section class="card"><div class="matches">{cards}</div>
<p class="note" id="noday" style="display:none;text-align:center">אין משחקים היום — מוצגים המשחקים הקרובים.</p>
<p class="note">לחיצה על "ניתוח מלא" פותחת ניתוח טקסטואלי של המשחק (הרכבים, טקטיקה, קריאת משחק). xG = גולים צפויים לפי המודל.</p>
</section>
<footer>מנוע Elo + Poisson + Monte Carlo · ניתוח טקסטואלי · נתונים חיים מ-ESPN<br>נבנה ע"י Claude</footer>
</div>
<script>
const DATES="{ds}-{de}";
async function refresh(){{
  const u=document.getElementById('updated');
  try{{
    const ctrl=new AbortController(); const tm=setTimeout(()=>ctrl.abort(),6000);
    const r=await fetch("https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates="+DATES+"&limit=60",{{cache:"no-store",signal:ctrl.signal}});
    clearTimeout(tm);
    const j=await r.json();
    for(const ev of (j.events||[])){{
      const card=document.querySelector('[data-mid="'+ev.id+'"]');
      if(!card)continue;
      const c=ev.competitions[0], st=c.status.type;
      const hs=c.competitors.find(x=>x.homeAway==='home').score;
      const as=c.competitors.find(x=>x.homeAway==='away').score;
      const stat=card.querySelector('.mstat');
      if(st.state!=='pre'){{
        const live=st.state==='in';
        stat.innerHTML='<span class="mscore">'+hs+'–'+as+'</span><span class="badge '+(live?'live':'done')+'">'+(live?'משחק חי':'הסתיים')+'</span>';
      }}
    }}
    u.textContent='עודכן: '+new Date().toLocaleString('he-IL');
  }}catch(e){{ /* offline / CORS: keep the data baked at build time */ }}
}}
// matchday key in the browser = UTC date of (now - 5h) -> rolls at 08:00 Israel time
function fdayNow(){{return new Date(Date.now()-18000000).toISOString().slice(0,10);}}
function showDay(){{
  const t=fdayNow();
  const cards=[...document.querySelectorAll('.match')];
  if(!cards.length)return;
  const days=[...new Set(cards.map(c=>c.dataset.fday))].sort();
  const day=days.includes(t)?t:(days.find(d=>d>=t)||days[days.length-1]);
  cards.forEach(c=>{{c.style.display=(c.dataset.fday===day)?'':'none';}});
  const lbl=document.getElementById('daylabel');
  if(lbl&&day){{const p=day.split('-');lbl.textContent=p[2]+'/'+p[1]+'/'+p[0];}}
  const nd=document.getElementById('noday'); if(nd)nd.style.display=(day===t)?'none':'block';
}}
showDay();
window.addEventListener('load',()=>{{showDay();setTimeout(refresh,300);}});
</script>
</body></html>'''


# ---------- per-match analysis page ----------
def _betting_section(analysis, h, a):
    opta = analysis.get("opta")
    bet = analysis.get("betting")
    if not (opta or bet):
        return ""
    parts = []
    if opta:
        parts.append(
            f'<p><b>תחזית Opta:</b> ניצחון {he(a)} {opta["away"]} · תיקו {opta["draw"]} · '
            f'ניצחון {he(h)} {opta["home"]} <span class="dim">({opta.get("sims","")})</span></p>')
    if bet:
        o = bet.get("odds")
        if o:
            parts.append(f'''<div class="odds">
              <div class="oc"><span>ניצחון {he(h)}</span><b>{o["home"]["dec"]}</b><span class="dim">{o["home"]["imp"]}</span></div>
              <div class="oc"><span>תיקו</span><b>{o["draw"]["dec"]}</b><span class="dim">{o["draw"]["imp"]}</span></div>
              <div class="oc fav"><span>ניצחון {he(a)}</span><b>{o["away"]["dec"]}</b><span class="dim">{o["away"]["imp"]}</span></div>
            </div><p class="dim sm">יחס עשרוני · באחוזים = הסתברות משתמעת מהיחס</p>''')
        if bet.get("predicted_scores"):
            ps = " · ".join(f'{p["src"]}: <b>{p["score"]}</b>' for p in bet["predicted_scores"])
            parts.append(f'<p><b>תחזיות תוצאה סופית:</b> {ps}</p>')
        if bet.get("handicap"):
            parts.append(f'<p><b>הפרש שערים (הנדיקפ):</b> {bet["handicap"]}</p>')
        if bet.get("ou"):
            parts.append(f'<p><b>סך שערים:</b> {bet["ou"]}</p>')
        if bet.get("value"):
            parts.append(f'<p><b>הימור ערך:</b> {bet["value"]}</p>')
        if bet.get("tip"):
            parts.append(f'<p class="tip">💡 <b>המלצה:</b> {bet["tip"]}</p>')
    return (f'<div class="sec betting"><h3>💰 תחזיות והימורים — מהאתרים המובילים</h3>'
            f'{"".join(parts)}'
            f'<p class="rg">⚠️ מידע למטרות ניתוח בלבד, לא ייעוץ הימורים. הימור אחראי · גיל 18+.</p></div>')


def render_analysis_page(state, fx, analysis):
    pr = predict(state, fx)
    h, a = fx["home"], fx["away"]
    title = f"{he(h)} נגד {he(a)}"
    wh, wd, wa = pr["pH"]*100, pr["pD"]*100, pr["pA"]*100
    model_strip = f'''<div class="modelstrip">
      <div class="ms-xg"><b>גולים צפויים:</b> {he(h)} {pr['lh']:.1f} – {pr['la']:.1f} {he(a)}
        · תוצאה סבירה {pr['score'][0]}–{pr['score'][1]}</div>
      <div class="probbar big"><div class="ph" style="width:{wh:.0f}%">{wh:.0f}%</div>
        <div class="pd" style="width:{wd:.0f}%">{wd:.0f}%</div>
        <div class="pa" style="width:{wa:.0f}%">{wa:.0f}%</div></div>
      <div class="problbl"><span>ניצחון {he(h)}</span><span>תיקו</span><span>ניצחון {he(a)}</span></div>
      <div class="ms-si">{surprise_pill(pr)}</div></div>'''

    if not analysis:
        body = f'''{model_strip}
        <div class="placeholder">
          <h3>הניתוח הטקסטואלי המלא יתווסף כאן</h3>
          <p>הרכבים צפויים · טקטיקה · כושר · ראש-בראש · קריאת משחק.<br>
          ייוצר אוטומטית ע"י Gemini בשלב הבא. כרגע מוצג ניתוח לדוגמה למשחק אחד בלבד.</p>
        </div>'''
        return _page(title, h, a, fx, body)

    def lineup_block(team):
        lu = analysis["lineups"][team]
        xi = "".join(f"<li>{n}</li>" for n in lu["xi"])
        return f'''<div class="lu">
          <div class="luhead">{team_chip(team)}<span class="form">{lu['formation']}</span></div>
          <ol class="xi">{xi}</ol>
          <p class="lunews">{lu.get('news','')}</p></div>'''

    kp = "".join(
        f'<div class="kp"><span class="kpn">{k["name"]}</span> '
        f'<span class="kpt">{he(k["team"])}</span><p>{k["why"]}</p></div>'
        for k in analysis.get("key_players", []))
    src = " · ".join(f'<a href="{u}" target="_blank">מקור {i+1}</a>'
                     for i, u in enumerate(analysis.get("sources", [])[:6]))
    betting_html = _betting_section(analysis, h, a)
    si = M.surprise_index(pr["pH"], pr["pD"], pr["pA"], _CHAOS["rate"])
    slabel, scls = M.surprise_level(si)
    swhy = analysis.get("surprise_why")
    surprise_box = (f'<div class="sec surprise {scls}"><h3>🎲 מדד הפתעה: {si}/100 · {slabel}</h3>'
                    f'<p>{swhy}</p></div>') if swhy else ""

    body = f'''
      <div class="headline">{analysis['headline']}</div>
      {model_strip}
      {surprise_box}
      <div class="sec"><h3>📋 מה על הכף</h3><p>{analysis['context']}</p></div>
      <div class="sec"><h3>👥 הרכבים צפויים</h3>
        <div class="lineups">{lineup_block(h)}{lineup_block(a)}</div></div>
      <div class="sec"><h3>♟️ טקטיקה צפויה</h3><p>{analysis['tactics']}</p></div>
      <div class="sec"><h3>📈 כושר אחרון</h3>
        <p><b>{he(h)}:</b> {analysis['form'][h]}</p>
        <p><b>{he(a)}:</b> {analysis['form'][a]}</p></div>
      <div class="sec"><h3>🤝 ראש בראש</h3><p>{analysis['h2h']}</p></div>
      <div class="sec"><h3>⚽ גולים צפויים — המאצ'אפ</h3><p>{analysis['matchup']}</p></div>
      {betting_html}
      <div class="sec"><h3>⭐ שחקני מפתח</h3><div class="kps">{kp}</div></div>
      <div class="sec pred"><h3>🎯 שורה תחתונה</h3><p>{analysis['prediction']}</p></div>
      <p class="note">{src}</p>'''
    return _page(title, h, a, fx, body)


def _page(title, h, a, fx, body):
    return f'''<!DOCTYPE html><html lang="he" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — חיזוי מונדיאל 2026</title><style>{CSS}</style></head>
<body><div class="wrap">
<div class="topbar"><a class="nav" href="index.html">← חזרה למשחקים</a>
  <button class="nav" onclick="location.reload()">🔄 רענן</button></div>
<section class="card analysis">
  <div class="ahead">{team_chip(h, big=True)}<span class="avs">נגד</span>{team_chip(a, big=True)}</div>
  <div class="asub">{stage_label(fx)} · {il_time(fx['date'])} · גביע העולם 2026</div>
  {body}
</section>
<footer>ניתוח טקסטואלי · נבנה ע"י Claude</footer>
</div></body></html>'''


# ---------- odds page (existing model sections) ----------
def current_standings(state):
    out, byg = {}, {}
    for fx in state["group_fixtures"]:
        if fx["completed"] and fx.get("hg") is not None:
            byg.setdefault(fx["group"], []).append(fx)
    for g, members in state["groups"].items():
        tab = B.table_from_matches(members, byg.get(g, []))
        rows = sorted(members, key=lambda t: (tab[t]["pts"], tab[t]["gd"], tab[t]["gf"]), reverse=True)
        out[g] = [(t, tab[t]) for t in rows]
    return out


def champion_section(sim):
    teams = sorted(sim["teams"].items(), key=lambda kv: kv[1]["p_champion"], reverse=True)
    top = [t for t in teams if t[1]["p_champion"] > 0][:12]
    mx = top[0][1]["p_champion"] if top else 1
    rows = "".join(f'''<div class="brow"><div class="bname">{team_chip(ab)}</div>
      <div class="btrack"><div class="bfill" style="width:{max(2,d["p_champion"]/mx*100):.1f}%"></div></div>
      <div class="bval">{pct(d["p_champion"],1)}</div></div>''' for ab, d in top)
    return f'<section class="card"><h2>🏆 סיכויי זכייה בגביע</h2><div class="bars">{rows}</div></section>'


def deeprun_section(sim):
    teams = sorted(sim["teams"].items(), key=lambda kv: kv[1]["p_champion"], reverse=True)[:20]
    head = "<tr><th>נבחרת</th><th>העפלה</th><th>1/8</th><th>1/4</th><th>חצי</th><th>גמר</th><th>אלופה</th></tr>"
    body = ""
    for ab, d in teams:
        cells = "".join(f'<td style="background:{heat(d[k],hue)}">{pct(d[k])}</td>'
                        for k, hue in [("p_adv",205),("p_r16",205),("p_qf",30),("p_sf",30),("p_final",350),("p_champion",350)])
        body += f"<tr><td class='tl'>{team_chip(ab)}</td>{cells}</tr>"
    return f'''<section class="card"><h2>📊 כמה רחוק כל נבחרת צפויה להגיע</h2>
      <div class="tbl-wrap"><table class="grid">{head}{body}</table></div>
      <p class="note">אחוז הסימולציות שבהן הנבחרת הגיעה לפחות לשלב הזה ({sim['n']:,} ריצות).</p></section>'''


def groups_section(sim, standings, state):
    cards = ""
    for g in sorted(state["groups"].keys()):
        simrows = {r["abbr"]: r for r in sim["groups"][g]}
        body = ""
        for ab, tab in standings[g]:
            padv = simrows[ab]["p_adv"]
            body += (f'<tr style="background:{heat(padv)}"><td class="tl">{team_chip(ab)}</td>'
                     f'<td>{tab["pld"]}</td><td><b>{tab["pts"]}</b></td>'
                     f'<td>{tab["gd"]:+d}</td><td class="adv">{pct(padv)}</td></tr>')
        cards += (f'<div class="gcard"><h3>בית {g}</h3><table class="gtab">'
                  f'<tr><th>נבחרת</th><th>מש\'</th><th>נק\'</th><th>הפרש</th><th>העפלה</th></tr>'
                  f'{body}</table></div>')
    return f'''<section class="card"><h2>🗂️ סיכויי העפלה לפי בית</h2>
      <p class="note">צבע = סיכוי העפלה. הטבלה משקפת תוצאות אמיתיות עד כה.</p>
      <div class="groups">{cards}</div></section>'''


def render_odds(state, sim):
    standings = current_standings(state)
    return f'''<!DOCTYPE html><html lang="he" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>סיכויי הטורניר — מונדיאל 2026</title><style>{CSS}</style></head>
<body><div class="wrap">
<div class="topbar"><a class="nav" href="index.html">← חזרה למשחקים</a></div>
<header><h1>📊 סיכויי הטורניר</h1><div class="upd">{sim['n']:,} סימולציות Monte Carlo</div></header>
{champion_section(sim)}
{groups_section(sim, standings, state)}
{deeprun_section(sim)}
<footer>מנוע Elo + Poisson + Monte Carlo · נבנה ע"י Claude</footer>
</div></body></html>'''


def render(state, sim):
    _LOGOS.clear()
    _LOGOS.update({a: t.get("logo") for a, t in state["teams"].items()})
    _CHAOS.clear()
    _CHAOS.update(tournament_chaos(state))
    os.makedirs(OUT_DIR, exist_ok=True)
    analyses = load_analyses()
    fx_by_id = {str(f["id"]): f for f in state["group_fixtures"]}

    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_landing(state, analyses))
    with open(os.path.join(OUT_DIR, "odds.html"), "w", encoding="utf-8") as f:
        f.write(render_odds(state, sim))
    # analysis page for every match in the window (today + tomorrow)
    pages = 0
    for fx in window_matches(state, days=2):
        a = analyses.get(str(fx["id"]))
        with open(os.path.join(OUT_DIR, f"match-{fx['id']}.html"), "w", encoding="utf-8") as f:
            f.write(render_analysis_page(state, fx, a))
        pages += 1
    return os.path.join(OUT_DIR, "index.html"), pages


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(160deg,#0f2027,#1c3a4a 60%,#16222a);
 color:#1b2733;direction:rtl;padding:14px;min-height:100vh}
.wrap{max-width:1080px;margin:0 auto}
header{text-align:center;color:#eafff4;padding:12px 8px 6px}
header h1{font-size:1.8rem}
header .sub{opacity:.85;margin-top:4px}
.upd{opacity:.65;font-size:.8rem;margin-top:6px;color:#eafff4}
.navbtns{display:flex;gap:8px;justify-content:center;margin-top:10px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.nav{display:inline-block;background:#11a36b;color:#fff;border:none;border-radius:9px;
 padding:8px 14px;font-size:.9rem;font-weight:600;cursor:pointer;text-decoration:none;font-family:inherit}
.nav:hover{background:#0d8a5a}
.card{background:#fff;border-radius:16px;padding:16px;margin:14px 0;box-shadow:0 8px 26px rgba(0,0,0,.22)}
.card h2{font-size:1.15rem;margin-bottom:12px;color:#0f3d2e;border-bottom:2px solid #e7f1ec;padding-bottom:8px}
.note{font-size:.78rem;color:#7a8794;margin-top:10px;line-height:1.5}
.chip{display:inline-flex;align-items:center;gap:7px;white-space:nowrap;font-weight:600}
img.fl{width:22px;height:22px;object-fit:contain;border-radius:3px;flex:0 0 auto}
.chip.big{font-size:1.25rem;gap:9px}.chip.big img.fl{width:34px;height:34px}
.fl{font-size:1.15rem}
/* matches */
.matches{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.match{border:1px solid #e9eeec;border-radius:13px;padding:12px;background:#fafdfb;display:flex;flex-direction:column}
.mtop{display:flex;justify-content:space-between;align-items:center;font-size:.78rem;color:#80909a;margin-bottom:9px}
.mgrp{font-weight:700;color:#0f3d2e}
.mstat{display:flex;align-items:center;gap:6px}
.mscore{background:#0f3d2e;color:#fff;border-radius:6px;padding:1px 8px;font-weight:700}
.mscore.pred{background:#cdd8d2;color:#33433b}
.badge{font-size:.66rem;padding:2px 7px;border-radius:20px;font-weight:700}
.badge.soon{background:#eef3f1;color:#7a8794}.badge.done{background:#dfeee6;color:#0f7a4f}
.badge.live{background:#e0654b;color:#fff}
.mteams{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:10px}
.mt{display:flex;align-items:center;gap:6px}
.xg{font-weight:800;color:#11a36b;font-size:1.05rem}.vs{font-size:.7rem;color:#9aa7b0}
.probbar{display:flex;height:24px;border-radius:7px;overflow:hidden;font-size:.72rem;font-weight:700;color:#fff}
.probbar.big{height:30px;font-size:.82rem;margin-top:6px}
.probbar div{display:flex;align-items:center;justify-content:center;min-width:20px}
.ph{background:#11a36b}.pd{background:#9aa7b0}.pa{background:#e0654b}
.problbl{display:flex;justify-content:space-between;font-size:.66rem;color:#8694a0;margin-top:4px}
.sirow{margin-top:9px;text-align:center}
.ms-si{margin-top:9px;text-align:center}
.si{display:inline-block;font-size:.78rem;font-weight:800;padding:4px 12px;border-radius:20px}
.si.hi{background:#fdeaea;color:#c0392b;border:1px solid #f1b8b0}
.si.mid{background:#fff4e0;color:#b9770e;border:1px solid #f0d9a8}
.si.lo{background:#e9f5ee;color:#1f7a4d;border:1px solid #c2e4ce}
.chaos{background:#241b33;color:#e9defb;border-radius:12px;padding:11px 14px;
 font-size:.85rem;text-align:center;border:1px solid #4b2e83;line-height:1.5}
.chaos b{color:#fff}
.abtn{margin-top:11px;text-align:center;background:#0f3d2e;color:#fff;border-radius:9px;
 padding:9px;font-weight:700;text-decoration:none;font-size:.9rem}
.abtn:hover{background:#16513c}
/* analysis page */
.analysis .ahead{display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;
 padding-bottom:8px;border-bottom:2px solid #e7f1ec}
.avs{color:#9aa7b0;font-weight:600}
.asub{text-align:center;color:#7a8794;font-size:.85rem;margin:8px 0 14px}
.headline{font-size:1.15rem;font-weight:800;color:#0f3d2e;text-align:center;margin-bottom:14px;line-height:1.5}
.modelstrip{background:#f3f9f6;border:1px solid #dcefe6;border-radius:12px;padding:12px;margin-bottom:16px}
.ms-xg{font-size:.92rem;color:#0f3d2e;margin-bottom:8px;text-align:center}
.sec{margin-bottom:16px}
.sec h3{font-size:1.02rem;color:#0f3d2e;margin-bottom:7px}
.sec p{line-height:1.7;color:#2c3a44;font-size:.95rem}
.sec.pred{background:#fff8f0;border:1px solid #f0e0c8;border-radius:12px;padding:13px}
.lineups{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.lu{background:#fafdfb;border:1px solid #e9eeec;border-radius:11px;padding:11px}
.luhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.form{background:#0f3d2e;color:#fff;border-radius:6px;padding:2px 9px;font-weight:700;font-size:.8rem}
.xi{margin:0 18px;font-size:.86rem;line-height:1.75;color:#2c3a44}
.lunews{font-size:.78rem;color:#7a8794;margin-top:8px;line-height:1.5}
.kps{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.kp{background:#fafdfb;border:1px solid #e9eeec;border-radius:10px;padding:10px}
.kpn{font-weight:800;color:#0f3d2e}.kpt{font-size:.75rem;color:#7a8794;margin-right:6px}
.kp p{font-size:.82rem;color:#41525c;margin-top:5px;line-height:1.5}
.placeholder{text-align:center;padding:24px 12px;color:#7a8794}
.placeholder h3{color:#0f3d2e;margin-bottom:8px}
.sec a,.note a{color:#11a36b}
/* betting */
.sec.betting{background:#f6f4fb;border:1px solid #e4ddf2;border-radius:12px;padding:14px}
.sec.betting p{margin-bottom:7px;font-size:.92rem}
.odds{display:flex;gap:8px;margin:6px 0}
.oc{flex:1;background:#fff;border:1px solid #e4ddf2;border-radius:9px;padding:9px 6px;text-align:center;
 display:flex;flex-direction:column;gap:2px}
.oc span{font-size:.74rem;color:#6b7785}
.oc b{font-size:1.15rem;color:#4b2e83}
.oc.fav{border-color:#4b2e83;background:#efe9fb}
.dim{color:#9089a6;font-size:.78rem}.sm{font-size:.72rem;margin-top:2px}
.tip{background:#efe9fb;border-radius:8px;padding:8px 10px;color:#3d2569}
.rg{font-size:.72rem;color:#9089a6;margin-top:10px;border-top:1px dashed #ddd5ee;padding-top:8px}
.sec.surprise{border-radius:12px;padding:13px;margin-bottom:16px}
.sec.surprise h3{margin-bottom:6px}
.sec.surprise.hi{background:#fdecec;border:1px solid #f1b8b0}
.sec.surprise.hi h3{color:#c0392b}
.sec.surprise.mid{background:#fff6e8;border:1px solid #f0d9a8}
.sec.surprise.mid h3{color:#b9770e}
.sec.surprise.lo{background:#eaf6ef;border:1px solid #c2e4ce}
.sec.surprise.lo h3{color:#1f7a4d}
/* odds page */
.bars{display:flex;flex-direction:column;gap:9px}
.brow{display:grid;grid-template-columns:130px 1fr 52px;align-items:center;gap:10px}
.btrack{background:#eef3f1;border-radius:8px;height:22px;overflow:hidden}
.bfill{height:100%;background:linear-gradient(90deg,#11a36b,#1ad19a);border-radius:8px}
.bval{font-weight:700;color:#0f3d2e;font-size:.9rem;text-align:left}
.tbl-wrap{overflow-x:auto}
table.grid{width:100%;border-collapse:collapse;font-size:.85rem;min-width:520px}
table.grid th,table.grid td{padding:7px 6px;text-align:center;border-bottom:1px solid #eef2f0}
table.grid th{background:#0f3d2e;color:#fff;font-weight:600}
.tl{text-align:right!important}
.groups{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.gcard{border:1px solid #eaefed;border-radius:12px;padding:10px;background:#fafdfb}
.gcard h3{font-size:.95rem;color:#0f3d2e;margin-bottom:6px}
.gtab{width:100%;border-collapse:collapse;font-size:.82rem}
.gtab th{font-size:.7rem;color:#8694a0;font-weight:600;padding:3px}
.gtab td{padding:5px 3px;text-align:center;border-top:1px solid #eef2f0}
.gtab .adv{font-weight:700;color:#0f3d2e}
footer{color:#cfe6dc;text-align:center;font-size:.76rem;opacity:.8;padding:16px 8px 28px;line-height:1.7}
"""


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    with open(os.path.join(DATA_DIR, "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    with open(os.path.join(DATA_DIR, "sim.json"), encoding="utf-8") as f:
        sim = json.load(f)
    path, pages = render(state, sim)
    print(f"Wrote {path} + {pages} analysis pages + odds.html")
