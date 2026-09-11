# Blok 12 — Outlook-rækkesynk + uge 40 Mallorca (11/9-2026)

Tests: 632 passed (pytest-shim, pypi blokeret — CI er dommer; pywebpush-testen springes over lokalt). `schemas/validate.py` grøn på alle seks filer.

## Ændringer pr. fil

- `.github/workflows/scripts/sync_outlook.py`: `parse_weeks()` — `week` kan nu være `'3'`, et interval `'3-17'` eller `'all'`. Selve synken er flyttet til `sync_week(WEEK)` og kører pr. uge (uændret rækkefølge: hent Intervals → slet Træning-events → opret). Ved interval springes uger med 0 workouts over uden at rydde (Japan-ugerne) — én uge alene fejler stadig som før. Token hentes én gang.
- `.github/workflows/create-outlook-events.yml`: input-beskrivelser opdateret. Cron/workflow_call/dispatch uændret.
- `docs/PIPELINE.md`: Outlook-rækken opdateret.
- `scripts/modules/test_outlook_times.py`: `test_sync_outlook_parse_weeks`.
- `data/proposals/2026-09-11-uge40-mallorca.json` (ny, `applied-offline`): uge 40 lagt om efter Outlook ("Kennet på Mallorca" 27/9-3/10). Søn 27/9 rejsedag (let løb valgfri), man-tor udendørs Z2 2 t → 3 t → 4 t med stigninger i Z2 (Sa Calobra uden PR), ons styrke A + løb, fre let 90 valgfri, lør fri, søn 4/10 Depottur 2 t + styrke B. Eneste gate-advarsel: CTL-ramp +5,2 i programuge 6 (blødt loft 5) — accepteret, uge 41 er recovery.
- `data/plan.json`: dagene 27/9-4/10, `season2027.weeks[4]` (Mallorca, quota 0/0), `travel` med Mallorca 27/9-3/10.
- `scripts/modules/test_proposals.py`: blok 11-testen springer uger over som senere forslag har skrevet om.

## Sådan lægges alle uger i Outlook

Actions → "Sync workouts til Outlook kalender" → Run workflow → `week`: `3-17`, `program`: `tds-2027`. Kør igen med samme input efter enhver planændring — synken sletter og genopretter Træning-events pr. uge, så gamle pas forsvinder. Søndagens cron holder den kommende uge opdateret automatisk.
