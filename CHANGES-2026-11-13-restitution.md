# CHANGES 2026-11-13 — restitution uge 47-51

Kennet er stadig træt efter sygdom (EKG og hjerte er tjekket). Planen skrues ned: uge 46-47 kun Z1-2, uge 48 maks. 90 min Z2, uge 49 første korte intensitet, hårde pas i uge 50-51 kun hvis uge 49 gik godt.

## Filer
- `data/bike_library.json`: to nye pas
  - `z2_rolig_60` (let, 60 min) — ren Z2 uden aktiveringer (z2_aabnere_60 har 4×2 min @85 % = Z3).
  - `intro_4x3_z34` (moderat, 62 min) — 4 × 3 min @90 % FTP, 3 min pause.
- `workouts/zwift/`: FaF_1_Z2_-_Rolig_60.zwo og FaF_4_Taer_-_Intro_4_x_3.zwo genereret med build_zwo.py; README opdateret.
- Selve planændringen sker via forslaget `2026-11-13-restitution-uge47-51` (plan-edit), ikke via commit.

## Test
- pytest: 722 passed, 1 skipped. schemas/validate.py grøn. node --check sw.js grøn. index.html uændret.

## Ikke verificeret
- De nye .zwo-filer skal kopieres til ~/Documents/Zwift/Workouts/187762/ på Mac'en (Intervals-pas bygges fra plan.json).
