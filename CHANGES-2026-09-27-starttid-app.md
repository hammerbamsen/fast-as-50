# 27/9-2026 — starttid i appens Justér-ark

Kennet 27/9: vil selv kunne sætte starttid på et pas i appen (ikke kun via chatten).

## Ændringer pr. fil
- `scripts/modules/edit_apply.py`: `adjust` tager `start_time` ('HH:MM' eller null). Skrives til `timeOverrides[dato][type]`. null fjerner passets tid. En dagsdækkende override ([h, m]) laves om til pr. disciplin, så dagens andre pas bliver hvor de er.
- `scripts/modules/plan_tab.py`: hvert pas i planTab får `start` (HH:MM) og `startFixed` — samme tid som Outlook-synken giver (`outlook_times.schedule_day`).
- `index.html`: Justér-arket har feltet "Starttid i kalenderen" (forudfyldt). Tidspunkt sendes kun ved ændring; tomt felt = standardtid. Plan-fanen viser "kl. HH:MM" pr. pas.
- `scripts/modules/test_edit_apply.py`: 2 nye tests.

## Test
- pytest: 668 passed, 1 skipped. schemas/validate.py: ok. node --check sw.js + index.html inline scripts: ok.
- planTab på rigtig plan.json: man 28/9 løb 06:30 (fast), cykel 16:15 (fast); tir 29/9 styrke 06:30, løb 07:15 (standard).

## Ikke verificeret
- Arket er ikke klikket igennem på iPhone. "kl."-tider vises først efter næste update-kpi-kørsel.
