# -*- coding: utf-8 -*-
"""
CTL-rekalibrering ved porte (14/9-2026).

Målene i plan.json (ctlTarget/tssTarget pr. uge) ligger fast — afvigelsen fra
dem er coachens signal. Men når hele banen er forskudt, skal de næste ugers mål
følge med, ellers kalder coachen en normal uge "over plan" i to måneder.

Porte (kun her overvejes rekalibrering):
  * mandag efter en RECOVERY-uge
  * mandag efter en uge med FTP-test (note/purpose indeholder "FTP-test")
  * manuelt: CTL_RECALIB=1 i miljøet (workflow-input)

Regel: afvigelse = CTL i dag − ctlTarget for ugen der starter i dag.
  * |afvigelse| < MIN_DEV -> intet
  * afvigelse > 0 -> forslag: de næste N uger forskydes med aftagende offset
    (fuld afvigelse i uge 0, lineært mod 0), tssTarget følger med 7 TSS pr. CTL-
    point (steady state). Aldrig ud over `nextRace`-grænsen for peak/race-CTL:
    kun uger inden HORIZON og aldrig uger med blockType RACE/TAPER/CAMP.
  * afvigelse < 0 -> INGEN rekalibrering nedad; kun en advarsel (returneres
    som `warning`) — planen skal ikke sænkes efter en dårlig uge.

Alt er et forslag (data/proposals/ctl-recalib-<dato>.json, status pending)
gennem den eksisterende gate. Intet ændres uden accept.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone, timedelta

from . import programs as _programs
from . import proposals as _props

MIN_DEV = 3.0          # CTL-point før en port foreslår noget
HORIZON = 8            # uger der forskydes (aftagende)
TSS_PER_CTL = 7        # steady state: +1 CTL ≈ +7 TSS/uge
PROTECTED = ("RACE", "TAPER", "CAMP")
PID_PREFIX = "ctl-recalib-"


def _da(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def _is_port(program: dict, today: date) -> tuple[bool, str]:
    """(er_port, begrundelse). Kun mandage."""
    if today.weekday() != 0:
        return False, ""
    w = _programs.week_no_raw(program, today)
    prev = _programs.week_meta(program, w - 1) if w >= 2 else {}
    if not prev:
        return False, ""
    if str(prev.get("blockType") or "").upper() == "RECOVERY":
        return True, f"mandag efter recovery-uge (uge {w - 1})"
    txt = f"{prev.get('note') or ''} {prev.get('purpose') or ''}".lower()
    if "ftp-test" in txt or "ftp test" in txt:
        return True, f"mandag efter FTP-test (uge {w - 1})"
    return False, ""


def offsets(dev: float, n: int = HORIZON) -> list[int]:
    """Aftagende heltals-offsets: fuld afvigelse først, lineært mod 0.
    dev=5, n=8 -> [5, 4, 4, 3, 2, 2, 1, 1]."""
    out = []
    for k in range(n):
        v = int(round(dev * (n - k) / n))
        out.append(v)
    return out


def recent_recalib_exists(root=None, within_days: int = 14, today: date | None = None) -> bool:
    today = today or date.today()
    for p in _props.list_all(root):
        pid = str(p.get("id") or "")
        if not pid.startswith(PID_PREFIX):
            continue
        if p.get("status") == "pending":
            return True
        try:
            d = date.fromisoformat(pid[len(PID_PREFIX):][:10])
        except ValueError:
            continue
        if (today - d).days < within_days:
            return True
    return False


def build_proposal(plan: dict, ctl: float, today: date, reason: str,
                   athlete: str = "kennet") -> dict | None:
    program = _programs.active_program(plan, athlete, today)
    if not program or ctl is None:
        return None
    pid_prog = program["id"]
    w0 = _programs.week_no_raw(program, today)
    meta0 = _programs.week_meta(program, w0)
    if meta0.get("ctlTarget") is None:
        return None
    dev = float(ctl) - float(meta0["ctlTarget"])
    if abs(dev) < MIN_DEV:
        return None
    if dev < 0:
        return {"warning": f"CTL {_da(ctl)} er {_da(abs(dev))} under ugens mål {meta0['ctlTarget']} — "
                           f"ingen rekalibrering nedad ({reason})."}
    offs = offsets(dev)
    changes, rows = [], []
    for k, off in enumerate(offs):
        if off <= 0:
            continue
        w = w0 + k
        m = _programs.week_meta(program, w)
        if not m or m.get("ctlTarget") is None:
            continue
        # Indeværende uge (k=0) justeres altid — den er startet, og målet er
        # nu en måling. Beskyttelsen gælder kommende race/taper/lejr-uger.
        if k > 0 and str(m.get("blockType") or "").upper() in PROTECTED:
            continue
        new_ctl = int(round(m["ctlTarget"] + off))
        ch = {"action": "set_week_targets", "programId": pid_prog, "week": w, "ctlTarget": new_ctl}
        # Indeværende uge: kun CTL-målet (måling) — ugens TSS-mål er allerede i gang.
        if k > 0 and m.get("tssTarget") is not None:
            ch["tssTarget"] = int(round(m["tssTarget"] + off * TSS_PER_CTL))
        changes.append(ch)
        rows.append(f"uge {_programs.week_start(program, w).isocalendar()[1]}: CTL {m['ctlTarget']} → {new_ctl}")
    if not changes:
        return None
    pid = f"{PID_PREFIX}{today.isoformat()}"
    return {
        "id": pid,
        "title": f"CTL-rekalibrering +{dev:.0f}",
        "status": "pending",
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "createdBy": "ctl-recalib",
        "note": (f"Port: {reason}. CTL i dag {_da(ctl)} mod ugens mål {meta0['ctlTarget']} (+{_da(dev)}). "
                 f"De næste {len(changes)} uger løftes aftagende, så kurven glider tilbage på sæsonens linje. "
                 f"Peak og race-CTL røres ikke. TSS-mål følger med ({TSS_PER_CTL} TSS pr. CTL-point)."),
        "summary": rows,
        "changes": changes,
    }


def maybe_propose(plan: dict, ctl, today: date | None = None, force: bool | None = None,
                  athlete: str = "kennet", root=None) -> dict | None:
    """Kaldes fra update_kpi. Returnerer forslaget (ikke gemt), {'warning': …}, eller None."""
    today = today or date.today()
    if force is None:
        force = os.environ.get("CTL_RECALIB", "").strip().lower() not in ("", "0", "false", "no")
    program = _programs.active_program(plan, athlete, today)
    if not program:
        return None
    port, reason = _is_port(program, today)
    if force:
        port, reason = True, "manuel kørsel"
    if not port:
        return None
    if recent_recalib_exists(root, today=today):
        return None
    return build_proposal(plan, ctl, today, reason, athlete)
