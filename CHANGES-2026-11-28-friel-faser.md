# 28/11-2026 — Friels faser og prioriteter kodet ind

Kennet fotograferede tabel 6.5 og 6.6 fra *Fast After 50* (1. udgave) og bad om at planen fulgte
dem. En uafhængig QA-agent gennemgik faseforslaget før implementering og fandt fire blockers.
Alle fire er rettet her.

## Hvorfor overhovedet

Planens `BASE` var **én udelt blok på 14 uger**. Friel deler Early og Late Base, og for løb over
4 timer har de modsatte prioriteter: Early Base er styrke først og aerob kapacitet sidst, Late
Base har aerob kapacitet som nummer ét. Planen kunne ikke følge tabellen, fordi den ikke kendte
forskel. Dertil var `BUILD` 13 uger mod Friels 6-9, og der var hverken Peak (1-2 uger), race-uge
eller Transition som faser.

## Kode

- `scripts/modules/friel_priorities.py` (ny) — tabel 6.5 (varigheder) og 6.6 (prioriteter i alle
  tre løbskolonner). Prioriteten kommer nu ét sted fra, så dashboardet, ugebriefen og
  Outlook-markeringen viser det samme. `normaliser()` oversætter "Build 1" → "Build".
  `varighed_ok()` måler en fase mod Friels spænd. `kort()` bygger data.json-blokken.
- `scripts/modules/proposals.py` + `schemas/proposal.schema.json` — **QA-blocker 1:** `phase`
  stod ikke i `WEEK_META_STR` og kunne ikke skrives af nogen af de seks actions. Hele
  faseomlægningen var ikke-implementerbar ad den sanktionerede vej, og CLAUDE.md forbyder at
  ændre plan.json via commit. `phase` er tilføjet med hvidliste (`PHASE_NAMES`), samme mønster
  som `BLOCK_TYPES` fik i går efter "RECOVERYY"-fundet.
- `scripts/modules/vo2_dose.py` — **QA-blocker 2:** med Friels fasenavne faldt `week_target()`
  til `None` for otte uger, fordi `PHASE_TARGET` kun kendte de gamle navne. Kortet ville have
  vist "uden for programmet — ingen måldosis", og den røde streak-regel kunne aldrig udløses.
  `PHASE_TARGET` dækker nu begge navnesæt, og opslaget går gennem `friel_priorities.normaliser()`
  så "Build 1"/"Build 2" rammer "Build". Late Base får 15 min (aerob kapacitet er nr. 1 der),
  Build 15 (vedligehold), Preparation 4, Race og Transition 0.
- `scripts/update_kpi.py` — `data['phase']` skrives efter planTab er bygget.
- `index.html` — nyt `phaseCard()` øverst på I dag: fasen stort, prikker for hvor langt man er,
  fasens formål, og prioritetsrækkefølgen med nummer ét fremhævet. Rødt varsel hvis fasen ligger
  uden for Friels spænd. `seasonStripV2()`s fasebånd er gjort tydeligere og den aktive fase
  markeret — Kennet skrev at det druknede.
- `scripts/modules/test_friel_priorities.py` (ny) — 9 tests, herunder at kolonnen for under 2
  timer vender prioriteten i Build (aerob kapacitet nr. 1 mod nr. 3), så tabellen ikke drifter.

## Planen (forslag `2026-11-28-friel-faser`, 40 changes)

Ti faser, alle inden for tabel 6.5: Preparation 5, Early Base 6, Late Base 6, Build 1 syv,
Peak 1 to, Race 1 én, Transition én, Build 2 otte, Peak 2 to, Race 2 én.

Rettelser efter QA:

- **Blocker 3:** uge 37 havde FTP-test + tærskel = to hårde pas i en aflastningsuge tre dage
  efter hjemkomst fra lejr #3. En test på restgæld giver et for lavt tal, som derefter flytter
  alle zoner ind i Stelvio-tapen. Testen er væk; ét tærskelpas fredag står.
- **Blocker 4:** uge 44 havde tærskel tirsdag og VO2 onsdag — 24 timer mod de 72 i
  `bike_library.meta.rules`. VO2 flyttet til lørdag.
- FTP-testen ligger nu i uge 27, nedtrapningsugen før lejr #1: friske ben, kvote 1 hårdt.
- Uge 35 havde en 5-timers tur med tærskel sent i turen på **samme søndag som rejsedagen** til
  lejr #3. Flyttet til lørdag 8/5, og ugen nedtrappet fra 500 til 430 TSS som de to andre
  før-lejr-uger.
- Styrke 2× skrevet ind i Build 1, Build 2 og begge Peak-faser. Den var forsvundet helt fra
  februar og frem, selvom Friel har den som **nr. 2 i Peak** og projektets princip 5 siger
  2×/uge resten af livet.
- "Maks-styrke 3-6 reps" er droppet: hjemmegymmet har håndvægte til 15 kg og kettlebells til
  20 kg, og 3-6 reps forudsætter 85-90 % af 1RM. Kennets valg 28/11: progressiv overload på
  Functional 4 i stedet.
- Kvote sat eksplicit på alle 39 uger. 22 af dem manglede den, og `plan_tab.py` og
  `coach_context.py` læser en manglende kvote som 0/0 — så coach'en ville have sagt "kvoten er
  brugt" på hver eneste kvalitetsdag.
- Transition ned fra 280 til 150 TSS. Den var sat som en almindelig aflastningsuge.
- Stelvio beskrevet som 5-6 t B-løb og formcheck, ikke "8-9 t bjergtest" — 130 km, 4.500 hm og
  350 TSS siger 5-6.
- Alpelejren har nu en fallback i teksten: bookes den ikke inden 1/6, køres 9-10 t hjemme. Den
  er ellers den eneste eksponering over 8 timer før et 8-11 timers A-løb.
- Madeira 1.-8./12 lagt i `plan.travel`. Turen lå i dagene, men ikke der hvor `friel.py`,
  `adaptation.py` og `plan_tab.py` læser rejse-ophold.
- De fire stigende uger i januar (uge 17-20, 440→510 TSS) **står med vilje**. QA anbefalede en
  aflastningsuge otte uger efter en afsluttet træthedsudredning; Kennet valgte 28/11 at beholde
  dem. Valget og stopklodsen (HRV ned og hvilepuls op) står nu skrevet i ugernes formål, så det
  er et valg og ikke en forglemmelse.

## Test

- (a) 771 passed, 1 skipped · (b) skemaer OK · (c) sw.js OK · (d) 3 inline scripts, 0 fejl
- Simuleret mod den rigtige plan: alle ti faser `varighed_ok: True`, nul nye Friel-flags,
  VO2-måldosis løser korrekt i hver fase (Preparation 4, Early Base 5, Late Base 15, Build 15,
  Peak 0, Race 0, Transition 0), og ingen uge fra 13 og frem mangler kvote.
- Fasekortet er renderet i node mod rigtige data og sendt til Kennet som preview.

## Ikke rettet

- **To fasesystemer side om side.** `programs.tds-2027.phases` bærer `ftpTarget`/`wkgTarget` pr.
  fase med de gamle navne og andre ugeintervaller. FTP-kortet vil sige "mål 305 (BUILD)" mens
  fasekortet siger "Late Base". Bør enten omdøbes eller flyttes til en egen nøgle (`ftpPhases`).
- **`ctlPeak: 88` og `ctlAtRace: 82` kan ikke nås.** Højeste uge-CTL i programmet er 74, og
  race-ugen står på 61. Et gab på 14 og 21 point. Selvstændigt forslag.
- Uge 1-12 beholder deres gamle faser. Fortiden omskrives ikke.
