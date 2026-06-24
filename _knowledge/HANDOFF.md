# HANDOFF — חיזוי מונדיאל 2026

מסמך המשכיות. קרא לפני המשך עבודה.

## מצב נוכחי (2026-06-24)
**שלב 1 הושלם ועובד** — מנוע Elo+Poisson+MonteCarlo + דאשבורד HTML, רץ מקומית מ-`run.py` ב-~14ש'.

**עיצוב מחדש (לבקשת המשתמש):** האתר רב-עמודי:
- `index.html` = **משחקי היום בלבד** (football-day 06:00→06:00 IL), כל משחק כרטיס + xG/1X2 + כפתור "ניתוח מלא". כפתור 🔄 רענן (fetch חי ל-ESPN client-side, עם timeout; כשל = שומר נתוני build). כפתור → `odds.html`.
- `odds.html` = סקציות ההסתברויות (זכייה/בתים/התקדמות).
- `match-<id>.html` = ניתוח טקסטואלי לכל משחק היום, נטען מ-`data/analysis/<id>.json`. אין JSON → placeholder.
**ניתוח לדוגמה הושלם** (Scotland-Brazil, `data/analysis/760465.json`) — אושר ע"י המשתמש כפורמט. ה-5 האחרים placeholder עד Gemini.

**סכמת analysis JSON** (מה ש-Gemini יפיק לכל משחק): headline, context, lineups{team:{formation,xi[],news}}, tactics, form{team}, h2h, matchup, **opta{home,draw,away,sims}** (פר-משחק!), **betting{odds{home/draw/away:{dec,imp}}, ou, handicap, predicted_scores[{src,score}], value, tip, sources[]}**, key_players[{team,name,why}], prediction, score_hint, sources[]. ה-renderer כבר תומך בכל אלה (כולל סעיף "💰 תחזיות והימורים" + הערת הימור אחראי).

## החלטות נעולות (מהשיחה עם המשתמש)
- פלט: **דאשבורד HTML** (עברית, RTL, מותאם נייד). לא אקסל.
- שיטה: **הכל ביחד** — Elo + Poisson(Dixon-Coles) + Monte Carlo.
- נתונים: **תוצאות חיות**, מותנה במה שכבר שוחק.
- אירוח: **ענן אוטונומי** — GitHub Actions + GitHub Pages (כדי לצפות מהנייד, המחשב כבוי).
- שכבת אנליסט: **Gemini API** (למשתמש יש מנוי Google AI Pro → גישת AI Studio + Pro + קרדיטים).
- GitHub username: **AviadAbekasis**. תיקייה: `U:\Aviad\Claude\מונדיאל 2026\`.

## ארכיטקטורת נתונים (מאומת מול המקורות)
- **ESPN hidden API** (חינם, בלי מפתח) — מקור האמת החי:
  - לוח: `site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260611-20260719&limit=400` → 104 אירועים.
  - בתים+טבלאות: `site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings?season=2026` → 12 בתים עם entries.
  - הבראקט כולו מקודד בשמות-מציין (Group A Winner / Round of 32 N Winner / Third Place Group A/B/C/D/F...).
  - לוגואים: `team.logo` → `a.espncdn.com/i/teamlogos/countries/500/<abbr>.png`.
- **eloratings.net/2026_World_Cup.tsv** (חינם) — Elo. עמודה 2=קוד, עמודה 3=Elo. צריך `r.encoding='utf-8'`.
  - eloratings מתעדכן אחרי כל משחק, אז ה-Elo כבר משקף תוצאות הטורניר → אין צורך לעדכן Elo ידנית.
- מיפוי קוד eloratings → ESPN abbr ב-`teams.py` (מאומת 1:1 לכל 48). מפתח קנוני = ESPN abbr.

## נקודות מודל / כיול
- Elo→λ: quartic ניטרלי ("Football rankings 2020"). Dixon-Coles ρ=-0.13. יתרון מארחת +70 Elo (שלב בתים בלבד).
- דגימת MC = Poisson עצמאי (מהיר); מטריצת DC רק לתצוגת 1X2.
- **ידוע: המודל top-heavy** (ארגנטינה ~29%, ספרד ~23%) — יותר מבתי-הימורים. כיול בשלב 3: הוסף כושר 10-משחקים + שונות, אולי הקטן השפעת דירוג.
- **Annex C (שיבוץ מקומות שלישיים)**: כרגע bipartite-matching שמכבד את קבוצות-המועמדים (לא הטבלה הרשמית המלאה של 495 שורות). מבני-נכון, השפעה זניחה על הסתברויות. לשיפור: קידוד הטבלה הרשמית.
- ולידציה עוברת: Σp_adv=32.00, Σp_champion=1.000, Σp_sf=4.00, כל בית Σp_win=1.0.

## שלב 2 — שכבת אנליסט (Gemini) — לא התחיל
מה שאין לו API חינמי ולכן ה-LLM מייצר (מעוגן בנתונים):
- הרכב צפוי + פורמציה (קרא RotoWire/FotMob preview HTML + ההרכב הסופי האחרון).
- טקטיקה צפויה: בשלב בתים לפי מצב-טבלה (must-win/כבר העפיל); בנוקאאוט לפי יריבה בלבד.
- מעקב השעיות (כרטיסים, כולל איפוס צהובים אחרי שלב הבתים ואחרי הרבע).
- הרכב/פציעות סופיים זמינים מ-API-Football (free key) ~40 דק' לפני משחק — אופציונלי.
- **תחזית Opta פר-משחק** (theanalyst.com/articles/...-prediction-world-cup-2026... — win%, sims). המשתמש ביקש מפורשות ש-Opta יופיע בכל ניתוח.
- **המלצות הימורים פר-משחק** מהאתרים המובילים: יחסי 1X2, הנדיקפ/הפרש שערים, תחזיות תוצאה סופית, value bet. מקורות עובדים: SportsLine, RacingPost, SportsMole, Yahoo, oddschecker. (compare.bet החזיר 403; theanalyst נגיש דרך WebFetch.) להציג יחס עשרוני + % משתמע + הערת הימור אחראי.
זרימה: לכל משחק קרוב → אסוף נתונים (preview+Opta+odds) → קריאת Gemini → JSON לפי הסכמה → `data/analysis/<id>.json` → build_dashboard מרנדר.

## שלב 3 — אוטומציה בענן — לא התחיל
- צור repo תחת AviadAbekasis (פרטי או ציבורי). דחוף את התיקייה.
- GitHub Actions: cron (כל בוקר + לפני מחזורים) → `python src/run.py` → commit `output/` → Pages מגיש.
- מפתח Gemini ב-GitHub Secrets (GEMINI_API_KEY). אסור בקוד.
- כתובת: `https://aviadabekasis.github.io/<repo>/`.
- שים לב: מ-19/6/2026 Google דוחה מפתחות API "standard" לא-מוגבלים — ודא שהמפתח החדש תקין.

## הרצה
`python src/run.py [N]` או דאבל-קליק `עדכן וחזה.bat`. preview מקומי: `.claude/launch.json` שם "wc2026" (port 8765).
