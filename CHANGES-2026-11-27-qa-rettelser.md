# 27/11-2026 — rettelser efter QA-review

En separat agent reviewede dagens tre commits uden at have skrevet koden. Verdikt: ingen
blockers, CI grøn, de forbudte filer urørte, livedata korrekt. Men syv reelle fejl, og én
alvorlig test-blindhed. Alle rettet her. Agentens nummerering er bevaret i kommentarerne.

## Ændringer pr. fil

- `scripts/modules/proposals.py`
  - **Fund 1:** `quota.haard`/`quota.moderat` blev valideret mod et frit 0-7-interval, så et
    forslag kunne skrive `quota.haard: 5` og dermed bryde CLAUDE.md regel 3 ad en vej
    `bike_library.check_week()` ikke ser. Loftet kommer nu fra
    `bike_library.meta().rules.maxHaardPerWeek` / `maxModeratPerWeek` (2 og 2).
  - **Fund 2:** `blockType` var fri tekst. En tastefejl som `RECOVERYY` gik igennem, og så gav
    `vo2_dose.week_target` mål 15 i stedet for 0, og `friel._phase()` returnerede `""` — altså
    blev en restitutionsuge målt som en build-uge, og fasereglerne slog stille af. Nu valideres
    mod `BLOCK_TYPES`.
- `schemas/proposal.schema.json`
  - Samme whitelist som `enum`, og `quota`-maksimum sænket fra 7 til 2.
  - **Fund 3:** koden tillod en upsert-patch på label alene, skemaet krævede `start` på hvert
    ophold. Da CI-trin (b) validerer alle `data/proposals/*.json`, kunne et sådant forslag
    aldrig committes — den annoncerede patch-vej var ubrugelig og opdagedes først som rødt CI.
    `start` er nu kun påkrævet i `mode: replace`, hvor listen erstatter alt.
- `scripts/modules/vo2_dose.py`
  - **Fund 4:** cykeltypelisten divergerede fra resten af repoet, så et pas Intervals leverer
    som `Gravel`, `MountainBike` eller `Cyclocross` faldt tilbage på puls. Pulsen hænger efter
    ved 2-4 minutters reps, så dosis blev underrapporteret 60-80 %, og projektets egen regel
    ("cykling måles på watt") blev brudt stille. `BIKE_TYPES` matcher nu `sessions.py:197`.
  - **Fund 5:** begge grene summede zone 5 **og opefter**. Z6/Z7 er anaerobt og neuromuskulært
    arbejde, ikke VO2max-arbejde: et pas med 0 s i Z5, 300 s i Z6 og 180 s i Z7 blev målt som
    8 min VO2-dosis, så sprints på en Z2-tur kunne tippe kortet til rødt. Watt tæller nu kun
    `secs[4]`. Puls tæller stadig `[4:]`, fordi pulszonerne ikke har et meningsfuldt loft over
    Z5 på samme måde som watt.
  - **Fund 6:** når `target` var `None` sprang hele farveblokken over, så kortet viste minutter
    ved siden af teksten "ingen data". Egen status nu: "uden for programmet — ingen måldosis".
  - **Fund 12:** `PHASE_TARGET["TAPER"] = 4` var død konfiguration — `TAPER` ligger i
    `BLOCK_ZERO` og rammer altid mål 0, hvilket docstringen også sagde. Fjernet. `PEAK` tilføjet
    med 4 min (Friels Peak: 3-5 min Z5-fartlek hver tredje dag), så den fase ikke falder til
    `None` midt i programmet.
  - **Fund 14:** `wk["week"]` kunne rejse `KeyError` i stedet for at returnere `None`.
- `scripts/modules/sessions.py` + `scripts/update_kpi.py`
  - **Fund 7:** `get_activities_since()` returnerede `[]` både ved "ingen aktiviteter" og ved
    HTTP-fejl. Et 500-svar fra Intervals en lørdag gav derfor `z5Min=0` og en falsk dom
    "under måldosis" — og tre sådanne uger i træk ville give rødt "tre uger med under halv
    dosis". Et stille API-udfald blev altså en træningsdom. Ny `strict=True` returnerer `None`
    ved fejl; pipelinen springer så kortet over og lader det stå på "kommer med næste
    pipeline-kørsel". Standardadfærden er uændret, så eksisterende kaldere ikke rammes.
