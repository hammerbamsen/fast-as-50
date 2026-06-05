#!/usr/bin/env python3
"""
Fast as Fifty — daglig opdatering kl 05:00
Henter data fra Intervals.icu og opdaterer data.json på GitHub.
Inkluderer: CTL, TSB, HRV, søvn, vægt, fedt, AF, løb km, sessions.
"""
import os, json, requests, base64
from datetime import date, timedelta
from statistics import mean

API_KEY    = os.environ.get("INTERVALS_API_KEY", "")
ATHLETE_ID = os.environ.get("INTERVALS_ATHLETE_ID", "i0")
GH_TOKEN   = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
REPO       = "hammerbamsen/fast-as-50"
BASE       = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
AUTH       = ("API_KEY", API_KEY)

def week_start():
    t = date.today()
    return t - timedelta(days=t.weekday())

def get_wellness():
    r = requests.get(f"{BASE}/wellness", auth=AUTH,
        params={"oldest": str(date.today()-timedelta(days=14)), "newest": str(date.today())})
    if r.status_code != 200:
        print(f"Wellness fejl: {r.status_code}")
        return {}
    data = r.json()
    if not data: return {}

    # Vægt — 7-dages glidende gennemsnit
    weights_7d = [d["weight"] for d in data[-7:] if d.get("weight")]
    weight_avg = round(mean(weights_7d), 1) if weights_7d else None
    weight_today = next((d["weight"] for d in reversed(data) if d.get("weight")), None)

    fats    = [d["bodyFat"] for d in data if d.get("bodyFat")]
    hrvs_7d = [d["hrv"] for d in data[-7:] if d.get("hrv")]
    hrv_avg = round(mean(hrvs_7d), 1) if hrvs_7d else None
    hrv_today = next((d["hrv"] for d in reversed(data) if d.get("hrv")), None)
    hrv_trend = "Stigende" if len(hrvs_7d) >= 3 and hrvs_7d[-1] > hrvs_7d[-3] else "Faldende" if len(hrvs_7d) >= 3 and hrvs_7d[-1] < hrvs_7d[-3] else "Stabil"

    # CTL og TSB (ATL)
    ctls  = [d["ctl"] for d in data if d.get("ctl")]
    atls  = [d["atl"] for d in data if d.get("atl")]
    ctl   = round(ctls[-1], 1) if ctls else None
    atl   = round(atls[-1], 1) if atls else None
    tsb   = round(ctl - atl, 1) if ctl and atl else None

    # TSB form-status
    if tsb is not None:
        if tsb > 5:    form = "Klar"
        elif tsb > -10: form = "Bygger"
        elif tsb > -20: form = "Hård blok"
        else:           form = "Overbelastet"
        form_color = "#27AE60" if tsb > 5 else "#F39C12" if tsb > -10 else "#E67E22" if tsb > -20 else "#C0392B"
    else:
        form, form_color = "—", "#7A6A58"

    # Søvn — seneste nat
    sleeps = [(d["id"], d.get("sleepSecs", 0)) for d in data if d.get("sleepSecs")]
    sleep_hrs = round(sleeps[-1][1] / 3600, 1) if sleeps else None
    sleep_7d_avg = round(mean([s[1] for s in sleeps[-7:]]) / 3600, 1) if len(sleeps) >= 2 else None

    # AF-dage denne uge
    wstart = week_start()
    af = sum(1 for d in data
             if date.fromisoformat(d["id"]) >= wstart
             and d.get("Alkohol") == 0)

    # HRV status
    if hrv_today and hrv_avg:
        hrv_pct = round((hrv_today - hrv_avg) / hrv_avg * 100)
        hrv_status = f"+{hrv_pct}% vs snit" if hrv_pct >= 0 else f"{hrv_pct}% vs snit"
    else:
        hrv_status = hrv_trend

    return {
        "weight":      weight_avg,
        "weight_today": round(weight_today, 1) if weight_today else None,
        "fat":         round(fats[-1], 1) if fats else None,
        "hrv":         hrv_today,
        "hrv_status":  hrv_status,
        "ctl":         ctl,
        "atl":         atl,
        "tsb":         tsb,
        "form":        form,
        "form_color":  form_color,
        "sleep_hrs":   sleep_hrs,
        "sleep_avg":   sleep_7d_avg,
        "af":          af,
    }

