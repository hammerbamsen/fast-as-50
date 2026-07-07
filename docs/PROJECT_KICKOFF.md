# Fast as Fifty — Projekt: Redigerbart plan-website (kickoff)
*Anker for det store projekt. Startet i lang session; fase 1 bygges i frisk samtale.*

## Mål
Ét system hvor Kennet OG Eva kan se og ændre deres workouts fra en webside.
Sandhed bor ét sted; alt andet genereres derfra. Friel som hård filter.

## Arkitektur
- **Sandhed:** `data/plan.json` (begge atleter, alle uger, hver dag som struktureret workout).
- **Pipeline:** `build_workouts.py` refaktoreres til at LÆSE plan.json (i dag hårdkodet).
  Rækkefølge bevares: plan.json → Intervals → Outlook → dashboard.
- **Website `plan.html`:** rullende 3-uger + fuld plan, faner Kennet/Eva,
  kalibreret CTL-projektion, Friel-flags pr. uge, planlæg-uger-frem inline.
- **Write-back:** edit → server-side Friel-gate → plan.json-commit → pipeline
  (GET+slet+POST+verifikation), concurrency-sikret (som af.html-mønsteret).
- **Word-snapshot:** genereres fra plan.json → OneDrive. Excel pensioneres.

## Friel-filter (kodet, testet — skal være server-side gate)
- TSB-gulv -30 (-35 camp) · CTL-ramp max 8 (blød 5) · max 3 løb/uge
- VO2 1x/build-uge · recovery-uge efter 3-ugers blok · undgå fortløbende løb
- QA fandt reelle flags: uge 1 (4 løb), uge 3 (TSB -36), uge 5/8/11 (aggressiv ramp)

## CTL-projektion — KRITISK
Naiv lærebogsmodel afviger op til 16,8 CTL-point fra target-kurven.
=> MÅ kalibreres mod Kennets rigtige Intervals-fitness-historik (= "hent data til basen").
ÅBENT SPØRGSMÅL til Kennet: er target-CTL peak 67 (uge 11) et mål vi styrer TSS op mod,
eller en optimistisk streg? Afklares når projektionen bygges.

## Faser
0. **OneDrive-reorg** (Kennet udfører — se tjekliste nedenfor).
1. plan.json (begge) + refaktorér build_workouts.py + Friel-validator som testet modul.
2. Læse-website plan.html (overblik + faner + CTL-graf + Friel-flags).
3. Write-back med server-side Friel-gate + concurrency.
4. Genereret Word-snapshot → OneDrive. Excel + dashboard-eksporter ud.

## OneDrive reorg-tjekliste (Phase 0 — Kennet udfører)
Mappe: OneDrive-rod → Claude (984 MB; workspace bekræftet).
- SLET: `CLAUDE OUTPUTS` (tom dublet af `Outputs`)
- FLYT: `About me/Pictures` (698 MB) → `Claude/Pictures`
- FLYT: `About me/About me/*` op ét niveau (fjern dobbelt-nesting)
- FLYT: `Fast as Fifty - traeningsplan` → `Projects/Fast as Fifty`
- ARKIVÉR → `_Arkiv`: Fast_as_Fifty_Dashboard.xlsx, Fast_as_Fifty_Dashboard_v1.1.xlsx,
  fast-as-fifty.html (kopier af live GitHub Pages), Master_Plan.xlsx (efter plan.json),
  gammel Fast_as_Fifty_Masterplan_2026.docx (efter fase 4)
- BEHOLD: Eva_Medoc_Master.xlsx + Eva_Medoc_Traningsplan_2026.docx (til de foldes ind i plan.json)

## Beslutninger låst i denne session
- Cykel-opvarmning/nedkøling: ægte ramp (`ramp:true`) — verificeret i Intervals+Zwift
- Sa Calobra via Puig Major: mandag 20/7 (tidlig afgang)
- Onsdag 22/7: formiddags-langtur før aftenflyet
- Uge 8 torsdag: løb → let Z2-spin (Friel: undgå fortløbende løb)
- Skotland → Wales overalt i kilder

## Referencer (værdier ligger i memory/GitHub-secrets — IKKE her)
- Repo: hammerbamsen/fast-as-50 · Intervals athlete i599466 · FTP 270W · threshold 4:20/km
- Azure app "Fast as Fifty Calendar" (secret i Actions) · OUTLOOK_CAL kennet@hammerby.com
- Workflows: build-workouts.yml (Intervals), create-outlook-events.yml (Outlook spejler fra Intervals),
  sync-onedrive.yml (OneDrive), update-kpi.yml (dashboard)
- OneDrive drive: b!l3-Ehh... · Claude-mappe item 01Y5SFS4FNET3L5UAZYRD3LKVCR5YM2ND7

## Arbejdsregler (ufravigelige)
Plan → accept → QA-subagent → implementér → verificér OUTPUT → rapportér.
Frisk SHA før PUT · GET+slet før POST · verificér indhold, ikke status.
