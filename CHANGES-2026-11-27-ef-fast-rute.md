# 27/11-2026 — EF på fast rute (Sa Calobra)

## Problemet

`aerobic.py` filtrerer stigningstunge ture væk med `MAX_HM_PER_KM = 15`, fordi GAP
underkorrigerer på stejlt terræn. Fornalutx ligger på 20-25 hm/km. **Alle tre Mallorca-lejre
i 2027 er dermed usynlige for EF** — netop de uger hvor den aerobe base bygges, og hvor Friel
siger at EF er det metrik man skal følge. Filteret er fagligt rigtigt: en bjergtur og en flad
grundtur kan ikke sammenlignes på samme tal. Men så mangler der et mål for lejrene.

Løsningen er ikke at hæve grænsen, som ville gøre tallene usammenlignelige. Den er at måle på
**samme rute**: watt pr. hjerteslag på én kendt stigning, hvor længde, højde og retning er ens
hver gang.

## Ændringer pr. fil

- `scripts/modules/fixed_route.py` (ny)
  - `ROUTES` — Sa Calobra: 9,45 km / 627 hm, tolerance ±1,2 km og ±90 hm (GPS-støj, og man
    starter og stopper sjældent præcis ved skiltet). Flere ruter kan tilføjes.
  - `find_effort(streams)` finder rutens vindue i aktivitetens streams med en two-pointer-sweep
    over `distance` og `altitude`. Tre ting afgør at det bliver stigningen og ikke noget andet:
    - **Vinduet skal begynde hvor stigningen begynder** (de foregående 2 min må ikke have
      været opad) **og slutte på toppen** (de følgende 2 min må ikke gå videre opad). Uden det
      matcher et vilkårligt 9,5 km-stykke midt på Puig Major, som er 14 km / 800 hm og
      indeholder et stykke der ligner Sa Calobra. Verificeret: Puig Major afvises nu.
    - **Stejlest vinder** blandt kandidaterne, så tilkørslen trimmes af og gennemsnitswatten
      bliver stigningens, ikke turens.
    - **Vinduet udvides derefter** til stigningens rigtige grænser, så tiden kan sammenlignes
      med PR'en (35:18) og ikke kun EF'en.
  - `is_candidate()` — forfilter på cykeltype og mindst 500 højdemeter, så der kun hentes
    streams for ture hvor det kan være. `BIKE_TYPES` importeres fra `vo2_dose`, så listen kun
    findes ét sted (QA-fund 4 i dag var præcis den divergens).
  - `merge()` nøgler på aktivitets-id, så en genkørsel ikke laver dubletter.
  - `card()` — retningen er det eneste der betyder noget: ±2 % mellem to forsøg er grænsen,
    under det er det støj. Ét forsøg vises uden dom.
- `scripts/modules/sessions.py` — `get_streams(act_id, types)`, samme endpoint og svarform som
  de to eksisterende stream-kald i filen.
- `scripts/update_kpi.py` — scanner de 35 dages aktiviteter, henter streams for kandidater der
  ikke allerede er i serien, og skriver nye forsøg til `data/fixed_route_ef.json` (nøglet på
  aktivitets-id, så serien overlever at `data.json` skrives forfra hver kørsel).
  `data['fixedRouteEf']` er kortets blok. Ikke-blokerende.
- `index.html` — `fixedRouteCard()` i Krop-fanen over principkortet: nuværende W/slag, retning
  i procent, bedste tid, og de seneste seks forsøg med dato, W/slag, tid, watt og puls.

## Test

- (a) `python3 -m pytest scripts/modules/ scripts/test_*.py -q` → **762 passed, 1 skipped**
  (9 nye i `test_fixed_route.py`: detektion i en hel tur med tilkørsel og nedkørsel, flad tur
  afvises, Puig Major afvises, for kort stigning afvises, stigning med pause giver lavere
  gennemsnitswatt, manglende puls/watt giver ingen EF, forfilteret, merge uden dubletter,
  og alle fire farvetilstande i `card()`)
- (b) `python3 schemas/validate.py` → OK
- (c) `node --check sw.js` → OK
- (d) index.html inline-scripts → 3 scripts, 0 fejl
- Mock hele vejen: syntetiske streams → `find_effort` → `record` → `merge` → `card` → lagt i en
  kopi af det rigtige `data.json` → valideret mod `data.schema.json`. To forsøg en måned fra
  hinanden gav 1,832 og 1,898 W/slag, +3,6 %, "motoren er blevet bedre", bedste tid 34:06.

## Kunne ikke verificeres

- **Detektionen er kun kørt på syntetiske streams.** Intervals' API kan ikke nås herfra
  (nøglen ligger i GitHub-secrets), så første rigtige prøve er en pipeline-kørsel. Risikoen
  ligger i `altitude`-strømmens støj: barometrisk højde svinger, og tolerancen på ±90 hm skal
  måske justeres efter første rigtige Mallorca-tur.
- **Serien starter tom.** Historiske Sa Calobra-ture bliver ikke hentet ind: et 35-dages vindue
  dækker dem ikke, og en backfill ville koste et stream-kald pr. kandidat-tur gennem hele
  historikken. Det er en selvstændig opgave — et engangsscript, ikke pipelinen.
- Kortet er ikke set i en browser, kun syntakstjekket.

## Tre tests gjort indholdsuafhængige i samme commit

`set_actuals`-forslaget flyttede `actualsThroughWeek` fra `medoc-2026`/8 til `tds-2027`/11, og
tre tests blev røde fordi de læste den rigtige `plan.json` og antog den gamle værdi:

- `test_programs.py::test_actuals_through_week_is_program_scoped` tester nu **reglen** — feltet
  gælder det program markøren peger på, 0 for alle andre — uden at låse hvilket program det er.
- `test_friel.py::test_validate_against_real_plan_after_program_switch` henter nu det aktive
  program og dets `actuals_through_week()` pr. dato i stedet for at antage "intet er historisk".
- `test_proposals.py::test_set_actuals_flytter_feltet_til_det_rigtige_program` sætter sit eget
  udgangspunkt i stedet for at låne det fra planen.

Det er fjerde gang i dag dette mønster rammer. QA-agenten foreslog en regel i CLAUDE.md om at
nye tests skal bruge en fixture eller vælge dynamisk; det er ikke gjort, men det bør det blive.
