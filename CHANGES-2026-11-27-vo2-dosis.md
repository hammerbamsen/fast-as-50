# 27/11-2026 — VO2-dosis på dashboardet

Baggrund: Kennet foreslog "ekstra fokus på VO2 og vægt". Vægt er allerede dækket (vægt,
7d-snit, fedtprocent, glidesti, cut-check, mål og W/kg på FTP-kortet), og dashboardets eget
afsnit "Hvorfor ikke bare VO2max" afviser med rette Garmins VO2max: ml/kg/min stiger
mekanisk når vægten falder. Det der manglede, var VO2 som **dosis** — Friel-gaten kender
reglen "1 VO2-stimulus pr. build-uge", men den ser kun planen, ikke hvad der blev kørt.

Måldosis følger Joe Friels dosering af aerob kapacitet: 3-5 min Z5 i prep, ca. 5 min i
tidlig base stigende til ca. 15 min i sen base, ca. 15 min i build/specifik, 0 i
restitutions-, taper- og løbsuger. Friels 2. udgave (maj 2026) flytter vægten mod mere base
og maks. 2 hårde pas pr. uge, så målet er et loft lige så meget som et gulv.

## Ændringer pr. fil

- `scripts/modules/vo2_dose.py` (ny) — Z5-minutter pr. kalenderuge fra Intervals-aktiviteter.
  Cykling måles på watt (`icu_zone_times` zone 5+), løb og resten på puls
  (`icu_hr_zone_times` indeks 4+). Pace-zoner bruges ikke: `compute_run_pace_zone_secs`
  koster ét API-kald pr. aktivitet, og et 5-ugers vindue ville koste 30+ kald.
  Et pas tæller som VO2-stimulus fra 4 min i Z5.
  Farvelogik: grøn ved ≥80 % af målet, gul under 80 % **fra lørdag** (den indeværende uge
  dømmes ikke mandag morgen), gul ved 120-150 %, rød over 150 % eller efter tre afsluttede
  uger under halv dosis. Restitutionsuge med mål 0: grøn ved 0-2 min, gul hvis der blev
  kørt Z5 alligevel.
- `scripts/update_kpi.py` — henter 35 dages aktiviteter, skriver `data['vo2']` og KPI-kortet
  `kpis.vo2`. Ikke-blokerende: fejler modulet, kører resten af pipelinen videre.
- `index.html` — nyt `vo2Card()` i Krop-fanen efter FTP-kortet: ugens dosis, status,
  søjler for de sidste fire kalenderuger med stiplet mållinje pr. uge. Plus KPI-rækken
  "VO2 DOSIS" under Træning. Farver kommer fra pipelinen, ikke fra UI'et.
- `scripts/modules/test_vo2_dose.py` (ny) — 9 tests: zonekilde pr. disciplin, ugebucketing,
  minimumsgrænse pr. pas, måldosis pr. fase, base-rampen 5→15, farver, restitutionsuge og
  streak-reglen.
- `scripts/modules/test_proposals.py` — tre tests fra tidligere i dag låste en bestemt uges
  `blockType` og antallet af rejse-ophold i den rigtige plan.json. De blev røde da
  Mallorca-forslaget blev anvendt. Nu er de indholdsuafhængige: de sammenligner før/efter
  og vælger selv en uge uden Mallorca-ophold.

## Test

- (a) `python3 -m pytest scripts/modules/ scripts/test_*.py -q` → 738 passed, 1 skipped
- (b) `python3 schemas/validate.py` → alle filer OK (data.schema.json har
  `additionalProperties: true`, så `vo2` krævede ingen skemaændring; `kpis.vo2` tilføjes kun
  når blokken findes, fordi kpis-værdier skal være objekter)
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl
- Mock mod rigtige data: `vo2_dose.card()` kørt på data/plan.json med mock-aktiviteter,
  resultatet lagt i en kopi af data.json og valideret mod data.schema.json → OK.
  Den indeværende uge (KU48) er en restitutionsuge med mål 0, så 10 min Z5 ville give gult
  "restitutionsuge, men der blev kørt Z5" — kortet håndhæver Kennets egen beslutning af
  13/11 om kun Z1-2 i uge 46-48.

## Kunne ikke verificeres

- `update-kpi.yml` er ikke kørt endnu, så `data.json` indeholder ikke `vo2` før næste
  pipeline-kørsel. Indtil da viser kortet "Kommer med næste pipeline-kørsel."
- 5-minutters maxwatt (den egentlige kapacitetsmåling) er IKKE med. Den kræver et nyt
  Intervals-kald mod power curve-endpointet og er en selvstændig opgave.
