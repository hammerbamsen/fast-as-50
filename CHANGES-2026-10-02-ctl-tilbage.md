# CTL-mål uge 40-45 tilbage til oprindelige (2/10-2026)

Årsag: Fredag 2/10 er rejsedag, så uge 40 ender langt under TSS 508. Løftet fra `ctl-recalib-2026-09-14` rulles tilbage for uge 40-45. Valgt af Kennet 2/10.

## Ændringer
- `data/proposals/2026-10-02-ctl-tilbage.json` — nyt forslag, anvendt offline (`modules.proposals apply-offline`).
- `data/plan.json` — `tds-2027` uge 4-9 (kalenderuge 40-45):

| Uge | CTL før → efter | TSS før → efter |
|---|---|---|
| 40 | 55 → 51 | 508 → 480 |
| 41 | 53 → 50 | 271 → 250 |
| 42 | 56 → 53 | 441 → 420 |
| 43 | 58 → 56 | 454 → 440 |
| 44 | 56 → 55 | 267 → 260 |
| 45 | 58 → 57 | 447 → 440 |

Oprindelige værdier hentet fra `data/plan.json` i commit `74cdd58^`.

## Ikke ændret
Uge 38-39 (afsluttet), alle træningspas, uge 46 og frem, peak-, race- og camp-uger.

## Test
pytest 675 bestået / 1 sprunget over, `schemas/validate.py` grøn, `node --check sw.js` og index.html inline-scripts grønne.

## Ikke verificeret
Hvordan coachen og Plan-fanen vises efter næste pipeline-kørsel. Appen viser nye mål efter sync.
