# 26/9-2026 — Hegnet Half i kommende løb + Plan-fanen = hele TdS-programmet

## Ændringer
- `scripts/modules/programs.py`: `upcoming_races()` tager også `plan.nextSeason.races` med for Kennet. Hegnet Half (7/3-2027) stod kun der og manglede derfor i "Kommende løb". Dubletter (navn+dato) fjernes som før.
- `scripts/modules/plan_tab.py`: ny parameter `from_program_start` — vinduet går fra det aktive programs start til slut. `scripts/update_kpi.py` sætter den: Plan-fanen viser nu 51 uger (7/9-26 – 29/8-27) i stedet for 53 (4 uger bagud på tværs af Médoc-programmet). Default er uændret (tests).

## Ikke i koden
- Outlook-event man 5/10 08:30 "Tjek tilmelding Tour des Stations 2027" (tilmelding til 2027 var ikke åben 26/9).
- Zoner: Kennet 26/9 — FTP 278 og beregnerens procenter gælder (cykel Z2 56–76 % = 154–211 W). Ingen kodeændring.

## Test
- pytest 660 passed, 1 skipped · schemas OK · node --check sw.js OK.
- Offline: upcoming_races → Hegnet Half, Stelvio, TdS. build_plan_tab(from_program_start=True) → 51 uger, 2026-09-07 … 2027-08-23.
