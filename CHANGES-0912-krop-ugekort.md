# Ændringer 12/9-2026 — Krop: samlet ugekort for levevaner

## Symptom
Krop-fanen viste AF-dage, protein og energi i tre forskellige sprog:
- AF-dage: ✓-cirkler man–søn (ISO-uge), tal "5/6".
- Protein: piller fra `checkinLog.slice(-7)` → søn–lør, altså sidste 7 dage og ikke ugen. Tal "0/7" tæller kun 3/3-dage; gul (2 af 3) blev ikke forklaret.
- Energi: piller søn–lør, tal "snit 7d 2,3 / 5" — en fjerde skala.

## Rettelse (index.html)
- Ny `habitsWeekCard()` erstatter AF-kortet + `proteinCard()` i `renderBody()`.
- Én grid (`.hab`): rækkelabel · 7 piller man–søn (ISO-uge, samme som AF) · "x/7"-tal.
- Samme farvelogik i alle tre rækker: grøn = ok (AF / 3 af 3 / energi ≥4), gul = delvist (drak lidt / 2 af 3 / energi 3), rød = nej, grå = ikke registreret, stiplet = fremtidig dag. Forklaring under striben.
- Tal til højre: AF `done/mål` (+ "n i træk"), protein `3/3-dage/7` (+ 4-ugers-snit fra kpis.protein.sub), energi `dage ≥4/7` (+ ugens snit). Farve efter afstand til mål som `_afColorFor`.
- Datakilde pr. dag: `logCurrent(iso)` — lokale rettelser i log-arket slår igennem med det samme, som på I dag-fanen. AF-farve følger `renderLogDots` (inkl. `af_kind` drak/autopilot).
- AF-historikken (`afHistoryViz`) beholdes nederst i samme kort.
- `proteinCard()` og `afStreakViz()` er nu ubrugte — ikke fjernet (kan slettes i en oprydning).

## QA
- `node --check` grøn på alle tre inline scripts.
- `habitsWeekCard()` kørt i node mod live data.json (12/9): 21 piller, 5 grøn AF, 5 gul protein, 1 rød + 4 gul energi, 2×grå (i dag), 3×stiplet (søndag). Tal: AF 5/6 · 5 i træk, protein 0/7 · 4 uger 0,0, energi 0/7 · snit 2,6/5.
- Ikke verificeret med Playwright-screenshot (Chromium kunne ikke hentes i sandkassen) — tjek 390 px i mørk/lys efter push.

## Samme dag: check-in "Energi: Høj" fejlede altid (422)
- **Symptom:** af-registrering.yml → "Intervals svar (422): Invalid motivation: 5". Alle registreringer med Høj er tabt siden log-arket kom — max energi i checkinLog var 3.
- **Årsag:** Intervals' `motivation`-felt er 1–4, ikke 1–5. Knappen Høj sendte 5.
- **Rettelse:** Høj = 4 (knap + logCurrent/logPick-mapping). Snit vises som "/4". checkin.py-docstring og test rettet (energi-snit-test: 4/3 → 3,5).
- **Handling for Kennet:** vælg Høj igen for 12/9 (og evt. tidligere Høj-dage) — de er aldrig nået Intervals.
