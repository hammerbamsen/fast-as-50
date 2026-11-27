# 27/11-2026 — Friels 2. udgave skrevet ind i gaten

Kennet læser *Fast After 50* og bad om at få principperne ind i dashboardet. Research viste
at der er kommet en **2. udgave (VeloPress, maj 2026)** hvor Friel har vendt sin position:
1. udgave sagde at masters-atleter mangler intensitet, 2. udgave siger at de nu laver for
meget intensitet og for lidt lav intensitet. Repoets eksisterende gate-regler blev udledt af
1. udgaves logik. Fem nye regler, valgt af Kennet.

Alle fem er **WARN, ikke HARD**. Klassifikationen af udendørs ture og løb sker på pasnavn og
kan tage fejl; en hård spærring på et gæt ville blokere rigtige planændringer. Kælderpas
læses fra `bike_library` og er sikre.

## Ændringer pr. fil

- `scripts/modules/friel.py`
  - `entry_load()` — ny fælles belastningsklassifikation. `libraryId` →
    `bike_library.load_of()` (autoritativt, jf. CLAUDE.md regel 3), ellers pasnavn mod
    `EASY_NAME_MARKERS` / `HARD_NAME_MARKERS`. Styrke, svøm og vandring returnerer `None`:
    de tæller i samlet belastning, men ikke i max-2-hårde (regel 4).
  - `planned_z5_min()` — planlagte minutter over 105 % af FTP i et kælderpas, beregnet ved at
    gå `steps` igennem rekursivt, så `reps`-blokke ganges med `n`.
  - `edition2_flags()` med regel 1, 2, 3 og 5:
    - **hard_per_week** — maks 2 hårde dage pr. uge, på tværs af discipliner. Hullet den
      lukker: `bike_library.check_week()` tæller kun cykelpas, så et hårdt løb tirsdag plus
      VO2 på cyklen torsdag gik ubemærket igennem.
    - **hard_spacing** — 48 timer mellem hårde pas, 72 når begge er Z5. Måles på tværs af
      ugegrænser.
    - **easy_days_min** — mindst 3 dage om ugen helt lette eller fri (Friels 5-2). Flager kun
      uger der er planlagt hele vejen igennem, så delvist planlagte uger ikke lyser.
    - **z5_per_session** — over ca. 15 min planlagt Z5 i ét pas.
  - Regel 4 lagt ind i den eksisterende `missing_recovery`: grænsen sænket fra 3 til 2
    belastningsuger, og `CAMP`, `SPECIFIK`, `STELVIO` og `PEAK` tæller nu med som belastning.
    Før så reglen kun `BUILD`, så en lejr fulgt af to build-uger slap igennem.
  - Taper- og race-uger er fritaget for regel 1, 2 og 3, som de allerede var for løbereglerne.
- `index.html`
  - `PT_RULE_DA` udvidet med danske navne til de fire nye flag.
  - Nyt `frielCard()` i Krop-fanen efter VO2-kortet. Delt i to lister med vilje: **hvad gaten
    flager** (syv regler, hver med det flagnavn den udløser) og **hvad der er op til dig**
    (stop med 1-2 reps tilbage, tal med lægen før en hård blok, volumen og intensitet går
    modsat, protein 40 g inden 30 min, hvile på efterspørgsel). Uden den opdeling ville
    kortet love mere end gaten holder.
- `scripts/modules/test_friel.py` — 8 nye tests, hver regel isoleret på en mock-plan, plus
  klassifikationen (bibliotek før navn, styrke udenfor) og fritagelsen i taper/race.

## Test

- (a) `python3 -m pytest scripts/modules/ scripts/test_*.py -q` → **751 passed, 1 skipped**
- (b) `python3 schemas/validate.py` → OK
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl

## Hvad reglerne finder på den rigtige plan

Fem flags i alt, så reglerne er ikke støjende. Tre af dem er reelle fejl i den plan der blev
skrevet tidligere i dag:

| Uge | Regel | Hvad |
|---|---|---|
| KU11 | missing_recovery | Lejr #1 er tredje belastningsuge i træk. Lejr #2 fik en forlejr-aflastning (KU14), lejr #1 fik ikke. |
| KU20 | missing_recovery | FTP-test-ugen ligger som tredje belastningsuge efter lejr #3. |
| KU29 | missing_recovery | Tre belastningsuger i træk i TdS-optakten. Lå der før i dag. |
| uge 14 | z5_per_session | `vo2_4x4` har 16 min Z5, ét minut over Friels ca. 15. Står med vilje: hans tal er cirka, og 4×4 er et kendt protokol. |
| uge 4 | consecutive_runs | Lå der før. |

De tre `missing_recovery` kræver en planændring, ikke en kodeændring. Den ligger som næste
skridt og skal gennem et forslag.

## Forbehold

- **Klassifikationen på pasnavn er den svage fuge.** `entry_load()` gætter på pasnavnet når der
  ikke er noget `libraryId`, altså for alle udendørs ture og alle løb. "Gravel 2 t" bliver
  moderat, "Bjerg VO2 4x4 Puig Major" bliver hård. Et pas der hverken har et let eller et hårdt
  markørord falder til moderat — det er det konservative valg, men det betyder at et reelt hårdt
  pas med et neutralt navn ikke tæller med i max-2-reglen.
- **`z5_per_session` kan kun måle kælderpas.** Udendørs pas har ingen `steps`, så lejrenes
  Z5-arbejde på Mallorca kan reglen ikke se. Det er VO2-kortets dosiskurve der dækker dem.
- **Protein-princippet står kun som tekst.** Det kunne kobles til protein-kortet og
  Martin-mailen, men det er ikke gjort.
