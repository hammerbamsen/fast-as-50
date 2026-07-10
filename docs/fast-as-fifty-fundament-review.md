# Fast as Fifty — Fundament-review & revideret plan

*Oprettet: 10. juli 2026 (autonom session). Senest opdateret: 10. juli 2026.*
*Til gennemgang: mandag 13. juli, 10:00–11:00 (kalenderblok sat, reminder 30 min før).*

---

## Dom (kort)

Træningsmetodikken er **solid**. Det **tekniske fundament er over-engineered** med mange løse ender. Rock solid bygges ved at fjerne bevægelige dele — ikke ved at tilføje features.

Konkret teknisk gæld:
- Dødt Azure/MSAL-scaffolding (forladt auth-forsøg, står der stadig).
- Inert push-infrastruktur (delvist bygget, ikke reelt i drift).
- Mac launchd som enkeltpunkts-fejl — offline = data fryser (set konkret i Wales).
- Skrøbelig sync og PAT spredt flere steder.
- KPI-cron reelt throttlet af GitHub (2–3 timer mellem kørsler, ikke hver 30. min).

---

## Fire ekspert-linser

### 1. Teknisk arkitekt
Fundamentet har for mange bevægelige dele og halvfærdige spor. Anbefaling: fjern dødt scaffolding, gør dashboard-friskhed uafhængig af Mac'en, og erstat cron-polling med en event-drevet trigger.

### 2. Træningsekspert
Metodikken holder: `plan.json` som single source of truth, Friel-gates (TSB-gulv, CTL-ramp ≤ 8/uge, max 3 løb/uge, recovery-uger), OW-svøm til Christiansborg, marathon-ladder 26 → 29 → 32 km. Lidt at ændre her — hold kursen.

### 3. Ernæringscoach
Tynd. Der mangler en fueling-ramme for de lange dage (Médoc, Stelvio). HRV måles, men fører ikke til handling. → substans i Fase 2.

### 4. UX
Falske fejl-tilstande er delvist ryddet (3-min poll med rolig besked i stedet for rød alarm). Staleness-banner er nu to-niveau. Done skal være idempotent. Ærlig UX slår alarmer.

---

## Revideret rækkefølge

### Fase 0 — Ryd dødt scaffolding
Azure Function, halv-MSAL, og beslut push-fremtiden. Hurtigst, størst effekt, nul risiko.

### Fase 1 — Hærd kernen
- Dashboard-friskhed **uden** Mac (Actions/event-drevet som primær kilde).
- **Kuglesikker aktivitets-fangst.**
- Ærlig UX (ingen falske fejl).
- Idempotent done.

> **Opdatering 10/7 — konkret bevis for behovet for bedre aktivitets-fangst:**
> KPI-cron kører reelt hver 2–3 timer (GitHub throttler scheduled Actions), ikke hver 30. min. Dagens kørsler: 01:08 → 05:35 → 09:36 → 12:25 → 15:12 UTC.
> En ny gåtur ("Pembrokeshire Gang", Walk, 45 min) blev uploadet fra Garmin til Intervals kl. 17:29 dansk tid — 17 min **efter** sidste kørsel (17:12) — og hang derfor på dashboardet, indtil pipelinen blev trigget manuelt.
> **Fix:** webhook (Intervals eller Strava) → `repository_dispatch` → `update-kpi`, så nye aktiviteter kommer ind straks i stedet for at vente på throttlet cron. `webhook-receiver`-workflowet findes allerede og kører på `GITHUB_TOKEN`. Afklar mandag hvilken kilde der er mest pålidelig.

### Fase 2 — Ernærings-substans
Fueling-ramme (Médoc/Stelvio) + HRV → handling.

### Fase 3 — Token-fri trigger
GitHub App + Cloudflare Worker som ren afslutning — ikke bygget ovenpå rodet.
Dette er den **varige** form af webhook-fixet fra Fase 1: ekstern aktivitets-event → Worker → GitHub App-token → dispatch. Ingen PAT i browseren.
GitHub App klar: **ID 4259031**, installation **145518829**, `.pem` hos Kennet.

---

## Beslutning mandag
**Fuld forenkling (Fase 0 → 3)** eller **kun token-fri (Fase 3)**?

---

## Åbne punkter (backlog til mandag)

1. **Webhook — straks-pickup af nye aktiviteter** (hører til Fase 1 + Fase 3). *(nyt 10/7)*
2. **`ANTHROPIC_API_KEY` som Actions-secret** → cloud-baseret AI-coach-regenerering (kører i dag kun via Mac-launchd).
3. **Z1 + Z6 zoner** i zone-beregneren på Træning-fanen.
4. **Oprydning:** slet `debug-secrets.yml`, `debug/secrets_check.txt` og `debug_output.txt` (grep for referencer først).
5. *(valgfri)* aften-AF-reminder cron.

---

*Rock solid bygges ved at fjerne, ikke ved at tilføje. Keep moving forward.*
