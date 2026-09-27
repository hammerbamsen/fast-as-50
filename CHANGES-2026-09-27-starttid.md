# 27/9-2026 — starttid i planændringer

Kennet 27/9: en cykeltur rykket til eftermiddag blev lagt kl. 07:15 i Outlook, fordi forslag ikke kunne gemme en starttid.

## Ændringer pr. fil
- `scripts/modules/proposals.py`: `set_day` har et valgfrit felt `time`: `[h, m]` (hele dagen), `{"Ride": [16, 15]}` (pr. disciplin) eller `null` (fjern). Det skrives til `athletes.<a>.timeOverrides[dato]`, som Outlook/Intervals-synk allerede læser. Uden `time` er dagens override urørt.
- `schemas/proposal.schema.json`: `time` er med i setDay.
- `scripts/modules/test_proposals.py`: 1 ny test (skriv/behold/fjern) + 3 nye afvisningscases.

## Test
- pytest: 666 passed, 1 skipped. schemas/validate.py: ok. node --check sw.js: ok.

## Ikke verificeret
- Kun via forslag (chat-vejen). Appens Justér-ark kan endnu ikke sætte en tid.
