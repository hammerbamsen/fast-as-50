# Ændringslog 26/9-2026 — coach-vurdering flyttet til I dag og gjort kortere

## Ændringer pr. fil
- `index.html`
  - Coach-vurderingen er fjernet fra Plan-fanen (både `renderPlan` og ugevisningen).
  - TRÆNER + DIÆTIST-kortet på I dag viser nu: én linje (bigPicture, max 180 tegn), en OBS-liste med coachens advarsler (max 3, uden dem banneret øverst allerede viser) og en fold "Hele vurderingen" med de tre afsnit, ↻ og tidsstempel.
  - bigPicture gentages ikke inde i folden. Tekstfarve i folden rettet til det mørke kort.
- `prompts/coach_system.md`, `scripts/modules/coach.py` (tool-skema): training/body/habits 1-2 korte sætninger med kun det der kræver opmærksomhed; bigPicture ÉN sætning, max 160 tegn.

## Test
- pytest 660 passed / 1 skipped, schemas/validate.py OK, node --check (sw.js + inline scripts) OK.
- Visuelt tjekket i Chromium ved 393 px (lukket og åben fold).

## Ikke verificeret
- Den kortere prompt slår først igennem ved næste coach-generering (ny aktivitet, vægtændring eller AF-ændring). Længden af det nye output er ikke set endnu.