def get_activities():
    r = requests.get(f"{BASE}/activities", auth=AUTH,
        params={"oldest": str(week_start()), "newest": str(date.today())})
    if r.status_code != 200:
        print(f"Activities fejl: {r.status_code}")
        return {}
    data = r.json()
    tss    = sum(a.get("training_load") or 0 for a in data)
    run_km = sum((a.get("distance") or 0)/1000 for a in data
                 if a.get("type") in ["Run","TrailRun","VirtualRun"])
    return {"tss": round(tss), "run_km": round(run_km, 1)}

def get_week_sessions():
    mon = week_start()
    sun = mon + timedelta(days=6)
    r = requests.get(f"{BASE}/activities", auth=AUTH,
        params={"oldest": str(mon), "newest": str(sun)})
    if r.status_code != 200:
        return None, None

    activities = {}
    for a in r.json():
        key = a["start_date_local"][:10]
        activities[key] = a

    disc_map = {
        "Run":"run","TrailRun":"run","VirtualRun":"run",
        "Ride":"bike","VirtualRide":"bike","EBikeRide":"bike",
        "Swim":"swim",
        "WeightTraining":"strength","Workout":"strength","Crossfit":"strength",
    }
    dk_days = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
    today = date.today()

    sessions = []
    for i in range(7):
        d = mon + timedelta(days=i)
        key = str(d)
        act = activities.get(key)
        is_today = d == today
        is_done  = d < today

        if act:
            disc  = disc_map.get(act.get("type",""), "free")
            label = act.get("name", dk_days[i])
        else:
            disc  = "free"
            label = "Hvile"

        s = {"day": dk_days[i], "disc": disc, "label": label, "done": is_done and bool(act)}
        if is_today: s["today"] = True
        sessions.append(s)

    # Dagens session
    today_act = activities.get(str(today))
    if today_act:
        disc = disc_map.get(today_act.get("type",""), "free")
        today_session = {
            "discipline": disc,
            "title":      today_act.get("name", "Træning"),
            "duration":   f"{round((today_act.get('moving_time') or 0)/60)} min",
            "zone":       "–",
            "desc":       today_act.get("description") or "",
            "completed":  True
        }
    else:
        today_session = None

    return sessions, today_session

def planned_tss(week_no):
    planned = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,
               8:186,9:596,10:598,11:638,12:194,13:345,14:245}
    return planned.get(week_no, 400)

def generate_coach_speech(w, a, week_no, form):
    """Dynamisk coach speech baseret på aktuelle data"""
    lines = []

    # HRV-baseret åbning
    if w.get("hrv") and w.get("hrv_status"):
        hrv = w["hrv"]
        status = w["hrv_status"]
        if "+" in str(status):
            lines.append(f"HRV {hrv} ms — {status}. Kroppen er klar.")
        elif "-" in str(status) and int(str(status).replace("%","").split()[0]) < -10:
            lines.append(f"HRV {hrv} ms — {status}. Skru ned i dag.")
        else:
            lines.append(f"HRV {hrv} ms — stabilt. Kør planen.")

    # Søvn
    sleep = w.get("sleep_hrs")
    sleep_avg = w.get("sleep_avg")
    if sleep and sleep_avg:
        if sleep < 6.5:
            lines.append(f"Søvn {sleep}t — under dit mål. Prioritér hvile i nat.")
        elif sleep >= 7.5:
            lines.append(f"Søvn {sleep}t — godt.")

    # Form
    tsb = w.get("tsb")
    if tsb is not None:
        if tsb < -15:
            lines.append(f"{HL_START}Form: {form}. Hård blok — hold formen til recovery-uge.{HL_END}")
        elif tsb > 5:
            lines.append(f"{HL_START}Form: {form}. Du er klar til at presse på.{HL_END}")
        else:
            lines.append(f"Form TSB {tsb} — bygger fitness planmæssigt.")

    # Uge-specifik besked
    week_msgs = {
        1: "Uge 1: etabler rytmen. 5 AF-dage, protein ved hvert måltid.",
        2: "Uge 2: volumen op. Holder du Z2 disciplin?",
        3: "Uge 3: peak build-uge. Sov godt i weekenden.",
        4: "Recovery-uge. Aktiv hvile — ikke sofa.",
    }
    lines.append(week_msgs.get(week_no, f"Uge {week_no}: hold systemet kørende."))

    speech = " ".join(lines[:3])  # max 3 sætninger
    highlight = lines[1] if len(lines) > 1 else lines[0]
    return speech.replace(HL_START,"").replace(HL_END,""), highlight.replace(HL_START,"").replace(HL_END,"")

