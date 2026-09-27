# 27/9-2026 — "Flyt" uden at bytte + løb i træk kan bekræftes

Kennet 27/9: ville flytte søndagens løb til mandag tidlig og stadig cykle mandag. Appen kunne kun bytte dage, og kun inden for samme uge.

## Ændringer pr. fil
- `scripts/modules/edit_apply.py`: `move` har ny mode `add` ("Læg oveni"). Kun det valgte pas flyttes; måldagens pas bliver.
- `scripts/modules/friel.py`: `consecutive_runs` er nu WARN (før HARD). Appen viser "Fortsæt alligevel". Max 3 løb/uge er stadig HARD.
- `index.html`: Flyt-arket har to valg: "Læg oveni" (standard) og "Byt dage". Dagslisten viser denne uge + næste uge (søndag → mandag virker). Konsekvenstekst og lokal opdatering følger valget. Coach-forslag med `move` bruger stadig "Byt dage", medmindre forslaget har `mode`.
- `scripts/modules/test_edit_apply.py`: 2 nye tests (add-mode bevarer måldagens pas; consecutive_runs er WARN).
- `data/proposals/2026-09-27-lob-til-man.json` (separat commit): søn 27/9 fri, note på man 28/9.

## Test
- pytest: 662 passed, 1 skipped. schemas/validate.py: ok. node --check sw.js + index.html inline scripts: ok.
- Røgtest på rigtig plan.json: løb flyttet oveni man 28/9 → `warn` "Fortløbende løbedage 2026-09-28 + 2026-09-29"; med confirmedWarn → `ok`.

## Ikke verificeret
- Flyt-arket er ikke klikket igennem i en browser/iPhone.
