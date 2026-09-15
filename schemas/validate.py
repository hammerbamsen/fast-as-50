#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validerer datafilernes STRUKTUR mod skemaerne i schemas/ (blok 7, 7/9-2026).

    python3 schemas/validate.py            # alle tre filer
    python3 schemas/validate.py data.json  # kun én

Kræver `pip install jsonschema`. Køres af CI (ci-pytest.yml) på hvert push.

Skemaerne kræver kun de felter koden reelt afhænger af (programs/weeks/days/
entries, id/load/erg/steps, meta/kpis/today/week_sessions) med
additionalProperties: true overalt — de fanger struktur-brud, ikke nye felter.
Ud over skemaet tjekkes to ting skemaer ikke kan: unikke pas-id'er i
bike_library.json og unikke entry-id'er i plan.json. Forslag i data/proposals/
tjekkes desuden for at filnavn = id og at ingen dato optræder to gange.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"

FILES = {
    "data/plan.json": "plan.schema.json",
    "data/bike_library.json": "bike_library.schema.json",
    "data.json": "data.schema.json",
}
# Forslag (blok 9): alle data/proposals/*.json valideres mod proposal.schema.json.
FILES.update({str(p.relative_to(ROOT)).replace("\\", "/"): "proposal.schema.json"
              for p in sorted((ROOT / "data" / "proposals").glob("*.json"))})


def _dupes(ids):
    return sorted(k for k, n in Counter(ids).items() if n > 1)


def extra_checks(rel, doc):
    """Regler skemaet ikke kan udtrykke. Returnerer liste af fejltekster."""
    errs = []
    if rel == "data/bike_library.json":
        d = _dupes(w.get("id") for w in doc.get("workouts", []))
        if d:
            errs.append(f"dublerede workout-id'er: {d}")
    if rel == "data/plan.json":
        ids = [e.get("id")
               for a in (doc.get("athletes") or {}).values() if isinstance(a, dict)
               for day in a.get("days") or []
               for e in day.get("entries") or []]
        d = _dupes(ids)
        if d:
            errs.append(f"dublerede entry-id'er på tværs af atleter/dage: {d[:10]}")
    if rel.startswith("data/proposals/"):
        if doc.get("id") != Path(rel).stem:
            errs.append(f"id {doc.get('id')!r} matcher ikke filnavnet {Path(rel).stem!r}")
        dates = [c.get("date") for c in doc.get("changes", []) if c.get("date")]
        d = _dupes(dates)
        if d:
            errs.append(f"datoer optræder to gange i changes: {d}")
        wks = [(c.get("programId"), c.get("week")) for c in doc.get("changes", [])
               if c.get("action") == "set_week_targets"]
        d = _dupes(wks)
        if d:
            errs.append(f"programuger optræder to gange i changes: {d}")
    return errs


def validate_file(rel, schema_name):
    from jsonschema import Draft202012Validator
    path = ROOT / rel
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"kan ikke læses/parses: {e}"]
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    v = Draft202012Validator(schema)
    errs = []
    for err in sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<rod>"
        errs.append(f"{where}: {err.message[:200]}")
    errs += extra_checks(rel, doc)
    return errs


def main(argv):
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print("jsonschema mangler: pip install jsonschema")
        return 2
    wanted = set(argv) or set(FILES)
    failed = 0
    for rel, schema_name in FILES.items():
        if rel not in wanted:
            continue
        errs = validate_file(rel, schema_name)
        if errs:
            failed += 1
            print(f"❌ {rel} ({schema_name}): {len(errs)} fejl")
            for e in errs[:25]:
                print(f"   - {e}")
            if len(errs) > 25:
                print(f"   … og {len(errs) - 25} til")
        else:
            print(f"✅ {rel} OK ({schema_name})")
    unknown = wanted - set(FILES)
    if unknown:
        print(f"ukendte filer ignoreret: {sorted(unknown)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
