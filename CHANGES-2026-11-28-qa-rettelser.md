# Ændringslog 28/11-2026 — QA-rettelser på set_season og fasekortet

QA-subagent kørte mutationstest på `b51bc7a` + `33cc0c6` og fandt 16 fejl, heraf
tre blokerere. Mutationsscoren var **12 af 24 fanget** — og alle 12 slupne lå i
`_apply_season`, altså netop den kode der skriver i planen. Den er nu dækket:
**11 af 11 tidligere slupne mutationer fanges**, plus den tolvte verificeret
manuelt.

## Blokerere

### 1. Forslaget gjorde en test rød når det blev anvendt
`_apply_season` synkroniserede `ftpTarget`/`wkgTarget` på `programs[pid].weeks`,
men ikke på `season2027.weeks`, som bærer de samme felter.
`test_tds_weeks_1_2_match_legacy_15_16` sammenligner de to lister og ville være
blevet rød dagen efter godkendelsen — præcis den fejltype CLAUDE.md-reglen
handler om, og den regel blev skrevet i samme commit som fejlen.

Synken rammer nu begge lister. Verificeret ved at anvende forslaget på en
kasseret kopi og køre hele pakken ovenpå: 799 grønne, skemaer grønne.

### 2. Synken flyttede tallene, men ikke ugens fasenavn
Flyttede et forslag en fasegrænse, fik ugen det nye tal og beholdt det gamle
navn. `friel_priorities` og Plan-fanen læser `weeks[].phase`, `ftp_track` læser
faselisten — de to kort ville sige hver sit. Navnet synkroniseres nu med.

### 3. `races[].date` accepterede et tal
`date.fromisoformat(str(r.get("date")))` normaliserede intet. Fra Python 3.11 er
`date.fromisoformat("20270307")` gyldig, så `20270307` slap gennem valideringen
og landede råt i planen. Derefter: `programs.next_race()` kastede `TypeError`
("<" mellem str og int) — kaldt fra `update_kpi.py`, så dashboard-opdateringen
var faldet — og `plan.schema.json` havde afvist filen i CI-trin b. Datoen skal
nu være en streng og gemmes normaliseret.

## Øvrige rettelser

- **Kortet tiede om ændret dato og prioritet** (fund 4). Det sammenlignede kun
  navne-mængder, så A-løbet kunne flyttes et år og nedgraderes uden en linje.
  Sammenligner nu (navn, dato, prioritet) og skriver hvad der ændrede sig.
- **`nextSeason.races` fik et 2026-løb** (fund 5). Hele programlisten blev
  kopieret over, så CPH Half 2026-09-20 landede i 2027-sæsonens liste.
  Filtreres nu på `nextSeason.year`.
- **`set_season.weightPlan` havde ingen rigtig validering** (fund 6). `{}` tømte
  planen, og kortlinjen var hårdkodet til "bringes i sync med programmets".
  Kører nu `_validate_weight_plan`, og linjen skrives ud fra en faktisk
  sammenligning.
- **To `set_season` på samme program** lod den sidste vinde i tavshed (fund 7).
  Dubletvagt tilføjet, som de øvrige actions har. Fejlbeskeden for ukendt action
  nævnte ikke `set_season`; rettet.
- **Fire uoverensstemmelser mellem skema og kode** (fund 8): float `ftpTarget`,
  `priority: null` og dato som tal blev accepteret af koden men afvist af
  skemaet — et forslag koden godkendte kunne ikke committes. Og `format: date`
  blev ikke håndhævet, fordi `validate.py` ikke bruger en FormatChecker; skemaet
  har nu et `pattern` i stedet. Samme type fejl som `set_travel` tidligere.
- **`_season_lines` krakkede på ugyldige races** (fund 9). Pipelinen kalder
  `summarize_for_data` uden `validate()`, så et håndskrevet forslag nåede
  hertil; `build_data_proposals` fangede exceptionen, men forslaget forsvandt
  lydløst fra kortet. Tåler nu ikke-objekter.
