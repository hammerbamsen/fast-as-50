# 27/11-2026 — ugemetadata i forslag + tre Mallorca-lejre 2027

Baggrund: Kennet har lagt tre træningsblokke på Mallorca i Outlook (14-21/3, 11-21/4 og
9-14/5 2027). Planen havde én ikke-booket lejr i uge 30 (KU13, 29/3). Et forslag kunne
indtil nu kun ændre `ctlTarget`/`tssTarget`, så flytning af en lejr krævede håndredigering
af plan.json — i strid med reglen om, at plan.json kun ændres via `edit_apply`.

## Ændringer pr. fil

- `scripts/modules/proposals.py`
  - `set_week_targets` tager nu også `blockType`, `location`, `note`, `purpose`,
    `keySession` og `quota{haard,moderat}`. `null` fjerner feltet. Mindst ét af
    tal-/metafelterne skal angives.
  - Metadata spejles i `season2027.weeks` for den uge der har samme ugenummer **og**
    samme startdato. `mirrorSeason: false` slår spejlingen fra. Tal spejles ikke: de to
    lister har hver sin CTL-kurve (programs 55-67 vs season2027 70-83).
  - Ny action `set_travel` (`mode: upsert` (standard) | `replace`) skriver
    `plan["travel"]`, sorteret på startdato. Upsert kan patche et kendt ophold på label
    alene; et nyt ophold uden `start` afvises i apply, hvor planen kan læses.
  - `target_changes_for_data` returnerer `metaAfter`, så forslagskortet viser tekstændringer.
- `schemas/proposal.schema.json` — `setWeekTargets` udvidet, nyt `setTravel`-def i `oneOf`.
- `scripts/modules/test_proposals.py` — 6 nye tests: metadata + spejling, `mirrorSeason:
  false`, `null` fjerner felt, upsert-fletning og sortering, camp-uge i Friel-gaten efter
  `set_travel`, og afvisning af dårlige datoer/ukendte felter.
- `data/travel_days.json` — de tre lejre tilføjet (læses af `coach.get_travel_label`).

## Test

- (a) `python3 -m pytest scripts/modules/ scripts/test_*.py -q` → 730 passed, 1 skipped
- (b) `python3 schemas/validate.py` → alle filer OK
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl

## Kunne ikke verificeres

- Selve planændringen (uge 28/30/32/33/36 m.fl.) ligger i et separat forslag og køres via
  `plan-edit`; den er ikke en del af dette commit.
- `friel._camp_weeks` markerer hver kalenderuge et Mallorca-ophold rører. Lejr #1 starter
  søndag 14/3, så KU10 får også camp-gulvet -35. Harmløst i en nedtrappet uge, men værd at
  huske hvis KU10 senere får mere belastning.
