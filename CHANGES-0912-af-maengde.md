# AF-niveauer efter mængde (12/9-2026)

Log-arkets undervalg ved "Ja" er nu **1–2 genstande** (gul) / **3+ genstande** (rød) i stedet for valgt / bare skete. Kennets beslutning 12/9.

- Lagring uændret: Intervals `Alkohol` 0/1/2. Ingen migrering — dage 4/9–11/9 logget som valgt/bare skete beholder samme farve (1 = gul, 2 = rød). Før 4/9 stadig rød (`KIND_CUTOVER`).
- `checkin.ALKOHOL_KIND` → `{1: 'faa', 2: 'mange'}`; `af_kind` og `habits.afKinds7` bruger de nye nøgler. Coach-prompter (system/daily/sunday) rettet: `mange` > 0 nævnes først, `faa` er neutralt.
- index.html: knapper, legend, farvelogik (`habitsWeekCard`, `renderLogDots`, `renderLogSheet`, `logPick`).
- Ikke rørt: princip 02 "Alkohol er et bevidst valg" (Mere → Regler). Den passer ikke længere til målingen — ret teksten hvis mængde-modellen er den endelige.
- 622 tests grønne, `node --check` på sw.js + inline scripts ok. Ikke verificeret i browser.
