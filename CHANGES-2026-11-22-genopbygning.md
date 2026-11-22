# 22/11-2026 — genopbygning: uge 48 Mallorca, cut videre, coach-stemme

Kennet 22/11: udredningen er færdig. Fokus er restitution og at komme i gænge med søvn,
sund mad, motion og begrænset arbejde. Kuren kører videre, moderat. Han valgte selv
længere Z1-2-ture i Mallorca (2-3 t) med vandring oveni, og at intet skjules i dashboardet.

## Ændringer pr. fil

- `data/proposals/2026-11-22-mallorca-uge48-genopbygning.json` (ny, status `pending`):
  - `set_weight_plan` på `tds-2027`: kun `note` opdateret. Tal uændret (69,5 kg / 19 %
    pr. 1/1-2027, cut fra 2/11, maks. 0,35 kg/uge). Noten skriver nu Martin-gennemgangen
    19/11, at udredningen er afsluttet, og stopreglen: når restitutionssignalet advarer
    (hvilepuls +2 og HRV −5 % over 14 dage mens vægten falder), spises der til vedligehold.
  - `set_day` 23/11, 24/11, 25/11, 26/11: de fire `Cykel Z2 90 min Mallorca` erstattet af
    2 t / 2,5 t / 2 t / 3 t ren Z2 (56-76 % FTP, samme opbygning som før). Styrke A (23/11)
    og Styrke B (26/11) uændret. Frivillig `Vandring 1,5 t` (Hike, `optional: true`)
    tilføjet 23/11 og 25/11. Samlet cykeltid uge 48: 9,5 t.
  - `set_day` 30/11: noten på `intro_4x3_z34` skærpet — gaten er HRV 47-76 og hvilepuls
    under ca. 47 **tre dage i træk**. Udredningen er ikke længere betingelsen.
  - Ingen intensitet i uge 48. Ingen stigninger på tid.
- `prompts/coach_system.md`: nyt afsnit `# Fase: genopbygning (fra 22/11-2026)` — volumen før
  intensitet, intensitet låst indtil gaten er åben, hvile og søvn omtales som en del af planen,
  cut-advarsel → spis til vedligehold, søvn og arbejde tæller med. Afsnittet fjernes igen, når
  fasen skifter. Intet skjult i dashboardet; kun stemmen er ændret.

## Test

- `python3 schemas/validate.py` — grøn (forslaget validerer mod `proposal.schema.json`).
- `python3 -m pytest scripts/modules/ scripts/test_*.py -q` — 722 passed, 1 skipped.
- `node --check sw.js` — grøn.
- `python3 -m modules.proposals apply-offline 2026-11-22-mallorca-uge48-genopbygning --dry-run`
  → `ok: Godkendt`, 5 datoer (23-26/11 + 30/11). Friel-gate og `bike_library.check_week()` passerer.

## Ikke verificeret

- Live-anvendelsen (`plan-edit` → `apply_proposal`) med Intervals- og Outlook-synk kører efter
  dette commit; `data/edit_result.json` er beviset.
