# Compliance pr. pas + CTL mod plan (30/9-2026)

Kennet kunne ikke se compliance pr. pas i dashboardet. `data.json` havde felterne (`completion_pct`, `actual_mins`, `actual_tss`, `planned_*`) i `week_sessions`, men `index.html` læste dem ikke.

## Ændringer
- `index.html`: nyt kort "Compliance — ugens pas" på I dag (under ugestriben): pr. pas faktisk/planlagt (min og TSS) og procent. Farve: grøn 80–120 %, gul 50–79 %, rød under 50 % eller over 120 %. Et planlagt pas på en dag der er gået uden aktivitet tæller som 0 %. Ugetotal (TSS og tid) for pas til og med i dag.
- `index.html`: linjen "CTL mod plan" i samme kort: CTL nu mod ugens mål, forskel, ugeændring mod planlagt ugeændring, ATL og afvigelse for de seneste 4 uger.
- `index.html`: `applyRemote` kopierer nu `fitnessLive` ind i `D` (bruges til CTL nu).
- Ingen ændringer i pipeline, plan.json eller skemaer.

## Test
- pytest 669 bestået, 1 sprunget over; `schemas/validate.py` OK; `node --check sw.js` OK; index.html inline-scripts OK.
- Logikken kørt mod live `data.json` i browseren: CTL 48,0 mod mål 55 (−7,0), ugeændring +1,5 mod plan +2,0.

## Ikke verificeret
- Kortet er ikke set gengivet på telefon. Layoutet bruger de eksisterende `.card`/`.label`-klasser.

## Tillæg (30/9-2026, senere): begge procenter pr. pas
- `index.html`: hvert pas viser nu tid og TSS hver for sig med egen procent og farve (fx "Tid 300/240 min = 125 % · TSS 95/171 = 56 %"). Tallet til højre er uændret pipelinens `completion_pct` (det svageste af tid og TSS). Forklaringslinjen er rettet.
- Ingen ændring i `DURATION_FIRST_DISCS` — cykel er stadig ikke tid-først. Beslutning venter.
- Senere samme dag: tallet til højre pr. pas (pipelinens `completion_pct`) er fjernet fra kortet, fordi tid og TSS nu står hver for sig. Ugetotalen i toppen er uændret.
- Senere samme dag (Kennets ønske): på cykelpas med "Mallorca" i navnet vises TSS-procenten uden farve (bjerge og pauser trækker TSS ned). Tiden farves stadig. Indendørs og danske pas er uændrede. Ugetotalen (TSS) tæller stadig Mallorca-pas med.
- Senere samme dag: `scripts/modules/sessions.py` lægger Garmin-aktivitetens navn på passet som `actual_name` (ny test i `test_sessions.py`). Dashboardet neutraliserer nu TSS-farven på cykelpas hvis pasnavnet indeholder "Mallorca" ELLER aktivitetens navn indeholder "Fornalutx". `actual_name` findes først i data.json efter næste pipeline-kørsel; indtil da virker kun pasnavns-reglen.
