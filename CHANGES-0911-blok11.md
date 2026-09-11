# Blok 11 — TdS-base efter TMB-rammen (11/9-2026)

Grundlag: Tour du Mont Blanc 2025 framework training plan, tilpasset Tour des Stations Ultrafondo 28/8-2027. Rammeplanen står i projektet (`claude/plan-tds2027-rammeplan-2026-09-11.md`). Beslutninger 11/9: 10-12 t/uge i vinter, lang tur søndag, VO2-blok først og derefter lange intervaller, styrke 2×/uge hele vejen, svøm 1×/uge (ons/fre — må ikke koste cykeltid), løb+svøm som vedligehold fra april, mål = gennemføre inden cut-off, fastede ture afklares med Martin først. Japan (ski) 24/1-6/2-2027 fra Outlook.

Tests: 631 passed (pytest-shim — pypi er blokeret i sessionen, så CI's rigtige pytest skal bekræfte; `test_send_push_integration::test_corrupt_subscription_does_not_crash_batch` springes over lokalt fordi `pywebpush` mangler). `schemas/validate.py` grøn på plan.json, bike_library.json, data.json og begge forslag. `build_zwo.py` kørt: 22 pas.

## Ændringer pr. fil

- `data/proposals/2026-09-11-uge39-53.json` (ny): 105 `set_day`-ændringer, 21/9-2026 → 3/1-2027, status `applied-offline`. Genereret af et engangsscript uden for repoet; anvendt med `python3 -m modules.proposals apply-offline 2026-09-11-uge39-53 --confirm-warn` (eneste advarsel: den generiske TSB-på-racedag-advarsel, som lå der i forvejen).
- `data/plan.json`:
  - `athletes.kennet.days` 21/9 → 3/1 skrevet om efter ugeskabelonen: man styrke A · tir HIT (kun ved normal HRV) · ons svøm · tor Z2 80 + styrke B · fre løb Z2 45 · lør 2 t Z2/durability · søn lang (2 t → 4 t). Recovery-uger 41, 44, 48, 52: åbnere, Z2 80, 2 t søndag, styrke 2 runder uden progression, gang lørdag. Uge 39 og 43 bytter ons/fre (løbeprobe onsdag, svøm fredag). FTP-test tor 24/9 og aerobe prober uændrede; cykelprobe 22/10 som note på torsdagens grundtur.
  - Tirsdag: uge 42 `ss_3x15`, uge 43 `tae_3x12`, uge 45-51 VO2 (`vo2_5x3`, `vo2_4x4`, `vo2_ronnestad_3015`, `vo2_5x3`, `vo2_4x4`, `vo2_10x1`), uge 53 `tae_3x12` som bro til lange intervaller fra uge 1.
  - Søndag: `z2_depottur_2t` → `bjerg_tds_racepace` → `dur_bjergtur_3t` → `dur_sent_i_turen` (uge 43 og 49, hårde) → `z2_langtur_4t` (uge 47, 50, 53) → `bjerg_tds_2x45` + forlængelse (uge 51). Alle med note om at de må køres ude som ren Z2 i samme varighed.
  - Timer pr. uge (alle discipliner): build 10,0-11,1 t, recovery 7,8 t, jul 5,4 t. `bike_library.check_week()` grøn i alle 15 uger.
  - `season2027.weeks` = `programs.tds-2027.weeks` (samme liste): purpose/quota for uge 3-17 matcher nu dagene (verificeret mod `week_load_counts`). Uge 17 (28/12) ændret fra RECOVERY til BASE (tss 440) — to recovery-uger i træk før tre build-uger og Japan gav ingen mening. 2027: purpose pr. uge med søndagens længde og tirsdagens HIT-type; uge 21-22 = Japan (RECOVERY, ski, tss 200); FTP-test flyttet fra uge 21 til tor 18/2 (uge 24); uge 23 = genstart 70 %; uge 49 ændret fra SPECIFIK til TAPER (−25 %, tss 450) så taperen er 3 uger progressivt som rammen foreskriver; uge 48 = sidste lange 8 t. Lejr #1 Mallorca (uge 30) og #2 Alperne (uge 46) står som i forvejen, markeret "ikke booket".
  - `travel`: Japan 24/1-6/2-2027 tilføjet. `updated` = 2026-09-11.
- `data/bike_library.json`: nyt pas `z2_langtur_4t` (FaF 1 Z2 - Langtur 4 t, let, 240 min, ERG) — 4 timer Z2 64-70 % med tre 5-min kadence-100-blokke og energiplan som Depottur. Biblioteket manglede et rent Z2-pas over 3 t; reglen "kun fra biblioteket" holdes ved at udvide biblioteket, ikke ved at opfinde pas i planen. `meta.updated` = 2026-09-11. Ingen eksisterende pas ændret.
- `workouts/zwift/FaF_1_Z2_-_Langtur_4_t.zwo` (ny) + `README.md` regenereret af `build_zwo.py`.
- `scripts/modules/test_proposals.py`: de to tests mod det rigtige forslag fra blok 9 erstattet — blok 9-forslaget testes nu kun som historik (status + 20 ændringer); nye tests for blok 11-forslaget (105 dage, svøm 1×/uge, styrke 2×/uge, lang tur søndag, alle libraryId'er findes, check_weeks tom) og kvoter pr. uge for alle 15 uger.
- `scripts/test_build_workouts_plan.py`: `test_rigtig_plan_har_de_ryddede_fredage` → `test_rigtig_plan_har_de_ryddede_dage` (25/12 ryddet, planen løber til 3/1-2027).

## Ikke verificeret

- Rigtig pytest (CI). Skemaerne og shim-kørslen er grønne, men CI er dommer.
- Intervals/Outlook: `build-workouts.yml` bygger den kommende uge søndag 05:00 UTC — første synk af den nye plan sker søndag 13/9 (uge 38 er urørt, så reelt først 20/9 for uge 39). Kør workflowet manuelt hvis planen skal ses i Intervals før.
- Den nye .zwo skal kopieres til `~/Documents/Zwift/Workouts/187762/` på Mac'en.

## Åbent

- Fastede ture: spørg Martin i næste ugemail før noget skrives ind.
- Mallorca uge 30 og Alperne uge 46: ikke booket. Planen revideres når de ligger i kalenderen.
- Uge 1-3/2027 (4/1-24/1) skrives dag for dag i næste blok — sammen med Japan-ugerne.
