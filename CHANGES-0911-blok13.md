# Blok 13 — FTP-sporing i dashboardet (11/9-2026)

Tests: 640 passed (pytest-shim; pywebpush-testen springes over lokalt — CI er dommer). Skemaer grønne. `node --check` grøn på index.html's tre inline scripts.

## Hvad
CTL blev allerede sporet (KPI mod ugemål, 51-ugers målkurve, projektion). FTP var kun et tal i zonerne. Nu:
- **KPI-kort "FTP"** i Træning-rækken: aktuel FTP, W/kg på 7-dages vægt, fasemål (season2027.phases) og næste testdato. Farve: grøn = på/over fasemål, orange = inden for 3 %, rød = under.
- **FTP-kort i Krop-fanen**: samme tal + alle seks fasemål (278 → 292 → 305 → 308 → 320 → 320) med den aktuelle fase fremhævet, og testhistorik (seneste 6).
- **Historik**: `athletes.kennet.ftpHistory[{date, ftpW, source}]` i plan.json. Seedet med 278 W (28/7-2026). Fyldes automatisk når FTP sættes via app'ens `set_zones` (edit_apply) — uændret FTP skriver intet.

## Filer
- `scripts/modules/ftp_track.py` (ny): `build()`, `kpi()`, `record()`, `next_test()`, `phase_for()`. Ren logik.
- `scripts/modules/test_ftp_track.py` (ny): 8 tests, inkl. mod den rigtige plan.json og set_zones-vejen.
- `scripts/modules/edit_apply.py`: set_zones med ny ftpW → `ftp_track.record`.
- `scripts/update_kpi.py`: `data['ftp']` + `data['kpis']['ftp']` (vægt fra body.glidepath.avg7).
- `index.html`: KPI-kort FTP, `D.ftp` fra data.json, `ftpCard()` i renderBody efter kropsfliserne.
- `data/plan.json`: `ftpHistory` seed.

## Efter FTP-test
Sæt ny FTP i app'en (Mere → zoner) eller bed Claude: zones.ftpW + ftpHistory + `set-zones.yml` mod Intervals. Kortet opdateres ved næste pipeline-kørsel (≤ 1 time).

## Ikke verificeret
`update_kpi.py` er ikke kørt lokalt (kræver Intervals-nøgler) — første rigtige kørsel er cron eller manuel "Daglig dashboard-opdatering".
