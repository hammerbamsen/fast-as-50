# 4/10-2026 — pasnavnet "Depottur" udgår

Kennet vil ikke bruge navnet "Depottur" mere. Passet er 2 timers ren Z2 med fast energiplan, og navnet blev misforstået som skiftetræning (brick).

## Ændringer pr. fil
- `data/bike_library.json`: `name` "FaF 1 Z2 - Depottur 2 t" → "FaF 1 Z2 - Lang Z2 2 t"; noten i Langtur 4 t nævner nu "Lang Z2 2 t". Pas-id `z2_depottur_2t` er uændret, fordi 14 plan-entries og historik peger på det.
- `workouts/zwift/`: ny `FaF_1_Z2_-_Lang_Z2_2_t.zwo` (genereret med `scripts/build_zwo.py`), gammel `FaF_1_Z2_-_Depottur_2_t.zwo` slettet, `README.md` og `FaF_1_Z2_-_Langtur_4_t.zwo` regenereret.
- `data/plan.json`: rettes IKKE i denne commit. De berørte pas omdøbes via plan-edit (action `adjust`), så Intervals og Outlook følger med.

## Test
- pytest: 675 bestået, 1 sprunget over
- `schemas/validate.py`: grøn
- `node --check sw.js` og index.html inline scripts: grønne

## Ikke verificeret
- Historiske forslag i `data/proposals/` og `data/martin_signals.md` nævner stadig det gamle navn. De er log og er ikke rettet.
