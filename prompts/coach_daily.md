# Dagens opgave

Det er {weekdayName} {date}. Lav dagens vurdering ud fra KONTEKST nedenfor og svar via `coach_output`.

1. `oneThing`: den ene handling der betyder mest i dag. Prioritér: readiness LOW / TSB under gulvet → aflast dagens pas; misset nøglepas → flyt eller drop, aldrig "indhent"; cut aktiv og `deltaVsPlan` over planen → én kost-handling fra principperne; ellers dagens pas præcist (navn, minutter, ERG/ikke ERG).
2. `training`: dagens pas (plan vs. udført), ugen indtil nu (`week.completed` / `missed` / `remaining`), CTL mod `ctlTarget` set i lyset af `blockType`, aerobt flag hvis sat.
3. `body`: vægt og fedt på 7-dages snit mod plan/cut. Retning kun efter reglen. Ingen kostdetaljer ud over principperne.
4. `habits`: AF-dage (`afWeek` af `afTarget`, dage med 3+ genstande), protein-dage, søvn, energi. Kort.
5. `bigPicture`: hvor er han i programmet, og hvorfor ser ugen sådan ud.
6. `weekFocus`: {weekFocusInstruction}
7. `warnings`: kun reelle handlingspunkter (72 t-brud, kvote overskredet, TSB under gulv, readiness LOW på en hård dag, cut-signal). Sæt `action` kun når en konkret plan-redigering løser det.

KONTEKST (JSON):
```json
{context}
```
