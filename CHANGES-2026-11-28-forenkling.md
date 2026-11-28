# 28/11-2026 — Puig Major, styrke som frekvens, og en Krop-fane der er skåret ned

Kennets udgangspunkt: dashboardet er vokset uhensigtsmæssigt, og styrkeprogrammet bruges ikke.
Spørgsmålet han stillede: hvis Joe Friel så det her, hvor ville han gøre det simplere?

## 1. VO2-dosis bliver i Z5 — ingen ændring

Spørgsmålet var, om dosis skulle tælles som Z5 eller som alt over Z4. Den blev i Z5.
Over Z4 er Z5+Z6+Z7, og så tæller hvert sprint på en Z2-tur som VO2-arbejde — præcis den fejl
der blev lukket 27/11 (fund 5). Hans 3-5 min reps ligger på 106-120 % af FTP, altså i Z5.

## 2. EF på fast rute: Puig Major i stedet for Sa Calobra

`scripts/modules/fixed_route.py` — ny rute `puig_major` (12 km / 700 hm, Kennets eget tal for
Fornalutx → toppen) og ny konstant `DEFAULT_ROUTE`, som `find_effort`, `record` og `card` nu
bruger. Sa Calobra bliver liggende i `ROUTES`, så gamle forsøg kan vises; kortet filtrerer på
rute. Baggrund: Sa Calobra-serien stod tom ("ingen forsøg endnu"), fordi det ikke er den tur
han kører. En længere stigning giver desuden et roligere W/slag.

`scripts/modules/test_fixed_route.py` — tre tests der satte Sa Calobras geometri som deres eget
udgangspunkt, siger det nu eksplicit med `route="sa_calobra"`. To nye tests:
- turen starter for foden af stigningen uden fladt tilløb (Fornalutx-tilfældet) — vinduet
  findes stadig, 12 km / 700 hm på ca. 50 min,
- kortet filtrerer på rute, så gamle forsøg på en anden rute ikke blander sig. Testen vælger
  standardruten dynamisk, så den ikke låser sig til navnet.

## 3. Styrke: frekvens i stedet for program

`scripts/modules/body.py` — ny `strength_frequency()`, lagt på `data['strength'].frequency`:
`{target, thisWeek, weeks: [{start, n, hit}]}` for de seneste 8 uger inkl. den indeværende.
Uger loggen ikke dækker helt springes over — en delvist dækket uge er ukendt, ikke nul.

`index.html` — `strengthCardHtml()` viser nu "1 / 2 denne uge" plus otte prikker. Øvelseslisten
på I dag (`todayStrengthHtml`) og hjælpefunktionerne `_stExRows` og `_stNext` er slettet.
Progressionsmotoren (`strength_progression.py`, `data.strength.next`) regner stadig, men vises
ikke: Kennet bruger den ikke, og det der afgør om man er funktionel som 70-årig, er at passene
bliver lavet.

## 4. Krop-fanen: ti blokke → tre

`renderBody()` er nu **krop** (hero, vægtgraf, tiles, fedtprocent) · **fitness** (W/kg) ·
**form** (HRV, hvilepuls, søvn). VO2-dosis, EF på fast rute, cut-tjekkets seks signaler,
Friels principper og vanerne er flyttet til en ny `renderDeeperNumbers()` under
**Mere > Dybere tal**. Intet tal er fjernet eller holdt op med at blive beregnet.

## 5. Forklaringerne foldet væk

Ny hjælpefunktion `why(html, label)` + `.why`-CSS. Brødteksten på VO2-kortet og EF-kortet, og
fasestigen med historikken på W/kg-kortet, ligger nu bag "HVORFOR ▾". En forklaring skal læses
første gang man ser et kort, ikke 200. gang.

## Test

Fire CI-trin lokalt: **822 passed, 1 skipped** · skemaer OK · `sw.js` OK · index.html's tre
inline-scripts OK. Desuden kørt i et rent virtuelt miljø med præcis CI's fire pakker (823
passed — `python-docx` mangler der, og en test skipper lokalt af samme grund).

Ud over `node --check` er `renderBody`, `renderDeeperNumbers` og `strengthCardHtml` kørt i en
vm-kontekst med den rigtige `data.json` for at fange en tom skærm, som syntakstjekket ikke
ser. Alle tre rendrer.

## Ikke verificeret

- `renderMore` kunne ikke køres i vm-konteksten: harnesset indlæser kun hovedscriptet, og
  `SW_STATE` ligger i et andet script-block. `kpis` normaliseres også først ved load. Begge er
  begrænsninger i mit testopsæt, ikke fejl i siden.
- Puig Majors 12 km / 700 hm er Kennets tal. Tolerancerne (±1,5 km, ±100 hm) skal bekræftes
  mod den første rigtige tur fra Fornalutx; rammer vinduet ved siden af, er det tolerancen der
  skal justeres, ikke logikken.
- `strength.frequency` findes først i `data.json` efter næste pipeline-kørsel. Kortet viser
  ingenting indtil da i stedet for at fejle.
