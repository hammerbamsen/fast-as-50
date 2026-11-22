# 22/11-2026 — vægt-milepæl: 70,5 kg pr. 21/1-2027

Kennet har check-in med Martin 21/1-2027 og vil have den dato som næste milepæl på vægt,
med baseline i dag.

## Ændringer pr. fil

- `data/proposals/2026-11-22-milepael-21-januar.json` (ny, status `pending`):
  `set_weight_plan` på `tds-2027`:
  - `startKg` 72,0 → 72,8 (7-dages snit 21/11), `bodyFatPctStart` 22,2 → 22,6 (14-dages snit)
  - `cutStartsFrom` 2026-11-02 → 2026-11-22, så glidesti og "bagud"-status regner forfra
  - `targetKg` 69,5 → 70,5, `bodyFatPctTarget` 19 → 20,5, `targetDate` 2027-01-01 → 2027-01-21
  - `holdFromMonth` 2027-01 → 2027-02, `maxLossPerWeekKg` uændret 0,35
  - Note: 0,27 kg/uge over 8,6 uger. Jul 24/12-1/1 på vedligehold. 69,5 kg / 19 % er næste
    milepæl efter Japan (februar-marts). Stopregel uændret.
- Programmets `goals` (69,5 kg / 19 %) er **ikke** ændret — sæsonmålet står.

## Begrundelse for tallet

Baseline 72,8 kg. 8,57 uger til 21/1. 70,5 kg kræver 0,27 kg/uge; 69,5 kg ville kræve
0,39 kg/uge over loftet, og 69,5 pr. 1/1 ville kræve 0,55 kg/uge. Faktisk rate de seneste
fire uger: −0,1 kg/uge. Genopbygning efter sygdom + jul gør alt over 0,3 kg/uge urealistisk.

## Test

- `python3 schemas/validate.py` — grøn.
- `python3 -m pytest scripts/modules/ scripts/test_*.py -q` — 722 passed, 1 skipped.
- `node --check sw.js` — grøn.
- `apply-offline --dry-run` → `ok: Godkendt`, 0 datoer (ingen dag-ændringer, ingen synk).

## Ikke verificeret

- Krop-fanens nye glidesti vises først efter næste `update_kpi`-kørsel.
