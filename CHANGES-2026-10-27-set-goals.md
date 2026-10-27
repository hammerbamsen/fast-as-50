# 27/10-2026 — kropsmål via forslag (set_goals) + røde blok 11-tests

Kennet 27/10: vægtmål 68 kg / 16 % til 31/1 er ikke realistisk efter virus (72,0 kg / 22,2 %). Nyt mål: under 70 kg til 1/1 — sat til 69,5 kg / 19 %. Mål og plan gennemgås igen med Martin 19/11.

## Ændringer
- `scripts/modules/proposals.py`: ny change-action `set_goals` {programId, goals{weightKg, bodyFatPct}} med intervaltjek (40–150 kg, 3–50 %). Ingen dato, intet at synke. Anvendes som alt andet via `edit_apply` action `apply_proposal`.
- `schemas/proposal.schema.json`: `setGoals` i `changes.oneOf`.
- `scripts/modules/test_proposals.py`: tests for `set_goals` (anvendelse, ugyldige værdier, ukendt program, gennem edit_apply, skema). De to blok 11-tests (`..._plan_matches`, `..._quotas`) var røde på main, fordi senere forslag (Mallorca uge 43, genstart uge 44–48) har ændret ugerne; de springer nu uger over, som et senere accepteret forslag har skrevet om (`_later_weeks`).

## Test
- pytest: 685 passed, 1 skipped (før: 2 failed). `schemas/validate.py` grøn. `node --check sw.js` grøn.
- Planændringen selv sendes som forslag `2026-10-27-mal-1-januar` via plan-edit (ikke commit af plan.json).

## Ikke verificeret
- Dashboardets tekst for måldato (31/1) er ikke datadrevet — kun tallene ændres.
