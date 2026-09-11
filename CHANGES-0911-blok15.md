# Blok 15 — chat-vejen: forslag direkte fra Claude uden push (11/9-2026)

## Hvad
Claude (Cowork) kan nu ændre planen fra chatten uden git push og uden at nogen klikker på workflows:
Claude bygger et forslag (samme format som `data/proposals/*.json`), sender det fra dashboard-siden i Chrome til Worker'ens `/plan-edit` som `apply_proposal` med forslaget inline i `params.proposal` (payload < 64 KB ≈ 6–8 uger). `plan-edit.yml` kører samme gate som Plan-fanen, committer plan.json, synker Intervals + Outlook for de berørte datoer og sender Martin-signal. Testet 11/9 kl. 11:08 (request r20260911-chatvej-1, commit 2f83244, gate Godkendt, 28/9 synket).

Kræver kun at Mac'en er tændt med Chrome (app-koden ligger i dashboardets localStorage). Virker uanset om Kennet skriver fra Mac eller iPhone.

## Ændring
- `scripts/apply_edit.py`: `proposal_decide(..., inline=)` — findes forslagsfilen ikke i repoet, oprettes den fra det inline forslag (status accepted, dates_changed, commit). Før: ikke-fatal fejl "findes ikke i repoet" og ingen historik.
- `scripts/modules/github.py`: `gh_put` med `sha=None` opretter en ny fil (sha udelades af body).

Tests: 641 passed (shim). Ingen skema-ændringer.
