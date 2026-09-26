# CLAUDE.md — arbejdsregler for dette repo

Fast as Fifty: Kennets trænings-dashboard (PWA) + pipeline i GitHub Actions. Alt på dansk — tekster, kommentarer, commit-beskeder, ændringslogs.

## Arbejdsform
- Claude må committe og pushe direkte til `main` (besluttet af Kennet 26/9-2026), når alle fire CI-trin nedenfor er grønne lokalt. Hent `origin/main` og rebase lige før push. Skriv en `CHANGES-<dato>-<emne>.md` i repo-roden (ændringer pr. fil, testresultat, hvad der ikke kunne verificeres) i samme commit.
- Undtagelser — brug en branch `claude/<dato>-<emne>` + PR i stedet: flere agenter arbejder i samme blok, ændringen rører `.github/workflows/` eller `workers/`, eller en test er rød og ikke kan rettes.
- Ret aldrig `data.json` og `health.json` i hånden, og ændr ikke `data/plan.json` via commit — planændringer går via `edit_apply`/forslag. Alt der var grønt skal forblive grønt. Rør ikke filer der er tildelt en anden agent i samme blok.
- Læs `docs/PIPELINE.md` før enhver ændring under `.github/workflows/`, og hold `health.yml`'s workflow-liste i synk med `name:` i de øvrige workflows.

## Kommandoer
```
python3 -m pytest scripts/modules/ scripts/test_*.py -q   # enhedstests (CI-trin a)
python3 schemas/validate.py                                           # JSON-skemaer (CI-trin b)
node --check sw.js                                                    # (CI-trin c; d = index.html's inline scripts)
python3 scripts/build_zwo.py                                          # .zwo-filer fra bike_library.json → workouts/zwift/
python3 scripts/update_kpi.py                                         # kræver INTERVALS_*/GH_TOKEN — kør ikke lokalt uden grund
```

## Ufravigelige regler (kældertræning)
1. Kælderpas vælges KUN fra `data/bike_library.json` via workout-`id` (`libraryId` på entry'en). Opfind aldrig et pas ad hoc, og ændr aldrig watt-tal i et eksisterende.
2. Ret aldrig en `.zwo`-fil i hånden — ret JSON'en og kør `scripts/build_zwo.py`.
3. Max 2 hårde + 2 moderate cykelpas pr. uge, mindst 72 timer mellem to hårde. Belastning står i feltet `load` (let/moderat/haard) — udled den ikke af kategorien. `bike_library.check_week()` håndhæver reglen; kør den før pas skrives til plan.json.
4. FTP er indendørs-målt. Styrke 2×/uge tæller i samlet belastning, men ikke i max-2-hårde-reglen.

## Filoversigt
- `index.html` + `sw.js` + `manifest.json` — dashboardet (I dag / Plan / Krop / Mere). `plan.html`, `eva.html` — klientsider der dispatcher via Worker'en (AF/check-in ligger i index.html's log-ark; af.html/checkin.html slettet blok 9).
- `scripts/update_kpi.py` — pipelinen; `scripts/modules/*` — ren logik + tests (`test_*.py`). `scripts/send_push.py` (daglig/aften/`--alert`), `scripts/health_report.py`, `scripts/build_workouts.py`, `scripts/build_zwo.py`, `scripts/apply_edit.py`.
- `data/plan.json`, `data/bike_library.json`, `data/plan_view.json`, `data/workout_library.json`, `data/proposals/*.json` (forslag — anvendes KUN via `edit_apply` action `apply_proposal`, offline med `python3 -m modules.proposals apply-offline <id>` fra `scripts/`); `data.json` og `health.json` i roden (skrives af Actions — ret dem aldrig i hånden).
- `.github/workflows/*` — se `docs/PIPELINE.md`. `schemas/` — JSON-kontrakter + `validate.py`. `workers/webhook-dispatch/` — Cloudflare Worker (GitHub App).
- `docs/` — PIPELINE, PAT_RENEWAL, PUSH_SETUP, AZURE_SETUP. `CHANGES-*.md` — ændringslogs pr. blok.

## Kontrakter
- **plan.json**: `programs{id → {start, end, totalWeeks, weeks[{week, start, blockType, ctlTarget}]}}`, `athletes{kennet, eva → {zones, days[{date, entries[{id, workout|null, note?, libraryId?, templateId?}]}]}}`. Aktivt program vælges efter dato i `modules/programs.py`. Styrke (blok 10): `athletes.kennet.strengthCheckin{søndag → {legs 0/1, upper 0/1, at}}` og `strengthProgression{current, previous, effectiveFrom, lastCheckin}` skrives KUN af `edit_apply` action `strength_checkin` (regler i `modules/strength_progression.py`); `strengthLog` (blok 8, RPE pr. pas) er bagudkompatibel men bruges ikke længere.
- **data.json**: `meta{updated 'YYYY-MM-DD HH:MM' lokal, week, date, ...}`, `kpis{label → {value, unit, sub, color}}`, `today[]`, `week_sessions[{day, disc, label, done}]`, plus historik/planTab/body. `strength{templates, next{exercises[] med progression lagt på, stateSummary, recovery}, checkin{due, date, next, ...}}` — check-in-kortet i I dag vises når `checkin.due` er sand. Farver beregnes i pipelinen, ikke i UI'et.
- **health.json**: `generatedAt`, `workflows{navn → {lastRun, conclusion, event, runUrl, durationS, expectedEveryMin?}}`, `secrets{navn → {expires, usedBy, note}}`. Dashboardet regner alder/farver selv — ingen anden tilstand i filen.
- **bike_library.json**: `meta{categories, rules}`, `workouts[{id, name, category, load, erg?, est_min, steps[{type steady|ramp|reps|free, min, pct|from/to|n+steps}]}]`.
Skemaerne i `schemas/` kræver kun de felter koden læser; udvider du en kontrakt, opdatér skemaet i samme commit.
