# 28/11-2026 — W/kg som hovedmål, CTL-peak 80, én faseøkonomi

Tre tal i planen var bygget på forudsætninger der ikke længere gjaldt. Kennet bad om at blive
guidet igennem dem med spørgsmål og valgmuligheder; alle tre valg er hans.

## Hvad der var galt

- **FTP-glidestien gik fra 278 til 320 W.** De 278 var fra en anden effektkilde i juli. Efter
  testen 8/10 er FTP 257, men glidestien fulgte ikke med. FTP-kortet stod derfor rødt med
  "bagud" mod et sæsonmål 25 % over hvor han faktisk er — et mål man aldrig nærmer sig holder
  op med at betyde noget.
- **`ctlPeak: 88`, men ugerne gav 74** og CTL er 29,2 i dag. Kennet accepterede 27/10 den
  realistiske kurve; tallet blev bare aldrig rettet.
- **To fasesystemer.** `phases` bar FTP-mål med de gamle navne og andre ugeintervaller, så
  FTP-kortet sagde "mål 305 (BUILD)" mens fasekortet sagde "Late Base".

## Kennets valg (28/11)

1. **W/kg som hovedtal**, watt noteret ved siden af, begge rekalibreret fra nu.
2. **ctlPeak 80** — mødes på midten mellem 74 og 88.
3. Fasesystemerne **slås sammen** (min anbefaling, som han bad om).

## Kode

- `scripts/modules/proposals.py` + `schemas/proposal.schema.json` — ny action **`set_season`**.
  Hverken `programs[pid].phases` eller `season2027` kunne nås af de seks øvrige actions, så
  FTP-glidestien og CTL-målet kunne kun rettes i hånden — samme type blocker som `phase` var i
  morges. `phases` erstatter hele listen og **valideres for dækning uden huller** fra uge 1 til
  `totalWeeks`: det er netop dækningen `ftp_track.phase_for()` slår op i, og et hul ville give
  "ingen fase" og dermed intet mål på kortet. Listen skrives på både programmet og
  `season2027`, så de to kopier ikke kan drive fra hinanden.
- `scripts/modules/ftp_track.py` — W/kg afgør status når både vægt og `wkgTarget` findes;
  ellers falder kortet tilbage på watt. Nyt felt `primary` siger hvilket af de to der dømmer.
  `seasonWkgTarget`/`seasonWkgStart` og `wkgTarget` pr. fase er lagt i blokken.
- `index.html` — FTP-kortet hedder nu "W/kg — mod 4,28 til TdS", viser W/kg stort og watt plus
  vægt på linjen under. Fasechipsene viser W/kg-målet.
- `scripts/modules/test_proposals.py` — 4 nye tests for `set_season`: skrivning begge steder,
  afvisning af huller i dækningen, af en sidste fase der ikke rammer `totalWeeks`, af ukendte
  fasenavne og sæsonfelter, og at sæsonmål kan sættes alene uden at røre faserne.

## Plan (forslag `2026-11-28-wkg-og-ctl`, 24 changes)

Glidesti i W/kg, med watt som følgetal:

| Fase | Uger | W/kg | ~FTP |
|---|---|---|---|
| Transition | 1-12 | 3,52 | 257 |
| Preparation | 13-17 | 3,60 | 258 |
| Early Base | 18-23 | 3,75 | 263 |
| Late Base | 24-29 | 3,95 | 274 |
| Build 1 | 30-36 | 4,10 | 283 |
| Peak 1 / Stelvio | 37-39 | 4,15 | 286 |
| Build 2 | 41-48 | 4,25 | 293 |
| Peak 2 / TdS | 49-51 | 4,28 | 295 |

295 W er +15 % på ni måneder. Meget af det er genvundet form, ikke ny: han lå på 278-284 på en
anden effektkilde i juli, og CTL er faldet fra over 50 til 29 under sygdommen.

CTL mod 80: Build 2's ugentlige TSS løftet ca. 11 % (snit 506 → 558), peak i uge 48 på CTL 80,
72 på startlinjen. Alle ramper ligger under +8, største er +7 i Alpelejrens uge.
`hoursPerWeekPeak` fra 15 til 17, fordi lejrugen nu er 850 TSS.

Uge 1-12 kaldes **Transition** i både faselisten og ugerne, så de to systemer er enige hele
vejen. Det var et påtvunget ophold efter Médoc og sygdom, og 12 uger er over Friels spænd på
1-4 — men det er historie, og kortet dømmer kun den aktuelle fase.

## Test

- (a) **775 passed, 1 skipped** · (b) skemaer OK · (c) sw.js OK · (d) 3 inline scripts, 0 fejl
- Simuleret mod den rigtige plan: nul nye flags, `phases` identiske i program og season2027,
  og fasekortet og FTP-kortet siger nu det samme i samme uge ("Late Base" begge steder).
- To tests rettet, begge af den slags CLAUDE.md-reglen fra i går advarer mod:
  `test_ftp_track::test_build_status_green_when_at_target` antog at watt afgjorde status, og
  `test_vo2_dose::test_base_ramper...` antog at ugerne i BASE-faseintervallet også havde
  `phase: "BASE"` — det holdt ikke efter omdøbningen. Den sidste måler nu reglen i stedet:
  hver uge skal have det mål dens egen fase giver.

## Stadig åbent

`weightPlan` i planen siger 68 kg og 16 % fedt inden 31/1-2027, selvom målet blev flyttet 22/11
til 70,5 kg og 20,5 % ved check-in med Martin 21/1. Samme slags forældelse som de tre ovenfor.
