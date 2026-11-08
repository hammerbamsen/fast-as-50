# Ændringslog 8/11-2026 — korrekt varighed og TSS i plan-edit-synk

**Problem:** Når en planændring (plan-edit) oprettede pas i Intervals, udledte Intervals varigheden af description-teksten. Svøm: "400m" blev læst som 400 minutter (1200 min i alt). Styrke: kun linjer med tid blev talt med (31 min i stedet for 45), og der kom ingen TSS.

**Ændringer**
- `scripts/modules/intervals_event.py` (ny): `build_payload` (nu med `external_id` og `workout_doc`, som build_workouts) og `corrections`, der finder de felter, der skal PUT'es, når Intervals' tid afviger mere end 60 s fra planen, eller når TSS mangler. Load-estimatet er det samme som i `build_workouts.estimate_load`.
- `scripts/apply_edit.py`: `intervals_create` bruger modulet og PUT'er rettelserne efter oprettelsen.
- `scripts/modules/test_intervals_event.py` (ny): 5 tests (svøm 1200→45 min, styrke 31→45 min + load, cykel røres ikke, planens load bruges hvis den er der, payload).

**Test:** pytest 712 passed / 1 skipped, schemas OK, `node --check sw.js` OK. PUT af moving_time + load er verificeret manuelt i Intervals på event 153233245 (svøm 19/11 → 45 min / 38 TSS).

**Ikke verificeret lokalt:** selve POST→PUT-forløbet mod Intervals (kræver API-nøglen i Actions). Det bliver verificeret ved næste plan-edit.
