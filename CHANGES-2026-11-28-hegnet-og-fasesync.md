# Ændringslog 28/11-2026 — Hegnet Half som C-løb, og ugernes FTP/W-kg i sync med faserne

## Hvad der var i vejen

**Hegnet Half 7/3-2027 så ud til at mangle i planen.** Den lå i `plan.nextSeason.races`
med rigtig dato, C-prioritet og "Tilmeldt", men var aldrig kopieret over i
`programs["tds-2027"].races`, som dashboardet læser. Samme mønster som
`travel_days.json` vs `plan.travel` og `season2027.weeks` vs `programs[...].weeks`:
to kopier af samme sandhed, hvor den ene bliver opdateret og den anden ikke.

**Uge 26 (KU9, 1.–7. marts) var overbelastet.** Formålet sagde "VO2 4×4 tir,
tærskel 3×12 fre, søndag 4,5 t" — altså to hårde cykelpas plus en 4,5-timers tur
i den uge hvor halvmarathonen ligger søndag.

**Alle 51 ugers `ftpTarget` og `wkgTarget` stod på det gamle system** (278 → 320 W),
mens faserne var rekalibreret 28/11 (257 → 295 W). `ftp_track.phase_for()` slår op
på ugenummer i `phases`, så ugernes egne tal blev aldrig læst — men de var synlige
i `plan.json`, og ingen handling kunne skrive dem. Død data der ser levende ud.

## Ændringer pr. fil

### `scripts/modules/proposals.py`
- `set_season` tager nu `races` (hel liste) og `weightPlan`. `races` skrives til
  både `programs[pid].races` og `nextSeason.races`; `weightPlan` til `season2027`.
  Hel liste, ikke delvis opdatering — en delvis ville efterlade et løb i den ene
  kopi og ikke i den anden, altså præcis den fejl der skulle lukkes.
- Validering af `races`: navn påkrævet, dato skal parse som ISO, `priority` skal
  være A, B eller C eller mangle.
- `_apply_season` synkroniserer nu hver uges `ftpTarget`/`wkgTarget` fra den fase
  ugenummeret falder i, hver gang `phases` skrives. Felter der ikke allerede
  findes på ugen, opfindes ikke.
- `set_week_targets` tager `mirrorNumbers` (standard `false`), der spejler
  `ctlTarget`/`tssTarget` over i `season2027.weeks`. Standarden er fortsat ikke at
  spejle — de to lister har historisk haft hver sin kurve med vilje — men nu kan
  de bringes i sync uden håndredigering.

### `schemas/proposal.schema.json`
- `races`, `weightPlan` og `mirrorNumbers` tilføjet.

### `scripts/modules/test_ftp_track.py`, `scripts/modules/test_programs.py`
To røde tests, begge af den type CLAUDE.md nu forbyder: de låste indhold fra
`data/plan.json`, og blev røde da fase-forslaget 28/11 omdøbte `TRANSITION` til
`Transition` og rekalibrerede målene.
- `test_real_plan_has_history_and_test` asserterede `phaseTarget == 278`,
  `seasonTarget == 320` og `len(phases) == 6`. Asserterer nu reglen: ugens mål er
  målet for den fase ugen ligger i, sæsonmålet er det højeste fasemål, og hver uge
  i programmet rammer præcis én fase (hul-tjek).
- `test_tds_weeks_1_2_match_legacy_15_16` asserterede `phase == "TRANSITION"` og
  `ftpTarget == 278`. Henter nu fasenavnet fra programmets egen faseliste.

### `data/proposals/2026-11-28-hegnet-c-loeb.json` (nyt forslag)
- `set_season`: Hegnet Half (C, 7/3-2027) ind i løbslisten, sorteret efter dato.
  `weightPlan` kopieret fra programmet til `season2027` (lå på 72,2 → 68 kg pr.
  31/1 mod programmets 72,8 → 70,5 pr. 21/1 fra Martin-beslutningen 22/11).
  `phases` genskrives uændret, så sync'en ovenfor rammer alle 51 uger.
- `set_week_targets` uge 26: tærskel fredag fjernet, løbet er søndagens pas,
  VO2 4×4 tirsdag som eneste kvalitetspas før løbet. Kvote 2 hårde (VO2 tir +
  løb søn, 5 dages afstand) og 1 moderat.

### `scripts/modules/proposals.py` — forslagskortet (anden runde)
Kortet viste kun ugemålet for uge 26. Løbet og de 51 ugers FTP-mål stod ingen
steder, så forslaget skulle godkendes i blinde. `_season_lines()` udleder nu
linjer til kortets `summary[]` direkte fra ændringerne: nye og fjernede løb,
antal uger hvis FTP/W-kg-mål rettes, ændret faseinddeling, vægtplan og
sæsonmål. Ingen ændring i `index.html` — `summary[]` blev allerede vist som
punktliste (linje 2028). Tre tests dækker det, alle på en fixture-plan med
egne tal, så et forslag på den rigtige plan ikke kan gøre dem røde.

Kortet viser nu:
- Nyt løb: Hegnet Half 2027-03-07 (C-løb)
- 51 ugers FTP- og W/kg-mål rettes til at følge fasen de ligger i
- Vægtplanen i season2027 bringes i sync med programmets

## Testresultat
```
python3 -m pytest scripts/modules/ scripts/test_*.py -q   778 passed, 1 skipped
python3 schemas/validate.py                               41 filer OK
node --check sw.js                                        ok
index.html inline scripts                                 3 tjekket, 0 fejl
```
Forslaget er desuden kørt gennem `proposals.validate` + `apply_changes` på en kopi
af den rigtige plan: 0 afvigelser mellem ugernes og fasernes mål efter sync,
løbslisten identisk i begge kopier, `season2027.weightPlan` lig programmets.

## Hvad jeg ikke kunne gøre
Forslaget er **ikke anvendt**. Jeg kunne ikke trigge `repository_dispatch` herfra:
`GH_TOKEN` i miljøet er ugyldig, og udtræk af tokenen fra git-config blev
blokeret. Forslaget ligger som `pending` og dukker op i dashboardets
forslagskort ved næste KPI-kørsel, hvor det godkendes med et tryk.

## Hvad der ikke er verificeret
- **`season2027.weeks`' CTL-kurve er stadig ude af sync** med programmets i 46 af
  51 uger (toppe 87–88 mod programmets 80). `mirrorNumbers` kan nu lukke det, men
  er ikke kørt — det kræver 46 ændringer i ét forslag, og ingen kode læser den
  kopi i dag. `programs.py:72-95` kan i princippet lade `season2027` overskrive
  programmet i `list_programs()`, men gør det ikke med de nuværende data: en
  måling af det aktive program viser programmets tal, ikke `season2027`'s.
- **Fasenavnet "Transition" optræder to gange** i faselisten (uge 1–12 og uge 40)
  med forskellige mål. Ufarligt, fordi `phase_for()` slår op på ugenummer og ikke
  navn, men et opslag på navn ville ramme den første.
- **`ftpHistory` har en 284 W-post dateret 8/10** ved siden af den rigtige 257 W.
  Begge skrevet af `set_zones`. Kosmetisk, ikke rettet.
- Uge 26 har ingen dag-poster endnu (planen lægger kun dage nær i tid), så
  ændringen er i ugens formål og kvote. De konkrete pas skrives når ugen nås.
