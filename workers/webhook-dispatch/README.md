# Cloudflare Worker — Intervals-webhook (Fase 3) + plan-edit + health

Én Worker, tre ruter:

- **`POST /`** — Intervals.icu-webhook. Udløser med det samme
  `repository_dispatch` mod GitHub (`intervals-activity`), i stedet for at
  vente på `update-kpi.yml`'s cron (hver 10.–30. min). `webhook-receiver.yml`
  findes allerede i repoet og kører bare `update_kpi.py` på ny — Worker'en
  skal derfor kun afgøre OM den skal trigge, ikke forstå hele payloaden.
- **`POST /plan-edit`** — erstatter den aldrig-deployede Azure Function
  (`azure-function/plan_edit`, slettet fra repoet). Ingen MSAL/Entra ID for
  én bruger: én delt hemmelighed (`PLAN_EDIT_SECRET`) sendt i en
  `X-Plan-Secret`-header, tjekket i Worker'en. Ved godkendt kald: samme
  `repository_dispatch` (`plan-edit`) som før, til `.github/workflows/plan-edit.yml`.
- **`GET /health`** — bekræfter at Worker'en kører og er konfigureret
  (erstatter `azure-function/health`).

Autentificering mod GitHub sker i begge dispatch-ruter som en GitHub App
(App ID `4259031`, installation `145518829`) — ingen PAT i browseren, ingen
langlivet hemmelighed rører klienten. Koden er testet lokalt (JWT-signering
verificeret uafhængigt med et testnøglepar via Web Crypto, plus mock-tests af
alle tre ruter: auth, manglende felter, happy path, event-type-filtrering)
før den committes her.

## Status

- [x] Worker-kode skrevet + testet (`worker.js`) — Intervals-webhook, plan-edit, health
- [ ] Intervals.icu-webhook oprettet (afventer svar fra David — mailet 13/7)
- [ ] Deployet til Cloudflare
- [ ] Webhook-secret + callback-URL sat op hos Intervals.icu
- [ ] `PLAN_EDIT_SECRET` sat, `plan.html` peger på Worker-URL

## Deploy — trin for trin

### 1. Konvertér .pem til PKCS#8

GitHub Apps leverer nøglen som PKCS#1 (`-----BEGIN RSA PRIVATE KEY-----`),
men Web Crypto (som Workers bruger) kræver PKCS#8
(`-----BEGIN PRIVATE KEY-----`). Konvertér én gang lokalt:

```bash
openssl pkcs8 -topk8 -inform PEM -outform PEM -nocrypt \
  -in original-github-app.pem -out github-app-pkcs8.pem
```

Brug indholdet af `github-app-pkcs8.pem` i trin 3 — ikke den originale fil.

### 2. Opret Worker'en

Enten via CLI (`wrangler.toml` findes allerede i denne mappe):

```bash
cd workers/webhook-dispatch
npx wrangler login      # én gang, åbner browser til Cloudflare-login
npx wrangler deploy
```

Eller via dashboardet: **Workers & Pages → Create → Create Worker**, navngiv
den `fast-as-50-webhook`, erstat standard-koden med hele indholdet af
`worker.js`, og deploy.

### 3. Sæt vars og secrets

**Settings → Variables and Secrets** på Worker'en (eller `npx wrangler secret put <navn>`):

| Navn | Type | Værdi |
|---|---|---|
| `GITHUB_APP_ID` | Variable | `4259031` |
| `GITHUB_INSTALLATION_ID` | Variable | `145518829` |
| `GITHUB_REPO` | Variable | `hammerbamsen/fast-as-50` |
| `GITHUB_APP_PRIVATE_KEY` | **Secret** | hele indholdet af `github-app-pkcs8.pem` fra trin 1 |
| `WEBHOOK_SECRET` | **Secret** | den delte hemmelighed du aftaler med Intervals.icu (se trin 4) |
| `PLAN_EDIT_SECRET` | **Secret** | en selvvalgt, tilfældig streng — bruges af `plan.html` i stedet for MSAL-login |

### 4. Konfigurér webhooken hos Intervals.icu

Når David har svaret og aktiveret webhook-adgang: sæt callback-URL til
Worker'ens rod-adresse (`https://fast-as-50-webhook.<dit-subdomain>.workers.dev/`)
og notér den delte hemmelighed han giver dig — den skal matche
`WEBHOOK_SECRET` fra trin 3.

`checkWebhookAuth()` i `worker.js` tjekker i dag tre almindelige varianter
(Bearer-header, `X-Webhook-Secret`-header, `?secret=`-query). Hvis
Intervals.icu bruger noget andet (fx en HMAC-signatur af body'en), justér
`checkWebhookAuth()` ud fra det David faktisk sender — kom tilbage, så
retter vi den sammen.

### 5. Test

```bash
# Health
curl "https://fast-as-50-webhook.<dit-subdomain>.workers.dev/health"

# Intervals-webhook
curl -X POST "https://fast-as-50-webhook.<dit-subdomain>.workers.dev/" \
  -H "X-Webhook-Secret: <din WEBHOOK_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"type":"ACTIVITY_UPLOADED"}'

# Plan-edit
curl -X POST "https://fast-as-50-webhook.<dit-subdomain>.workers.dev/plan-edit" \
  -H "X-Plan-Secret: <din PLAN_EDIT_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requestId":"test1","action":"adjust","entryId":"<en-rigtig-entryId>","params":{}}'
```

Forventet for Intervals-testen: `dispatched` (200). Tjek derefter
**Actions**-fanen i repoet — "Intervals Webhook Receiver" skal have en ny
kørsel. Forventet for plan-edit-testen: `{"ok":true,...}` (200), og
"Plan-redigering (fase 3a)"-workflowet skal have en ny kørsel.

## Filer

- `worker.js` — selve Worker-koden (alle tre ruter)
- `wrangler.toml` — Wrangler-konfiguration til `npx wrangler deploy`
- `README.md` — denne fil
