# Blok 14 — styrke: check-in hver 4. uge + falsk fejl fjernet (11/9-2026)

Tests: 641 passed (shim; pywebpush springes over). Skemaer grønne. node --check grøn.

## Hvad
- **Falsk fejl "workout_doc har ingen trin" på styrkepas** (event_structure_warnings, vist som fejl i dashboardet): Intervals bygger ikke trin for WeightTraining, og passet køres efter beskrivelsen — ikke fra uret. Regel 2 (INGEN_TRIN) springer nu WeightTraining over. Regel 1 (struktureret beskrivelse) gælder stadig.
- **Styrke-check-in hver 4. uge i stedet for hver 14. dag** (Kennets ønske 11/9: 14 dage var for tæt). Første check-in stadig søn 4/10, derefter 1/11, 29/11, 27/12 … Samme spørgsmål, samme progression.

## Filer
- `scripts/modules/event_structure.py`: `_NO_STEP_TYPES = {'WeightTraining'}`, INGEN_TRIN undtager dem. Test `test_styrke_uden_trin_er_ok`.
- `scripts/modules/strength_progression.py`: `CHECKIN_INTERVAL_DAYS = 28`. Tests opdateret (1/11, 2/11).
- `index.html`: tekst "uændret næste 4 uger" + kommentar.
- `data/workout_library.json`: progression-tekst "hver 4. uge".
