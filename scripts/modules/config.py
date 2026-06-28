"""Fælles konfiguration, konstanter og hjælpefunktioner."""
import os, time, requests

API_KEY       = os.environ.get('INTERVALS_API_KEY', '')
ATHLETE_ID    = os.environ.get('INTERVALS_ATHLETE_ID', 'i0')
GH_TOKEN      = os.environ.get('GH_TOKEN', '')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
REPO          = 'hammerbamsen/fast-as-50'
BASE          = f'https://intervals.icu/api/v1/athlete/{ATHLETE_ID}'
AUTH          = ('API_KEY', API_KEY)

# Autoritativ uge-for-uge CTL-plan (matcher CTL_PLAN i index.html)
CTL_PLAN = [34, 36, 38, 41, 48, 52, 49, 54, 59, 64, 68, 64, 61, 58]

DK_DAYS    = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag","Lørdag","Søndag"]
DAY_SHORT  = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
DK_MONTHS  = ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"]

BLOCK_TYPES = {1:'BUILD',2:'BUILD+',3:'BUILD+',4:'RECOVERY',5:'BUILD',6:'BUILD',
               7:'RECOVERY',8:'BUILD',9:'BUILD',10:'BUILD+',11:'BUILD+',12:'TAPER',
               13:'TAPER',14:'RACE'}


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
