# 27/11-2026 — ugemarkering i Outlook + søndagsbrief

To ønsker fra Kennet: en markering i kalenderen for hver uge, så han kan læse hvad det er for
en uge, og en påmindelse søndag 06.30 om hvad der er planlagt i den kommende uge og hvad der
skal laves om. Begge rører `.github/workflows/`, så det her er en branch + PR, ikke et direkte
push til main (CLAUDE.md).

## Ugemarkering i Outlook

- `scripts/modules/week_marker.py` (ny, ren logik) — emne, body, Graph-payload og
  fingeraftryk.
  - **Emne:** `KU11 · CAMP · Mallorca — Lejr #1: volumen og aerob base`. Gentofte udelades,
    fordi det er standard og bare fylder. Afkortes ved 120 tegn.
  - **Body:** fase, blok, sted, CTL- og TSS-mål, kvote, formål, nøglepas, note, rejse og løb.
  - **Heldags, `showAs: free`** — markeringen må ikke blokere tid eller forveksles med et pas.
  - **Fingeraftryk** af de felter markeringen viser, skrevet som `sync:<hash>` i body. Er
    fingeraftrykket uændret, røres begivenheden ikke. Uden det ville hver kørsel slette og
    genoprette 40 begivenheder.
  - **Kategorien heder `Ugeplan`, ikke `Træningsuge`.** `build_workouts.outlook_delete_by_date`
    sletter alt hvor kategori eller emne indeholder "ning" (fra "Træning"), så en
    `Træningsuge`-kategori ville blive ryddet af træningssynken. En race-uge hvis formål
    nævner "B-løb" ville desuden blive ramt af samme substring-filter på emnet.
- `scripts/build_workouts.py` — **heldagsvagt** i det løse slettefilter: en heldagsbegivenhed
  er aldrig et træningspas. `$select` hentede ikke `isAllDay`, så det er tilføjet. De to andre
  slettesteder (`sync_outlook.py`, `apply_edit.py`) matcher kategorien eksakt og var sikre.
- `.github/workflows/scripts/sync_week_markers.py` (ny) — Graph-kaldene. Én `calendarView`
  over hele vinduet frem for et kald pr. uge. Opretter manglende, patcher ændrede, springer
  uændrede over, fjerner dubletter og markeringer på mandage der ikke længere er programuger.
  `DRY_RUN=1` viser hvad der ville ske uden at skrive.
- `.github/workflows/week-markers.yml` (ny) — søndag 05:00 UTC (en halv time før briefen, så
  kalenderen er opdateret når pushen kommer), plus `workflow_dispatch` med program, vindue og
  dry-run, plus `repository_dispatch: week-markers`.
- **Vinduet er som standard denne uges mandag og fremad** — markeringer på uger der er forbi
  er støj, og de kan ikke ændres alligevel. Det giver 40 markeringer nu.

## Søndagsbrief

- `scripts/modules/week_brief.py` (ny, ren logik) — bygger push-beskeden for den **kommende**
  uge:
  - Titel: `KU49 · BASE · 460 TSS`
  - Body: antal pas fordelt på discipliner, de hårde pas ved navn, og **hvad der skal rettes**
    — Friel-flagene for netop den uge, oversat til kort dansk ("over 2 hårde pas", "for få
    lette dage"). Er der intet, står der "Intet at rette."
  - **Er ugen slet ikke lagt endnu**, siger beskeden det direkte: `KU49 er ikke lagt endnu`
    med blok, TSS-mål og formål. Det er den hyppigste årsag til at en uge ender som
    improvisation.
  - Body klippes ved 220 tegn, så den kan læses på en låseskærm.
- `scripts/send_push.py` — ny `run_send_week_brief()` på samme `_send_to_kennet`-kerne som
  aften-nudgen og alerts. `PUSH_MODE=week`.
- `.github/workflows/send-push.yml` — cron `30 5 * * 0` og `week` tilføjet til `mode`-inputtet
  så den kan testes manuelt.
- `.github/workflows/health.yml` + `scripts/health_report.py` — det nye workflow registreret
  med en uges forventet interval, jf. CLAUDE.md om at holde listen i synk.

## Test

- (a) `python3 -m pytest scripts/modules/ scripts/test_*.py -q` → **778 passed, 1 skipped**
  (16 nye: 8 i `test_week_marker.py`, 8 i `test_week_brief.py`)
- (b) `python3 schemas/validate.py` → OK
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl
- YAML parset for alle tre ændrede workflows.
- Kørt mod den rigtige `plan.json`: 51 uger giver gyldige emner under 120 tegn, hvert
  fingeraftryk kan læses tilbage ud af body. Søndagsbriefen for 29/11 gav
  `KU49 · BASE · 460 TSS` / "9 pas: 3 styrke, 3 vandring, 2 løb, 1 cykel. Intet at rette."
- En test fastholder at kategorien ikke må indeholde "ning", så fælden ikke genopstår.

## Kunne ikke verificeres

- **Ingen af de to har talt med Microsoft Graph eller en push-service herfra.** Azure-secrets
  og VAPID-nøglen ligger i GitHub, så første rigtige prøve er en kørsel. Kør
  `week-markers.yml` med **dry-run slået til** først: den viser hvad der ville blive oprettet
  uden at skrive i kalenderen.
- **Søndag får to pushes:** den daglige 06:00 og briefen 06:30. Forskellige tags, så de
  erstatter ikke hinanden. Skal det være én, skal den daglige springe søndag over.
- **Sommertid:** GitHub-cron kender kun UTC, så `30 5 * * 0` bliver 07:30 om sommeren. Samme
  forskydning som de øvrige cron-linjer i filen lever med.
