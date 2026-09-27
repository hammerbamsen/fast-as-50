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

## QA 27/9 (samme dag)
- UI i headless Chromium (390×844) med rigtig data.json: Flyt-ark viser "Læg oveni" (valgt) / "Byt dage", 13 dage (denne + næste uge), korrekt konsekvenstekst og payload `mode: add|swap`. Justér-ark forudfylder 16:15, Gem er slået fra indtil ændring, sender `start_time` kun ved ændring, `null` ved tomt felt. Ingen JS-fejl.
- Ende-til-ende: adjust `start_time: '16:30'` via plan-edit → timeOverrides opdateret, Outlook-event flyttet til 16:30–18:30, ingen sync-fejl. Sat tilbage til 16:15.
- Fejl fundet og rettet: "Læg oveni" på en fri dag lod "Fri"-noten blive stående ved siden af passet. Nu fjernes hviledags-noter (uden workout, ikke done) på måldagen. Ny test. pytest: 669 passed.