- `data/travel_days.json`
  - **Fund 15:** filen er en dublet af `plan["travel"]`, og teksterne var allerede divergeret
    (lejr #1 "høj belastning" vs. "volumenlejr"). Alle felter synkroniseret fra plan.travel,
    som er kilden, og en `_note` tilføjet der siger hvilken fil der er hvad. Rettede felter:
    lejr #1 og #3's `label_during`, plus Norge-turens `end` og `travel_home_date`, som var
    forældede fra før.
- `scripts/modules/test_vo2_dose.py`
  - **Fund 8 (den alvorlige):** testfixtures lagde kun tid i Z1 og Z5, så en forskydning af
    zone-indekset fra Z5 til Z4 bestod alle ni tests — modulets vigtigste egenskab var utestet.
    Fixtures har nu Z4-tid som standard, plus `test_zone_indeks_er_z5_og_kun_z5_for_watt` og
    `test_alle_cykeltyper_maales_paa_watt`.
  - **Fund 9:** `test_base_ramper...` bestod også med `BASE_RAMP = (15, 15)`, altså med rampen
    slået fra. `test_restitutionsuger_taeller_ikke_i_streak` brugte `weeks=3`, så
    `len(under_halv) >= 3` aldrig kunne blive sand, og assertionen var opfyldt uanset logikken.
    Begge rettet, og ny `test_base_rampen_rammer_begge_endepunkter` på en fixture hvor første og
    sidste base-uge er kendt.
  - **Fund 10:** `kpi()` var helt utestet, men skriver direkte til `data.json`'s kpis-kontrakt.
    Ny `test_kpi_kontrakten`.
  - **Fund 11:** farve- og statustests låste uge 28's og 29's `blockType` i den rigtige
    plan.json — netop det et forslag nu kan ændre. De kører nu mod en fast fixture-plan `FIX`.
    Kun fasereglen testes mod den rigtige plan, og da uden at låse en bestemt uge.
- `scripts/modules/test_proposals.py`
  - **Fund 11:** metadata-testen satte `blockType: "CAMP"`, `location: "Mallorca"` og
    `ctlTarget: 66` — præcis de værdier planen nu har i uge 28, så tre assertions ville også
    bestå hvis patchen ikke gjorde noget. Bruger nu værdier der ikke findes i planen.
    Rejse-testen låste labelen "Japan (ski) med Eva" og dens startdato; den vælger nu det
    første ophold dynamisk.

## Test

- (a) `python3 -m pytest scripts/modules/ scripts/test_*.py -q` → **743 passed, 1 skipped**
  (fem nye tests)
- (b) `python3 schemas/validate.py` → alle filer OK
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl
- Validering kørt direkte mod begge veje: `quota.haard: 5` og `blockType: "RECOVERYY"` afvises
  nu af både `proposals.validate()` og JSON-skemaet. En upsert-patch uden `start` accepteres af
  begge; samme patch i `mode: replace` afvises af begge.
- **Mutationstest af det rettede modul** (kopi uden for repoet, modulet gendannet bagefter).
  Alle seks indførte fejl fanges nu, inkl. den der før slap igennem:

  | Mutation | Resultat |
  |---|---|
  | `secs[4]` → `secs[3]` (watt-zone forskudt) | 7 failed |
  | `hr[4:]` → `hr[3:]` (puls-zone forskudt) | 7 failed |
  | `BASE_RAMP = (15, 15)` (rampe slået fra) | 2 failed |
  | `BIKE_TYPES` → kun `("Ride",)` | 1 failed |
  | `MIN_SESSION_MIN = 1` | 1 failed |
  | streak-grænse 3 → 99 | 1 failed |

## Ikke rettet, og hvorfor

- **Fund 13** (`block_type`-parameteren i `week_target` bruges kun af tests): den er en del af
  kontrakten og bliver brugt af de fem Friel-regler i næste commit. Beholdt med vilje.
- **Fund 16** (commit `7105278` med forslagsfilen har ingen `CHANGES-*.md`): kan ikke rettes
  bagud uden at skrive historien om. Forslagsfilen er sin egen dokumentation, og
  `CHANGES-2026-11-27-lejre-og-ugemetadata.md` henviser til den.
- **Skønhedsfejlen** ved et lille mål: 7 min Z5 i en TRANSITION-uge (mål 4) udløser rødt med
  teksten "for meget Z5 — Friel: maks ca. 15 min pr. pas", hvilket er selvmodsigende. Teksten
  bør skelne mellem "over ugens mål" og "over 15 min i ét pas". Rettes med regel 5 i næste
  commit, hvor loftet pr. pas bliver en rigtig regel.
