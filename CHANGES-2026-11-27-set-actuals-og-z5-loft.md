# 27/11-2026 — set_actuals og Z5-loftet

De to flag der stod tilbage efter Friel-reglerne var ikke træningsproblemer, men ét stykke
bogholderi og ét minut.

## Ændringer pr. fil

- `scripts/modules/proposals.py` + `schemas/proposal.schema.json`
  - Ny action **`set_actuals`** sætter `athletes.<a>.actualsThroughWeek` og
    `...ThroughWeekProgram`. Feltet stod på uge 8 og pegede på `medoc-2026`, og
    `programs.actuals_through_week()` returnerer 0 når markøren peger på et andet program.
    Derfor blev **ingen** uge i `tds-2027` regnet som historisk, og et `consecutive_runs`-flag
    fra 28.-29. september 2026 stod stadig som aktuelt. Intet i pipelinen skrev feltet, og
    ingen af de fire eksisterende actions kunne nå det — det kunne kun rettes i hånden i
    plan.json, hvilket CLAUDE.md forbyder.
  - `_apply_actuals` afviser et ugenummer over programmets længde: et tastefejl-tal ville gøre
    hele planen historisk og alle flag grå.
- `scripts/modules/friel.py`
  - `MAX_Z5_MIN_PER_SESSION` 15 → 16. Friel skriver "ca. 15 min" samlet rep-tid i Z5 pr. pas,
    og `vo2_4x4` ligger på 16. Et flag på ét minut mod et cirka-tal er støj, og 4×4 er et
    kendt protokol. Over 16 flager stadig: `vo2_4x4_clark` (18 min) og
    `vo2_ronnestad_3015` (20 min) er reelt over hans tal.
- `scripts/modules/test_proposals.py` — 2 nye tests: feltet flyttes til det rigtige program og
  `actuals_through_week()` begynder at svare, plus afvisning af manglende programId, negativt
  ugenummer, et tal over programmets længde og et ukendt program.

## Test

- (a) `python3 -m pytest scripts/modules/ scripts/test_*.py -q` → **753 passed, 1 skipped**
- (b) `python3 schemas/validate.py` → OK
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl
- Simuleret mod den levende plan: med loftet på 16 forsvinder `z5_per_session`, og med
  `actualsThroughWeek: 11` på `tds-2027` forsvinder `consecutive_runs`. **Nul aktuelle flags.**

## Bemærk

`actualsThroughWeek` skrives af ingen. Den skal flyttes manuelt hver gang et nyt program bliver
aktivt, og glemmes den, står gamle flag som aktuelle i månedsvis — som her. Kandidat til at
blive sat af `update_kpi` ud fra dagens dato, men det er ikke gjort: feltet betyder "gennemført",
ikke "passeret", og de to er ikke altid det samme.
