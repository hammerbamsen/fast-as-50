# 1/10-2026 — Clark 4x4 (120 %) i biblioteket

## Ændringer pr. fil
- `data/bike_library.json`: nyt pas `vo2_4x4_clark` (haard, 59 min, 4 × 4 min @ 120 % FTP, 3 × 30 s åbnere @ 110 %). Eksisterende pas urørte.
- `workouts/zwift/FaF_5_VO2_-_4_x_4_Clark_120.zwo` + `README.md`: genereret med `build_zwo.py`.
- `data/proposals/2026-10-01-vo2-clark-8dec.json`: forslag (pending) — tir 8/12 skifter fra `vo2_4x4` til `vo2_4x4_clark`. Tir 10/11 er uændret.

## Test
pytest 675 grønne, `schemas/validate.py` grøn, `node --check sw.js` grøn.

## Ikke verificeret
- 120 % og åbnernes placering er aflæst fra et skærmbillede af Clarks workout (clarkcycles). Tjek mod videoen.
- Forslaget er endnu ikke anvendt på plan.json.
