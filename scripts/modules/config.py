"""Fælles konfiguration, konstanter og hjælpefunktioner."""
import os, time, requests

API_KEY       = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID    = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
GH_TOKEN      = os.environ.get('GH_TOKEN', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
REPO          = 'hammerbamsen/fast-as-50'
BASE          = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH          = ('API_KEY', API_KEY)

# ── Goal Engine: al plan-data læses fra data/plan.json ─────────
# plan.json er den ENESTE kilde til CTL-plan, blok-typer, racedatoer,
# programstart og mål. Hardcodede fallbacks bruges kun hvis filen mangler.
import json as _json
from datetime import date as _date

_PLAN_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'plan.json')

def _load_plan():
    try:
        with open(_PLAN_PATH, encoding='utf-8') as f:
            return _json.load(f)
    except Exception as e:
        print(f"  ⚠️  plan.json kunne ikke læses ({e}) — bruger fallback-konstanter")
        return None

PLAN = _load_plan()

if PLAN:
    _weeks      = sorted(PLAN['weeks'], key=lambda w: w['week'])
    CTL_PLAN    = [w['ctlTarget'] for w in _weeks]
    BLOCK_TYPES = {w['week']: w['blockType'] for w in _weeks}
    TOTAL_WEEKS = PLAN['program']['totalWeeks']
    PLAN_START  = _date.fromisoformat(PLAN['program']['start'])
    RACES       = PLAN.get('races', [])
    GOALS       = PLAN.get('goals', {})
else:
    # Fallback (bør aldrig rammes i drift)
    CTL_PLAN    = [34, 36, 38, 41, 48, 50, 54, 60, 56, 61, 67, 63, 59, 56]
    BLOCK_TYPES = {1:'BUILD',2:'BUILD+',3:'BUILD+',4:'RECOVERY',5:'BUILD',6:'BUILD',
                   7:'BUILD',8:'BUILD+',9:'RECOVERY',10:'BUILD',11:'BUILD+',12:'TAPER',
                   13:'TAPER',14:'RACE'}
    TOTAL_WEEKS = 14
    PLAN_START  = _date(2026, 6, 1)
    RACES       = [{"name": "Christiansborg Rundt", "date": "2026-08-29"},
                   {"name": "Marathon du Médoc", "date": "2026-09-05"}]
    GOALS       = {"weightKg": 70, "bodyFatPct": 20}

# Faste programmål -- én kilde, brugt i både dashboard-KPI'er og coach-tekst.
# CTL-start/slutmål udledes ALTID af CTL_PLAN, så de aldrig kan komme ud af sync med planen.
CTL_START = CTL_PLAN[0]
CTL_GOAL = CTL_PLAN[-1]
AF_GOAL = 5
SLEEP_GOAL_HOURS = 7
SWIM_GOAL_M = 2000
RUN_KM_GOAL = 40
RUN_KM_GOAL_WEEK = 10

DK_DAYS    = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag","Lørdag","Søndag"]
DAY_SHORT  = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
DK_MONTHS  = ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"]

# (BLOCK_TYPES defineres ovenfor af Goal Engine / plan.json)

# Friel-baserede løb-pace-zoner (sek/km), baseret på threshold 4:20/km.
# VIGTIGT: Intervals.icu's egen pace_zone_times bruger en generisk 7-zone
# %-tabel der IKKE matcher disse grænser for Z3 og opefter (verificeret
# 2/7-26 -- se sessions.py: compute_run_pace_zone_secs).
# Z2 matcher tilfældigvis ICU's egen tabel, men Z3-Z6 gør ikke -- derfor
# beregnes løb-zone-tid altid ud fra rå pace-stream mod DISSE grænser.
RUN_PACE_ZONES_SEC_PER_KM = {
    'Z1': (335, 99999),   # langsommere end 5:35/km
    'Z2': (296, 334),     # 4:56-5:34/km
    'Z3': (266, 295),     # 4:26-4:55/km
    'Z4': (253, 265),     # 4:13-4:25/km
    'Z5': (233, 252),     # 3:53-4:12/km
    'Z6': (0, 232),       # hurtigere end 3:52/km
}


def api_get(url, auth=None, params=None, timeout=20, retries=3):
    """requests.get med exponential backoff retry på transiente fejl."""
    for attempt in range(retries):
        try:
            r = requests.get(url, auth=auth, params=params, timeout=timeout)
            if r.status_code < 500:
                return r
            print(f"  ⚠️  api_get {url} → HTTP {r.status_code}, forsøg {attempt+1}/{retries}")
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"  ⚠️  api_get {url} → {e}, forsøg {attempt+1}/{retries}")
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    return None


def ctl_plan_for_week(week_num):
    idx = min(max(week_num, 1), len(CTL_PLAN)) - 1
    return CTL_PLAN[idx]


def fix_enc(s):
    if not isinstance(s, str):
        return s
    try:
        return s.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def fmt(val, decimals=1):
    if val is None:
        return "—"
    try:
        return f"{float(val):.{decimals}f}".replace('.', ',')
    except (ValueError, TypeError):
        return str(val)


def color_for(val, target, lower=True):
    if val is None:
        return '#7A6A58'
    try:
        val = float(val)
        pct = val / target if target else 0
        if lower:
            if pct <= 1.0:   return '#27AE60'
            if pct <= 1.1:   return '#E67E22'
            return '#C0392B'
        else:
            if pct >= 0.95:  return '#27AE60'
            if pct >= 0.80:  return '#E67E22'
            return '#C0392B'
    except (ValueError, TypeError):
        return '#7A6A58'
