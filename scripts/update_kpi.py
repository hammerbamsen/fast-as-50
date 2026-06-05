#!/usr/bin/env python3
"""
Fast as Fifty — daglig opdatering
Henter data fra Intervals.icu og opdaterer data.json på GitHub.
"""
import os, json, requests, base64
from datetime import date, timedelta

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
        params={"oldest": str(date.today()-timedelta(days=7)), "newest": str(date.today())})
    if r.status_code != 200:
        print(f"Wellness fejl: {r.status_code}")
        return {}
    data = r.json()
    if not data: return {}
    weights = [d["weight"]  for d in data if d.get("weight")]
    fats    = [d["bodyFat"] for d in data if d.get("bodyFat")]
    hrvs    = [d["hrv"]     for d in data if d.get("hrv")]
    ctls    = [d["ctl"]     for d in data if d.get("ctl")]
    wstart  = week_start()
    af = sum(1 for d in data
             if date.fromisoformat(d["id"]) >= wstart
             and d.get("Alkohol") == 0)
    return {
        "weight": round(weights[-1],1) if weights else None,
        "fat":    round(fats[-1],1)    if fats    else None,
        "hrv":    round(sum(hrvs)/len(hrvs),1) if hrvs else None,
        "ctl":    round(ctls[-1],1)    if ctls    else None,
        "af":     af,
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
    return {"tss": round(tss), "run_km": round(run_km,1)}

def dk_date():
    today     = date.today()
    dk_days   = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag","Lordag","Sondag"]
    dk_months = ["jan","feb","mar","apr","maj","jun","jul","aug","sep","okt","nov","dec"]
    return dk_days[today.weekday()], f"{today.day}. {dk_months[today.month-1]}"

def planned_tss(week_no):
    planned = {1:383,2:460,3:466,4:167,5:511,6:490,7:546,
               8:186,9:596,10:598,11:638,12:194,13:345,14:245}
    return planned.get(week_no, 400)

def get_data_json():
    headers = {"Authorization": f"token {GH_TOKEN}", "User-Agent": "FastAsFifty-Bot"}
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/data.json", headers=headers)
    r.raise_for_status()
    info = r.json()
    content = json.loads(base64.b64decode(info["content"]).decode("utf-8"))
    return content, info["sha"]

def upload_data_json(data, sha, msg):
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "User-Agent": "FastAsFifty-Bot",
        "Content-Type": "application/json"
    }
    payload = {
        "message": msg,
        "content": base64.b64encode(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")).decode("utf-8"),
        "sha": sha
    }
    r = requests.put(f"https://api.github.com/repos/{REPO}/contents/data.json",
                     headers=headers, json=payload)
    r.raise_for_status()
    print(f"data.json opdateret: {r.json()['commit']['sha'][:10]}")


def get_week_sessions():
    """Hent ugens aktiviteter fra Intervals.icu og byg week_sessions array"""
    mon = week_start()
    sun = mon + timedelta(days=6)
    r = requests.get(f"{BASE}/activities", auth=AUTH,
        params={"oldest": str(mon), "newest": str(sun)})
    if r.status_code != 200:
        return None

    activities = {a["start_date_local"][:10]: a for a in r.json()}

    dk_days = ["Man","Tir","Ons","Tor","Fre","Lør","Søn"]
    disc_map = {
        "Run": "run", "TrailRun": "run", "VirtualRun": "run",
        "Ride": "bike", "VirtualRide": "bike", "EBikeRide": "bike",
        "Swim": "swim",
        "WeightTraining": "strength", "Workout": "strength",
    }

    today = date.today()
    sessions = []
    for i in range(7):
        d = mon + timedelta(days=i)
        key = str(d)
        act = activities.get(key)
        is_today = d == today
        is_done = d < today

        if act:
            disc = disc_map.get(act.get("type",""), "free")
            label = act.get("name", dk_days[i])
            dur = f"{round(act.get('moving_time',0)/60)} min" if act.get("moving_time") else ""
        else:
            disc = "free"
            label = "Hvile"
            dur = ""

        s = {"day": dk_days[i], "disc": disc, "label": label, "done": is_done}
        if is_today:
            s["today"] = True
        sessions.append(s)

    # Dagens session
    today_key = str(today)
    today_act = activities.get(today_key)
    if today_act:
        disc = disc_map.get(today_act.get("type",""), "free")
        today_session = {
            "discipline": disc,
            "title": today_act.get("name", "Træning"),
            "duration": f"{round(today_act.get('moving_time',0)/60)} min",
            "zone": "–",
            "desc": today_act.get("description", ""),
            "completed": False
        }
    else:
        today_session = None

    return sessions, today_session

def main():
    today  = date.today()
    week1  = date(2026, 6, 1)
    wk     = min(max((today - week1).days // 7 + 1, 1), 14)
    days_medoc = max(0, (date(2026,9,5)  - today).days)
    days_chr   = max(0, (date(2026,8,29) - today).days)
    day_name, day_date = dk_date()

    print(f"Opdaterer: {day_name} {day_date} | Uge {wk} | Médoc: {days_medoc}d")

    w = get_wellness()
    a = get_activities()
    planned = planned_tss(wk)
    tss_comp = round(a["tss"] / planned * 100) if a.get("tss") and planned else None

    weight  = w.get("weight")
    fat     = w.get("fat")
    ctl     = w.get("ctl") or 34
    hrv     = w.get("hrv")
    af      = w.get("af", 0)
    run_km  = a.get("run_km")
    tss_pct = tss_comp

    print(f"Data: vægt={weight} fedt={fat} CTL={ctl} HRV={hrv} AF={af} km={run_km} TSS={tss_pct}%")

    # Hent eksisterende data.json
    data, sha = get_data_json()

    # Opdater felter
    data["meta"]["updated"]              = str(today)
    data["meta"]["week"]                 = wk
    data["meta"]["daysToMedoc"]          = days_medoc
    data["meta"]["daysToChristiansborg"] = days_chr
    data["meta"]["dayName"]              = day_name
    data["meta"]["date"]                 = day_date

    data["af"]["weekDone"] = af

    def fmt(v, fallback="—"):
        return str(v).replace(".0","") if v is not None else fallback

    data["kpis"]["weight"]["value"]  = fmt(weight, "74,5")
    data["kpis"]["fat"]["value"]     = fmt(fat, "23,0")
    data["kpis"]["ctl"]["value"]     = fmt(ctl)
    data["kpis"]["hrv"]["value"]     = fmt(hrv)
    data["kpis"]["tss"]["value"]     = fmt(tss_pct)
    data["kpis"]["runKm"]["value"]   = fmt(run_km, "0")

    # Hent ugens sessioner
    sessions_result = get_week_sessions()
    if sessions_result:
        sessions, today_session = sessions_result
        data["week_sessions"] = sessions
        if today_session:
            data["today"] = today_session
        print(f"Sessioner opdateret: {[s['label'] for s in sessions]}")

    upload_data_json(data, sha, f"Auto {today} — uge {wk} | CTL={ctl} AF={af} km={run_km}")
    print("Færdig!")

if __name__ == "__main__":
    main()
