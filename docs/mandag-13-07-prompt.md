# Fast as Fifty — mandagssession 13/7 (kickoff-prompt)

Kontekst: Vi skal gennemgå fundament-reviewet og beslutte forenklings-omfang.

**Siden sidst (11/7 — Wales):**
- **Coach-grounding fix DEPLOYET** (`scripts/modules/coach.py`): AI-vurderingen bygger nu på eksplicitte GENNEMFØRT-/MISSET-lister fra `week_sessions` og har en ufravigelig regel om at et gennemført pas aldrig må kaldes "manglende". Baggrund: coachen påstod tirsdagens Zwift-cykel (7/7) var glemt, selvom den lå korrekt i Intervals (TSS 49) og allerede talte med i CTL. Roden var todelt: (a) prompten fodrede ikke modellen en liste over hvad der FAKTISK var gjort, og (b) AI-vurderingen fryser fast mellem Mac-kørsler.
- **Konsekvens for mandag:** Mac'en skal `git pull` den nye kode, og AI-vurderingen skal regenereres, før fixet er synligt. Det gør backlog-punkt 3 (ANTHROPIC-secret) til et *konkret* førsteprioritets-punkt — se nedenfor.

**Læs FØRST reviewet** (det bærer al detalje):
- Repo: `docs/fast-as-fifty-fundament-review.md`
- OneDrive: `Projects/Fast as Fifty/fast-as-fifty-fundament-review.md`

**Dom:** Træningsmetodikken er solid. Det tekniske fundament er over-engineered med løse ender. Rækkefølge: forenkl → hærd → token-fri.

**Dagens beslutning:** fuld forenkling (Fase 0 → 3) eller kun token-fri (Fase 3)?

**Faser:**
- Fase 0 — ryd dødt scaffolding (Azure Function, halv-MSAL, beslut push).
- Fase 1 — hærd kernen (dashboard uden Mac, kuglesikker aktivitets-fangst, ærlig UX, idempotent done, plan-kohærens-tjek).
- Fase 2 — ernærings-substans (fueling Médoc/Stelvio + HRV→handling).
- Fase 3 — token-fri trigger (GitHub App + Cloudflare Worker; App klar: ID 4259031, installation 145518829, .pem hos mig).

**Backlog (åbne punkter):**
1. Webhook — straks-pickup af nye aktiviteter (Fase 1+3): Intervals/Strava → `repository_dispatch` → `update-kpi`. `webhook-receiver` findes og kører på GITHUB_TOKEN.
2. Sync-bug: `sync-onedrive.yml` — `data/Master_Plan.xlsx` + `data/Eva_Medoc_Master.xlsx` mangler i repoet (midlertidigt fikset med `continue-on-error` 10/7). Beslut: genskab kilderne eller fjern de døde steps.
3. **`ANTHROPIC_API_KEY` som Actions-secret → cloud AI-coach-regenerering.** *(hævet til førsteprioritet 11/7)* `ANTHROPIC_API_KEY` er ikke sat som Actions-secret (kendt fra tidligere sessioner — kan ikke bekræftes med nuværende PAT, der mangler secrets-read; tjek selv i GitHub → Settings → Secrets and variables → Actions). Derfor regenereres coach-vurderingen kun på Mac'en (launchd) — den fryser fast og modsiger de friske `week_sessions` mellem kørsler. Kennet lægger nøglen ind (jeg har den ikke), og vi verificerer at `update-kpi` regenererer vurderingen i skyen hver kørsel. Dette *er* den varige del af coach-fixet: dagens grounding-kode fjerner hallucinationen, secret'en fjerner staleness'en. Kræver også at Mac-koden pull'es (eller at cloud-kørslen bliver kilden).
4. Z1 + Z6 zoner i zone-beregneren (Træning-fanen).
5. Oprydning: slet `debug-secrets.yml`, `debug/secrets_check.txt`, `debug_output.txt` (grep referencer først).
6. (valgfri) aften-AF-reminder cron.

**Arbejdsregler (ufravigelige):**
- Analysér → præsentér plan → vent på mit "kør" → implementér + QA → verificér **faktisk output** (ikke kun statuskoder).
- Brug subagents til QA og bounded tasks. Tjek `data.json`/GitHub via API før terminal.
- Workflow-filer redigeres via Git Data API (Contents API afviser dem). SHA hentes frisk lige før hver PUT.
- Svar på dansk, terse. Repo: `hammerbamsen/fast-as-50`. Dashboard: `hammerbamsen.github.io/fast-as-50`. Credentials ligger i memory.

**Start med:** bekræft at du har læst reviewet, og præsentér så din anbefaling — fuld forenkling (0→3) eller kun token-fri (3) — med kort begrundelse. Vent på mit valg før implementering.
