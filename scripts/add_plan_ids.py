# -*- coding: utf-8 -*-
"""
Engangs-migration (fase 2, idempotent): tilføjer stabilt `id` på hver
workout-entry i data/plan.json for begge atleter.

Id'et er 8 hex-tegn, genereres ÉN gang og må aldrig regenereres —
det er nummerpladen fase 3-write-back bruger til at matche et pas
mod Intervals/Outlook, uanset om dagen flyttes.

Kør fra repo-roden: python3 scripts/add_plan_ids.py
"""
import json
import uuid
from pathlib import Path

PLAN = Path(__file__).resolve().parent.parent / "data" / "plan.json"


def main():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    seen = set()
    added = 0

    for ath in plan["athletes"].values():
        for day in ath.get("days", []):
            for entry in day.get("entries", []):
                eid = entry.get("id")
                if eid:
                    seen.add(eid)

    for ath_key, ath in plan["athletes"].items():
        for day in ath.get("days", []):
            for entry in day.get("entries", []):
                if entry.get("id"):
                    continue
                eid = uuid.uuid4().hex[:8]
                while eid in seen:
                    eid = uuid.uuid4().hex[:8]
                entry["id"] = eid
                seen.add(eid)
                added += 1

    if added:
        PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"Tilføjet {added} id'er. Unikke i alt: {len(seen)}.")


if __name__ == "__main__":
    main()