HL_START = "***"
HL_END   = "***"

def get_data_json():
    headers = {"Authorization": f"token {GH_TOKEN}", "User-Agent": "FastAsFifty-Bot"}
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/data.json", headers=headers)
    r.raise_for_status()
    info = r.json()
    content = json.loads(base64.b64decode(info["content"]).decode("utf-8"))
    return content, info["sha"]

def upload_data_json(data, sha, msg):
    headers = {"Authorization": f"token {GH_TOKEN}", "User-Agent": "FastAsFifty-Bot", "Content-Type": "application/json"}
    payload = {
        "message": msg,
        "content": base64.b64encode(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")).decode("utf-8"),
        "sha": sha
    }
    r = requests.put(f"https://api.github.com/repos/{REPO}/contents/data.json", headers=headers, json=payload)
    r.raise_for_status()
    print(f"data.json opdateret: {r.json()['commit']['sha'][:10]}")

def main():
    today  = date.today()
    week1  = date(2026, 6, 1)
    wk     = min(max((today - week1).days // 7 + 1, 1), 14)
    days_medoc = max(0, (date(2026,9,5)  - today).days)
    days_chr   = max(0, (date(2026,8,29) - today).days)

    print(f"Opdaterer: {today} | Uge {wk} | Médoc: {days_medoc}d")

    w = get_wellness()
    a = get_activities()

    planned  = planned_tss(wk)
    tss_comp = round(a["tss"] / planned * 100) if a.get("tss") and planned else None

    def fmt(v, dec=1):
        if v is None: return "—"
        return str(round(v, dec)).replace(".", ",")

    print(f"Wellness: vægt={w.get('weight')} CTL={w.get('ctl')} TSB={w.get('tsb')} HRV={w.get('hrv')} søvn={w.get('sleep_hrs')} AF={w.get('af')}")

    # Hent data.json
    data, sha = get_data_json()

    # Opdater meta
    data["meta"]["updated"]              = str(today)
    data["meta"]["week"]                 = wk
    data["meta"]["daysToMedoc"]          = days_medoc
    data["meta"]["daysToChristiansborg"] = days_chr

    # Opdater AF
    data["af"]["weekDone"] = w.get("af", 0)

    # Opdater KPIs — nu med søvn og TSB i stedet for TSS compliance
    data["kpis"] = {
        "weight":  {"value": fmt(w.get("weight")),      "unit": "kg",  "sub": f"Mål <72 kg · snit 7d",     "color": "#27AE60"},
        "fat":     {"value": fmt(w.get("fat")),          "unit": "%",   "sub": "Mål <20%",                  "color": "#F39C12"},
        "ctl":     {"value": fmt(w.get("ctl")),          "unit": "",    "sub": "Mål 60 (uge 11)",            "color": "#C0392B"},
        "tsb":     {"value": fmt(w.get("tsb")),          "unit": "",    "sub": w.get("form", "—"),           "color": w.get("form_color", "#7A6A58")},
        "sleep":   {"value": fmt(w.get("sleep_hrs")),    "unit": "t",   "sub": f"Snit {fmt(w.get('sleep_avg'))}t · mål 7t", "color": "#2874A6"},
        "runKm":   {"value": fmt(a.get("run_km"), 1),    "unit": "km",  "sub": "Mål 40+ km uge 10",         "color": "#C0392B"},
        "hrv":     {"value": fmt(w.get("hrv"), 1),       "unit": "ms",  "sub": w.get("hrv_status", "—"),    "color": "#7A6A58"},
    }

    # Dynamisk coach speech
    coach, highlight = generate_coach_speech(w, a, wk, w.get("form","—"))
    data["coachSpeech"]    = coach + " {HL}"
    data["coachHighlight"] = highlight

    # Sessioner
    sessions, today_session = get_week_sessions()
    if sessions:
        data["week_sessions"] = sessions
    if today_session:
        data["today"] = today_session

    upload_data_json(data, sha, f"Auto {today} — uge {wk} | CTL={w.get('ctl')} TSB={w.get('tsb')} søvn={w.get('sleep_hrs')}t AF={w.get('af')}")
    print("Færdig!")

if __name__ == "__main__":
    main()
