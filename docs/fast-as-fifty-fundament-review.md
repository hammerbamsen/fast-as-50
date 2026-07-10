# Fast as Fifty — Fundament-review & revideret plan

*Oprettet: 10. juli 2026. Senest opdateret: 10. juli 2026 (genskabt fra sidste session + dagens fund).*
*Til gennemgang: mandag 13. juli, 10:00–11:00 (kalenderblok sat, reminder 30 min før).*

---

## Samlet dom

Din tese ("for komplekst, mange løse ender") holder — men **kun på teknik-siden**. Træningsmetodikken er solid. Rock solid = **færre bevægelige dele der hver især altid virker**, ikke flere features.

---

## Fire ekspert-linser

### 1. Træning
Metodikken er solid (Friel, TSB-gulv, CTL-ramp, recovery-uger, disciplin-zoner) — **rør den ikke**. Den reelle svaghed er **dataintegritet**: manglende aktiviteter → forkert CTL → forkerte load-beslutninger (Zwift-ritt 7/7 tabte load). Plus plan-inkohærens (Wales-ugen markeret "ingen cykel", men med et cykelpas).

### 2. UX
Gode knogler, men fejl-tilstandene er brugerfjendtlige: falske "Timeout"-alarmer for ting der faktisk lykkedes, manuel afstemning (paste token → done → sync), ingen ærlig "opdateret for X min siden". Bedste UX = du stoler på data uden at skulle tjekke.

### 3. Ernæring
AF/vægt-tracking er godt og simpelt — behold. Men fueling-strategi (Médoc/Stelvio: g kulhydrat/time, hydrering, restitution) og HRV → handling er under-udviklet. Tilføj **substans, ikke features**.

### 4. Teknisk / AI
Over-engineered for ét én-bruger-system: ~17 workflows, 6+ datalagre, mange sync-veje. Løse ender: dødt Azure/MSAL-scaffolding, inert push, Mac som enkeltpunkts-fejl (dashboard står stille når du rejser), skrøbelige mønstre (`toggle_done` ikke idempotent, SHA-races, plan.json↔Intervals desync).

---

## Revideret rækkefølge (forenkl → hærd → så token-fri)

### Fase 0 — Ryd dødt scaffolding
Azure Function, halv-MSAL, og beslut push-fremtiden. Hurtigst, størst effekt, nul risiko.

### Fase 1 — Hærd kernen
- Dashboard-friskhed **uden** Mac.
- **Kuglesikker aktivitets-fangst.**
- Ærlig UX (ingen falske fejl).
- Idempotent done.
- Plan-kohærens-tjek (fang uger hvor plan og pas modsiger hinanden).

> **Opdatering 10/7 — dataintegritets-svagheden ramte i dag (konkret bevis):**
> KPI-cron kører reelt hver 2–3 timer (GitHub throttler scheduled Actions), ikke hver 30. min. Dagens kørsler: 01:08 → 05:35 → 09:36 → 12:25 → 15:12 UTC.
> En ny gåtur ("Pembrokeshire Gang", 45 min) blev uploadet fra Garmin kl. 17:29 dansk tid — 17 min **efter** sidste kørsel (17:12) — og hang på dashboardet indtil manuelt trigger. Præcis mønstret fra træningslinsen: **manglende aktivitet → forkert load-billede.**
> **Fix:** webhook (Intervals eller Strava) → `repository_dispatch` → `update-kpi`, så nye aktiviteter kommer ind straks. `webhook-receiver`-workflowet findes allerede og kører på `GITHUB_TOKEN`.

### Fase 2 — Ernærings-substans
Fueling-ramme (Médoc/Stelvio) + HRV → handling.

### Fase 3 — Token-fri trigger
GitHub App + Cloudflare Worker som ren afslutning — ikke et lag ovenpå rodet. Den varige form af webhook-fixet fra Fase 1: ekstern aktivitets-event → Worker → GitHub App-token → dispatch. Ingen PAT i browseren.
GitHub App klar: **ID 4259031**, installation **145518829**, `.pem` hos Kennet. Mønter-kode skrevet + testet.

---

## Beslutning mandag
**Fuld forenkling (Fase 0 → 3)** eller **kun token-fri (Fase 3)**?

---

## Åbne punkter (backlog til mandag)

1. **Webhook — straks-pickup af nye aktiviteter** (hører til Fase 1 + Fase 3). *(nyt 10/7)*
2. **Sync-hærdning følges op:** `sync-onedrive.yml` fejlede hårdt siden 7/7, fordi `data/Master_Plan.xlsx` og `data/Eva_Medoc_Master.xlsx` mangler i repoet. Midlertidigt fikset med `continue-on-error`. Beslut: genskab kilderne, eller fjern de døde steps. *(nyt 10/7)*
3. **`ANTHROPIC_API_KEY` som Actions-secret** → cloud-baseret AI-coach-regenerering.
4. **Z1 + Z6 zoner** i zone-beregneren på Træning-fanen.
5. **Oprydning:** slet `debug-secrets.yml`, `debug/secrets_check.txt` og `debug_output.txt` (grep for referencer først).
6. *(valgfri)* aften-AF-reminder cron.

---

*Rock solid bygges ved at fjerne, ikke ved at tilføje. Keep moving forward.*
