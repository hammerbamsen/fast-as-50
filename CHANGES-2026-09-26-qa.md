# 26/9-2026 — QA af appen (alle fire faner renderet lokalt i 393 px med live data.json)

## Rettet
- `index.html`: gammelt statisk kort "Styrke — Functional Strength 2" i Mere fjernet (forældet øvelsesliste, dublet af det nye styrkekort).
- `index.html`: "Én ting til i morgen" fjernet. Overskriften skiftede, når dagens pas var udført, men coachen skriver stadig om i dag — i dag stod der "i morgen" over "Kør Gravel Z2 ude … du har allerede gennemført turen".
- `prompts/coach_system.md`: regel — er dagens pas udført, gentages passet ikke; `oneThing` handler om resten af dagen eller morgendagens forberedelse.
- `scripts/modules/martin_signals.py`: Martin-mailen viser pasnavn i stedet for bibliotek-id (fx "z2_depottur_2t"). Test opdateret.
- `scripts/health_report.py`: forventet kadence for "Daglig dashboard-opdatering" 60 → 120 min. GitHub drosler cron til 2–3,5 t, så System-kortet stod gult uden grund. Test opdateret.

## Test
- pytest 660 passed, 1 skipped · schemas OK · node --check sw.js OK · inline scripts OK · ingen JS-fejl ved rendering af de fire faner.

## Ikke rettet (kræver beslutning eller er data)
- Hegnet Half (7/3-2027) mangler under "Kommende løb" (står ikke i det aktive programs races).
- Plan siger "53 uger", Mere siger "51-ugers periodeplan" (Plan tæller Médoc-programmets sidste uger med).
- Cykelzoner i Mere (Z2 154–211 W) afviger fra overview (150–205 W) — zoneberegneren bruger andre procenter end plan.json.
