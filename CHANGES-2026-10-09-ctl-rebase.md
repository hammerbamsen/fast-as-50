# Forslag: CTL-pejlemærker uge 41-53 (9/10-2026)

Udløst af påmindelsen efter FTP-testen 8/10 (kalenderuge 41).

## Fund
- Projektionen i Plan-fanen bygger på `tssTarget` pr. uge (`friel.project_fitness`), ikke på summen af de enkelte pas. Pas har ingen TSS-værdi i plan.json.
- Fra CTL 47,4 (9/10) kræver målene ca. 615 TSS i uge 42 og 500-550 i BASE-ugerne. De nuværende TSS-mål er 420-500. Projektionen ender derfor 4-7 CTL-point under pejlemærkerne.
- Programuge 18+ (uge 1/2027 og frem) har ingen dage i plan.json, så projektionen falder dér. Det er en separat mangel.
- FTP står på 257 W (var 278 W). `ftpHistory` har to `set_zones` den 8/10: 284 W og derefter 257 W.

## Ændringer
- `data/proposals/2026-10-09-ctl-rebase-base.json` — nyt forslag, status `pending`. Kun `ctlTarget` for tds-2027 programuge 5-17 (kalenderuge 41-53) sættes til projektionen med de nuværende TSS-mål. Ingen TSS-mål, pas, peak, race eller camp røres. Intet er anvendt; det kræver accept.

## Test
- `schemas/validate.py` grøn, `node --check sw.js` grøn.
- pytest: 671 bestået, 4 fejler (`test_interval_reps.py`: `test_bike_zone_watts_fra_ftp`, `test_bike_reps_paa_watt`, `test_bike_target_fra_workout_doc`, `test_hometrainer_z3_trigger`). De fejler også uden denne ændring: testene forventer zoner fra FTP 278, og plan.json har nu 257.

## Ikke verificeret
Om 257 W er den rigtige testværdi (se 284 → 257 ovenfor). Testen i `test_interval_reps.py` bør bruge en fast fixture i stedet for live plan.json.
