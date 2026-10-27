# 27/10-2026 — rekalibrering fra i dag: CTL-mål + glidesti (set_weight_plan)

Kennet 27/10: "start fra hvor jeg er nu — ikke hvor jeg skulle have været". CTL 38,7 efter virus; vægt 72,0 kg / 22,2 %.

## Fund
Planens TSS-mål kan ikke levere dens egne CTL-mål. Simuleret med τ = 42 dage giver de oprindelige TSS-mål fra CTL 38,7 i dag CTL 74 på julilejren (mål 88) og 61 på racedagen (mål 82). Det var også tilfældet før virussen. Selve træningen (pas, timer) ændres ikke her — kun målelinjen.

## Ændringer
- `scripts/modules/proposals.py`: ny change-action `set_weight_plan` {programId, weightPlan{startKg, targetKg, bodyFatPctStart, bodyFatPctTarget, maxLossPerWeekKg, cutStartsFrom, targetDate, holdFromMonth, note}} — flettes ind i `programs.<id>.weightPlan`, med intervaltjek og tjek af targetDate > cutStartsFrom efter fletning.
- `schemas/proposal.schema.json`: `setWeightPlan` i `changes.oneOf`.
- `scripts/modules/test_proposals.py`: tests for `set_weight_plan`; set_goals-testen afhænger ikke længere af den rigtige plans mål.
- `scripts/modules/test_body.py`, `test_coach_context.py`: `_plan()` bruger nu glidestien fra 11/9 frosset (`LEGACY_TDS_WEIGHT_PLAN`), så logiktestene med datoer i sep/okt ikke følger rekalibreringer.
- `scripts/modules/test_programs.py`: CTL-kurve og weightPlan testes for sammenhæng i stedet for faste tal.

## Planændring (forslag `2026-10-27-rekalibrering-nu`, via plan-edit — ikke commit)
- CTL-mål uge 8–51 (kalenderuge 44 → 2027/34) = simuleret CTL af TSS-målene fra 38,7. TSS-mål uge 8–12 = genstartspassene: 120 / 280 / 350 / 460 / 440.
- Glidesti: 72,0 kg / 22,2 % fra 2/11 → 69,5 kg / 19 % 1/1 (0,29 kg/uge, loft 0,35), hold fra jan.

## Test
- pytest 697 passed, 1 skipped — både mod nuværende plan.json og mod planen med forslaget anvendt offline. `schemas/validate.py` og `node --check sw.js` grønne.

## Ikke verificeret
- Dashboardets visning efter næste update-kpi-kørsel.
