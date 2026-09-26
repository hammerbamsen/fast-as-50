# Ændringslog 26/9-2026 — dagstal på vægt- og fedtfeltet

## Hvorfor
Under cuttet (fra 21/9) erstattede "forventet X" dagens måling på VÆGT- og FEDT-felterne i I dag. Dagstallet var ikke synligt nogen steder for vægt.

## Ændringer pr. fil
- `index.html` (I dag, KPI-felter): under fase `cut` viser feltet nu både dagstal og forventning.
  - VÆGT: `7d-snit · dag 72,3 · forv. 72,1` (før: `7d-snit · forventet 72,1`)
  - FEDT: `14d-snit · dag 21,4 · forv. 21,8` (før: `14d-snit · forventet 21,8`)
  - Mangler dagens måling, udelades "dag"-delen. Fase `pre` og `hold` er uændrede.

## Test
- pytest: 660 passed, 1 skipped
- schemas/validate.py: OK
- node --check sw.js + index.html inline scripts: OK

## Ikke verificeret
- Visuel ombrydning af den længere tekst i det smalle felt på iPhone.
- sw.js er ikke bumpet — app-shell er stale-while-revalidate, så ændringen vises efter næste genindlæsning.
