# 6/10-2026 — "Åbnere" omdøbt til "Aktivering"

Kennet: "åbnere" er direkte oversat fra engelsk "openers" og giver ikke mening på dansk. Fremover hedder passet **Aktivering**.

## Ændringer
- `data/bike_library.json`: navn "FaF 1 Z2 - Åbnere 60" → "FaF 1 Z2 - Aktivering 60"; purpose-tekst "åbnere" → "aktiveringer". `id` (`z2_aabnere_60`) og tag er uændret, så `libraryId` i plan.json og forslag stadig matcher.
- `workouts/zwift/`: gammel `.zwo` slettet, ny `FaF_1_Z2_-_Aktivering_60.zwo` genereret med `build_zwo.py`; README opdateret.

- `data/bike_library.json`: trinteksten "Åbner" / "Åbner 95+ rpm" → "Aktivering" / "Aktivering 95+ rpm" i 15 pas (kun tekst, ingen watt-tal ændret).
- `scripts/build_workouts.py`: FTP-testens trin "Åbner 5 min" → "Aktivering 5 min".

## Ikke ændret her (kræver plan-edit)
- `data/plan.json` har pasnavnet på 4 datoer (6/10, 27/10, 24/11, 22/12) og trintekster i flere pas samt "åbnere" i ugetekster. Rettes via forslag, ikke commit. Intervals og Outlook følger efter plan-edit.

## Test
- pytest 675 grønne, 1 skipped; `schemas/validate.py` grøn; `node --check sw.js` og index.html inline scripts grønne.
