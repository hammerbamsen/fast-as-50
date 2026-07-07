# -*- coding: utf-8 -*-
"""
Martin-signaler — Fast as Fifty (T5).

Opsamler kostrelevante planændringer i data/martin_signals.md, som
integreres i den ugentlige søndagsmail til Martin Kreutzer.
Martin får IKKE løbende notifikationer — filen er intern opsamling.

Relevansfilter (kun ændringer der påvirker energibehov):
  - hårdt pas tilføjet/fjernet/flyttet (VO2, Z4/Z5, interval, tempo, tærskel)
  - langt pas tilføjet/fjernet/flyttet (>= 90 min)
  - samlet daglig varighed ændret >= 45 min

Alt andet (fx flyt af 30 min recovery-spin) er støj og logges ikke.
"""
from datetime import date, datetime, timezone, timedelta

HARD_MARKERS = ("vo2", "z4", "z5", "interval", "tempo", "tærskel", "taerskel",
                "5×3", "4×5", "6×3", "5x3", "4x5", "6x3")
LONG_SECONDS = 90 * 60          # langt pas
DAY_DELTA_SECONDS = 45 * 60     # relevant daglig varighedsændring

MD_HEADER = (
    "# Signaler til Martin — opsamles til søndagsmailen\n"
    "\n"
    "<!-- Auto-opdateret ved plan-redigering. Integreres i den ugentlige\n"
    "     mail til Martin Kreutzer og ryddes derefter. Ingen løbende mails. -->\n"
)


def _secs(wo):
    try:
        return int(wo.get("moving_time") or 0)
    except (TypeError, ValueError):
        return 0


def _is_hard(wo):
    name = (wo.get("name") or "").lower()
    return any(m in name for m in HARD_MARKERS)


def _is_long(wo):
    return _secs(wo) >= LONG_SECONDS


def _tags(wo):
    t = []
    if _is_hard(wo):
        t.append("hårdt")
    if _is_long(wo):
        t.append("langt")
    return t


def _fmt_wo(wo):
    mins = _secs(wo) // 60
    tags = _tags(wo)
    tag_s = f" [{', '.join(tags)}]" if tags else ""
    return f"{wo.get('name', '?')} ({mins} min){tag_s}"


def _day_workouts(plan, d_iso, athlete):
    for d in plan.get("athletes", {}).get(athlete, {}).get("days", []):
        if d.get("date") == d_iso:
            return [e["workout"] for e in d.get("entries", []) if e.get("workout")]
    return []


def _relevant(before, after):
    """Relevant for Martin? Hårdt/langt pas berørt, eller stor varighedsændring."""
    b_names = {(w.get("name"), _secs(w)) for w in before}
    a_names = {(w.get("name"), _secs(w)) for w in after}
    changed = [w for w in before if (w.get("name"), _secs(w)) not in a_names] + \
              [w for w in after if (w.get("name"), _secs(w)) not in b_names]
    if any(_is_hard(w) or _is_long(w) for w in changed):
        return True
    delta = abs(sum(_secs(w) for w in after) - sum(_secs(w) for w in before))
    return delta >= DAY_DELTA_SECONDS


def _week_no(d_iso, plan):
    try:
        start = date.fromisoformat(plan["program"]["start"])
        return (date.fromisoformat(d_iso) - start).days // 7 + 1
    except (KeyError, ValueError):
        return None


def _dow_da(d_iso):
    days = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
    return days[date.fromisoformat(d_iso).weekday()]


def build_signal(old_plan, new_plan, action, dates_changed, athlete="kennet",
                 now=None):
    """
    Returnerer markdown-blok med kostrelevante ændringer — eller None hvis
    ændringen er irrelevant for Martin. Kun Kennets plan (Martin er Kennets
    kostvejleder).
    """
    if athlete != "kennet":
        return None
    lines = []
    for d_iso in sorted(set(dates_changed or [])):
        before = _day_workouts(old_plan, d_iso, athlete)
        after = _day_workouts(new_plan, d_iso, athlete)
        if not _relevant(before, after):
            continue
        w = _week_no(d_iso, new_plan)
        b_s = "; ".join(_fmt_wo(x) for x in before) or "hviledag"
        a_s = "; ".join(_fmt_wo(x) for x in after) or "hviledag"
        wk = f"uge {w}, " if w else ""
        lines.append(f"- **{_dow_da(d_iso)} {d_iso}** ({wk}{action}): "
                     f"{b_s} → {a_s}")
    if not lines:
        return None
    ts = (now or datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=2)))).strftime("%d/%m %H:%M")
    return f"\n### Planændring {ts}\n" + "\n".join(lines) + "\n"


def append_signal(existing_md, signal_md):
    """Append signal til eksisterende md-indhold (opretter header hvis tom)."""
    base = existing_md if (existing_md or "").strip() else MD_HEADER
    if not base.endswith("\n"):
        base += "\n"
    return base + signal_md
