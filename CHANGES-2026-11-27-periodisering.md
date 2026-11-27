# 27/11-2026 — periodiseringsoverblik på I dag + testregel i CLAUDE.md

## `CLAUDE.md`

Ny ufravigelig regel: **tests må ikke låse indhold i `data/plan.json`.** Mønstret gav røde
tests seks gange på én dag — hver gang et forslag ændrede blockType, et rejse-ophold eller
`actualsThroughWeek`, og hver gang så fejlen ud som en kodefejl. Reglen peger på de to veje der
virker (fixture-plan, eller vælg uge/ophold dynamisk) og på at man skal assertere reglen frem
for værdien.

## `index.html` — `seasonStripV2()` på I dag-fanen

Ligger lige under ugestriben, over compliance-kortet. Hele programmet i én stribe:

- **Søjlehøjde** = ugens TSS-mål, så periodiseringens form er synlig: base der stiger, lejre
  der stikker op, aflastningsuger der falder.
- **Farve** = blockType. Blå nuancer for base, orange for build, rød-brun for specifik og
  Stelvio, grøn for lejr, grå for recovery, sand for taper, rød for race.
- **▲** over en løbsuge (rød for A-løb, orange for B), **●** under en lejruge, og ramme om
  denne uge.
- **Fasebånd** nedenunder med navn hvor segmentet er mindst fire uger bredt.
- **Nedtælling:** "næste lejr om N uger · Stelvio om N uger".
- **NU** og **NÆSTE** med blockType, TSS-mål, rejse-ophold og ugens formål.
- Foldet liste med **de næste otte uger** — ugenummer, blockType og formål.

Alt læses fra `data.json` → `planTab.weeks`, som pipelinen allerede skrev. Ingen nye data,
ingen beregning i UI'et.

## Test

- (a) pytest → se nedenfor
- (b) `python3 schemas/validate.py` → OK
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl
- **Kortet er faktisk renderet**, ikke kun syntakstjekket: funktionen blev kørt i node mod det
  rigtige `data.json` og gav 51 søjler, 3 løbsmarkeringer, 5 lejremarkeringer, fasebånd med
  seks faser og "NU KU48 RECOVERY · 440 TSS". En standalone preview-fil blev sendt til Kennet.
