# Blok 16 — plan-indbakke i Outlook: ændringer fra chatten uden Mac (11/9-2026)

## Hvorfor
Chat-vejen fra blok 15 kræver at Mac'en er tændt (Chrome bærer app-koden). Kennets Mac er tit lukket. Cowork-sessionen kan ikke nå GitHub eller Worker'en, men den kan skrive i Outlook via Microsoft 365-connectoren — og GitHub Actions har allerede Calendars.ReadWrite på kalenderen (Outlook-synken).

## Hvordan
1. Claude opretter et kalender-event den 1/1-2030 (parkeringsdato, showAs free): subject `FAF-INBOX <forslag-id>`, body = base64 af plan-edit-payload'en (samme JSON som Worker'en dispatcher: action, entryId, params, confirmedWarn).
2. `plan-inbox.yml` (cron */20, reelt 1-3 t; eller manuelt) kører `scripts/plan_inbox.py`: henter events på parkeringsdatoen, kører hver payload gennem `scripts/apply_edit.py` (samme gate, plan.json-commit, Intervals + Outlook for berørte datoer, Martin-signal), læser resultatet i `data/edit_result.json` og sletter eventet ved status ok. Afvist → subject `FAF-INBOX-AFVIST … — <gate-besked>` og eventet bliver stående.
3. Ingen nye hemmeligheder, ingen Azure-ændringer.

## Filer
- `scripts/plan_inbox.py` (ny), `scripts/test_plan_inbox.py` (ny, 2 tests).
- `.github/workflows/plan-inbox.yml` (ny). `health.yml`: navnet tilføjet. `docs/PIPELINE.md`: ny række.

## Ikke verificeret
End-to-end kræver push + første kørsel. Testes med et forslag straks efter push.