- **`mirrorNumbers` overskrev `ctlTarget`** selv når forslaget kun nævnte
  `tssTarget` (fund 10) — `if k in wk` læste ugens nuværende værdi. Spejler nu
  kun de nøgler changen selv angiver.
- **`mirrorNumbers` var en lydløs no-op** når startdatoen afveg (fund 11). Nu en
  `ValueError` der siger hvilken uge og hvilken dato.
- **En fase uden `ftpTarget`** efterlod ugerne på de gamle tal, så de viste 278
  som fasemål samtidig med at `ftp_track` sagde "intet fasemål" (fund 12).
  Feltet fjernes nu fra ugen. En fase der kun sætter det ene af de to mål
  afvises.
- **De to omskrevne tests var for løse** (fund 13). `test_real_plan_has_history_
  and_test` sammenlignede `phase_for` med sig selv — mutationer der fik
  `phase_for` til altid at returnere første eller sidste fase slap igennem — og
  bestod også hvis alle mål faldt til 0. Henter nu faselisten uafhængigt,
  verificerer at `phase_for` rammer rigtigt for hver af de 51 uger, og
  assarterer bånd (150-500 W, 2-7 W/kg) og monotoni frem for værdier.
  `test_programs` tjekker nu fasenavnet for alle uger, ikke kun uge 1.
- **Fasekortet fremhævede begge "Transition"** (fund 14). `index.html` slog op på
  navn, og fasen findes to gange (uge 1-12 og uge 40) med hver sit mål.
  `ftp_track` leverer nu `week`, og UI'et fremhæver på interval.

## Forslaget `2026-11-28-hegnet-c-loeb.json` omskrevet (fund 15)

Uge 26 sagde to ting på én gang: programmets `purpose` planlagde VO2 tirsdag,
tærskel fredag OG 4,5 t søndag — samme søndag som løbet — mens
`season2027`-tvillingen havde en note om Hegnet som **B-løb** og
`blockType: RACE`. Og forslagets egen formålstekst påstod at fjerne et
tærskelpas fredag, som ikke fandtes som dagspost (ugen har ingen dage endnu).

Ugen sættes nu til ét udtryk i begge kopier: C-løb, `blockType: BUILD` (et
C-løb er træning, ikke et mål, så ugen bliver ikke en løbsuge), VO2 tirsdag som
eneste kvalitetspas, laktattærskel udgår, note rettet fra B til C.

Bemærk hvad gaten IKKE kunne kontrollere: `check_weeks` kører kun på de datoer
`set_day` rører, og forslaget har ingen `set_day`-changes. Kvoten
`{haard: 2, moderat: 1}` er derfor en hensigt, ikke en målt kendsgerning —
`athletes.kennet.days` slutter 2027-01-03.

## Testresultat
```
python3 -m pytest scripts/modules/ scripts/test_*.py -q   799 passed, 1 skipped
python3 schemas/validate.py                               grøn
node --check sw.js                                        grøn
index.html inline scripts                                 3 tjekket, 0 fejl
```
Plus: forslaget anvendt på en kasseret kopi → 799 grønne og skemaer grønne
**efter** anvendelse. Og mutationstest: 11 af 11 tidligere slupne fejl fanges,
den tolvte (`mirrorNumbers` uden start-tjek) verificeret separat.

## Hvad der ikke er rettet
- `season2027.weeks`' CTL-kurve afviger stadig fra programmets i 46 af 51 uger.
  `mirrorNumbers` kan lukke det, men er ikke kørt — ingen kode læser kopien.
- `vo2_dose.py` slår fasen op på navn (samme latente fejl som fund 14).
  Ufarlig i dag, fordi feltet kun bruges til BASE-rampen.
- `vo2_dose.card(None, ...)` giver samme svar som `card([], ...)`, så en
  API-fejl ville se ud som nul VO2-minutter. Pipelinen fanger det før kaldet
  (`if _acts_35d is None: spring over`), men funktionen burde selv sige nej.
- `_validate_season` accepterer løb i fortiden og dubletter af samme løbsnavn.
- `ftpHistory` har stadig en 284 W-post dateret 8/10 ved siden af den rigtige
  257 W. Kosmetisk.
