# 3/11-2026 — plan 9/11 → jul + Sa Calobra Zwift Video

## Ændringer pr. fil
- `data/bike_library.json`: nyt pas `bjerg_sa_calobra_video` (FaF 6 Bjerg - Sa Calobra Zwift Video): 15 min opvarmning, 45 min på 86 % FTP @ 72 rpm, 10 min nedvarmning. `erg: false` (Zwift Video er fri kørsel), load moderat, 70 min.
- `workouts/zwift/`: .zwo genereret med `build_zwo.py`.
- `data/proposals/2026-11-03-plan-til-jul.json`: forslag for 9/11–27/12 (49 datoer). Anvendes via plan-edit (apply_proposal), ikke commit af plan.json.

## Indhold i forslaget (Kennets valg 3/11)
- 10–12 t/uge. Tir VO2, tor Sa Calobra Zwift Video. Styrke 3×/uge (A-B-A / B-A-B).
- Mallorca 22.–27/11: udendørs Z2 2–2½ t, rigtig Sa Calobra tir 24/11 (kontrolleret), kropsvægtstyrke. Rejsedage fri.
- Madeira 1.–8/12: 3 vandringer à 3 t, løb Z2, kropsvægtstyrke. VO2 man 30/11 før afrejse.
- Uge 52 recovery, fri 24.–25/12.

## Test
- pytest: 702 passed, 1 skipped. schemas/validate.py grøn. node --check sw.js ok.
- Gate (apply-offline på kopi): Godkendt uden advarsler, 49 datoer.

## Ikke verificeret
- Om Zwift Video kan køre opvarmning før ruten — Kennet opvarmer på en flad Watopia-rute.

## Tillæg 3/11 kl. 08 — Sa Calobra som to pas
- `data/bike_library.json`: nyt pas `opvarmning_15` (ERG, 15 min, let, tag "opvarmning"). `bjerg_sa_calobra_video` uden opvarmning: 45 min på 86 % + 10 min ned = 55 min. Watt uændret.
- `scripts/modules/test_bike_library.py`: pas med tag "opvarmning" skal være over 10 min (ellers 20 min).
- `data/proposals/2026-11-03-sa-calobra-to-pas.json`: 10/11, 19/11, 9/12, 17/12 → Opvarmning 15 + Sa Calobra Video 55.
- Test: 707 passed. Skema grønt. Gate (kopi): Godkendt.
