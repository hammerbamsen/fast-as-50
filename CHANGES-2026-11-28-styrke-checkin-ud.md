# 28/11-2026 — Styrke-check-in'et er ude

Check-in'et hver 4. uge spurgte om ben og overkrop for at fodre `strengthProgression`, som
afgjorde vægte og reps i styrkekortet. Da kortet samme dag blev lavet om til frekvens, blev
check-in'et et spørgsmål, hvis svar ikke længere nåede skærmen. Kennets beslutning: ud.

## Kode

- `index.html` — kortet i I dag (`ckCardHtml`), gem-flowet (`ckSave`) og deres tilstand
  (`CK`, `CK_KEY_PREFIX`, polling) er slettet, i alt ca. 80 linjer. Linjen "check-in venter i
  I dag" er væk fra styrkekortet. Tre kommentarer der pegede på check-in'et er rettet.
- `scripts/modules/body.py` — `build_strength` returnerer ikke længere `checkin`, og kalder
  ikke `strength_progression.build_checkin`. Docstringen siger hvorfor.
- `scripts/modules/test_strength_progression.py` — testen hed
  `..._and_checkin`; den asserterer nu at nøglen er væk, og at `frequency` er der i stedet.
  `build_checkin()` har sine egne tests og er stadig dækket.

## Det der bliver liggende, og hvorfor

`strength_progression.py` med `build_checkin()`, plan-edit-handlingen `strength_checkin` og
felterne `strengthCheckin`/`strengthProgression` i plan.json er urørt. De er testede, de gør
ingen skade, og at fjerne dem ville røre plan-kontrakten og `edit_apply` — det er en større
ændring end den Kennet bad om. `data.strength.next` beregnes stadig, fordi planen og
Word-masteren navngiver passene efter den.

Konsekvens: svarer nogen alligevel på et check-in (fx via et gammelt kald), opdateres
progressionen stadig i plan.json. Det ses bare ikke, og der er ikke længere nogen vej til det
fra appen.

## Test

Fire CI-trin lokalt: 822 passed, 1 skipped · skemaer OK · `sw.js` OK · tre inline-scripts OK.
`renderToday`, `renderWeek`, `renderBody`, `renderDeeperNumbers` og `strengthCardHtml` kørt i
vm-kontekst med den rigtige data.json — alle rendrer. `renderMore` kan som før ikke køres i
harnesset (`SW_STATE` ligger i et andet script-block).
