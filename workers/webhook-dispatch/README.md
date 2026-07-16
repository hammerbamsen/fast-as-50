# Cloudflare Worker — Intervals-webhook (Fase 3) + token-fri dispatch + health

Én Worker, syv ruter — dækker al PAT-fri dispatch for hele Fast as Fifty:

- **`POST /`** — Intervals.icu-webhook. Udløser med det samme
  `repository_dispatch` mod GitHub (`intervals-activity`), i stedet for at
  vente på `update-kpi.yml`'s cron (som i praksis kun kører hver 2–3,5 time —
  se Læringer nedenfor, `*/30` bliver throttlet af GitHub). `webhook-receiver.yml`
  findes allerede i repoet og kører bare `update_kpi.py` på ny — Worker'en
  skal derfor kun afgøre OM den skal trigge, ikke forstå hele payloaden.
- **`POST /plan-edit`** — erstatter den aldrig-deployede Azure Function
  (`azure-function/plan_edit`, slettet fra repoet). Bruges af `plan.html` og
  `eva.html`.
- **`POST /af-registrering`** — bruges af `af.html` (AF-check-in).
- **`POST /checkin`** — bruges af `checkin.html` (dagligt wellness-check-in).
- **`POST /refresh`** — manuel trigger fra dashboardets OPDATÉR-knap.
  Dispatcher samme event som Intervals-webhooken (`intervals-activity`), men
  bag `X-Plan-Secret` i stedet for `WEBHOOK_SECRET`, så browseren aldrig ser
  webhook-hemmeligheden. Nødvendig fordi wellness (morgenvægt) og
  Strava-aktiviteter IKKE udløser aktivitets-webhooks.
- **`POST /push-subscribe`** — bruges af `eva.html` og `index.html` (web
  push-abonnement).
- **`GET /health`** — bekræfter at Worker'en kører og er konfigureret
  (erstatter `azure-function/health`).

De fem POST-dispatch-ruter kræver alle `X-Plan-Secret`-headeren
(`PLAN_EDIT_SECRET`) — samme værdi i alle fem klientsider, ingen PAT
nogen steder længere.

Autentificering mod GitHub sker i begge dispatch-ruter som en GitHub App
(App ID `4259031`, installation `145518829`) — ingen PAT i browseren, ingen
langlivet hemmelighed rører klienten. Koden er testet lokalt (JWT-signering
verificeret uafhængigt med et testnøglepar via Web Crypto, plus mock-tests af
alle tre ruter: auth, manglende felter, happy path, event-type-filtrering)
før den committes her.

## Status

**LIVE siden 16/7-2026.** Hele kaeden verificeret ende-til-ende:
Intervals -> Worker -> GitHub -> data.json paa **7 sekunder**
(aktivitet aendret 13:30:36Z, workflow-run startet 13:30:43Z, conclusion success).

- [x] Worker-kode skrevet + testet (`worker.js`)
- [x] Deployet til Cloudflare (`/health`: alle flag `true`)
- [x] Webhook-adgang givet af David 14/7: https://intervals.icu/oauth/client/580
- [x] `WEBHOOK_SECRET` + `PLAN_EDIT_SECRET` sat
- [x] Webhook-URL sat paa klient 580, `ACTIVITY_UPLOADED` + `ACTIVITY_UPDATED` valgt
- [x] **Atlet i599466 har OAuth-godkendt app'en** (scope `ACTIVITY:READ`)
- [x] `ANTHROPIC_API_KEY` tilfoejet til `webhook-receiver.yml`
- [x] `/refresh`-rute skrevet + mock-testet (6/6)
- [ ] `/refresh` deployet til Cloudflare  <- ENESTE UDESTAAENDE

## Laeringer der kostede tid (16/7)

**1. Cron'en loeg.** `update-kpi.yml` siger `*/30`, men GitHub throttler
scheduled Actions haardt. Faktiske koersler 16/7: 01:00, 04:38, 07:22, 09:34,
11:39 UTC — dvs. **hver 2-3,5 time**, ikke hver 30. min. `*/30` er en
hensigtserklaering, ikke en aftale. Webhooken er derfor ikke luksus: uden den
er load-billedet systematisk forkert flere timer dagligt.

**2. "0 athletes are testing it" var den stille blokering.** Webhook-URL,
secret og event-typer kan vaere 100% korrekte — Intervals sender alligevel
ingenting, foer en atlet har OAuth-godkendt app'en. Consent-URL:
`https://intervals.icu/oauth/authorize?client_id=580&redirect_uri=http%3A%2F%2Flocalhost%2F&scope=ACTIVITY%3AREAD&response_type=code`
Koden fra `localhost/?code=...` veksles paa `POST https://intervals.icu/api/oauth/token`
(IKKE `/oauth/token` — den giver 405).

**3. Cloudflare-secrets kan ikke laeses tilbage.** Derfor kan man ikke
verificere at to sider matcher — kun overskrive. Kopiér ALTID fra den side der
kan laeses (Intervals) til den der ikke kan (Cloudflare). Symptomet paa mismatch
er et paent `401` fra SEND TEST-WEBHOOK — hvilket samtidig BEVISER at URL'en er
rigtig og Worker'en koerer.

**4. Worker'en svarer 2xx baade ved dispatch og ved bevidst ignorering.**
Et groent "OK: 2xx" fra SEND TEST-WEBHOOK beviser derfor IKKE at der skete
noget. Verificér altid paa GitHub-siden (`webhook-receiver.yml`-runs), ikke paa
Intervals-siden.

**5. `webhook-receiver.yml` manglede `ANTHROPIC_API_KEY`** (mens `update-kpi.yml`
havde den). Havde webhooken vaeret taendt uden det fix, ville HVER koersel have
skrevet data.json med doed coach-tekst. Tjek altid env-paritet mellem workflows
der koerer samme script.

**6. Intervals API:** aktiviteter opdateres paa `PUT /api/v1/activity/{id}`
(ikke `/athlete/{id}/activities/{id}` — 405). `{"description": null}` ignoreres
stille; brug tom streng for at rydde et felt.

**7. Ingen loop-risiko ved `ACTIVITY_UPDATED`:** `update_kpi.py` har nul
skrivninger til Intervals (kun laesninger), saa den kan ikke trigge sig selv.

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

# AF-registrering
curl -X POST "https://fast-as-50-webhook.<dit-subdomain>.workers.dev/af-registrering" \
  -H "X-Plan-Secret: <din PLAN_EDIT_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-07-14","alkohol":0}'

# Checkin
curl -X POST "https://fast-as-50-webhook.<dit-subdomain>.workers.dev/checkin" \
  -H "X-Plan-Secret: <din PLAN_EDIT_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-07-14","alkohol":0,"protein":2,"energi":4,"stress":2}'

# Push-subscribe
curl -X POST "https://fast-as-50-webhook.<dit-subdomain>.workers.dev/push-subscribe" \
  -H "X-Plan-Secret: <din PLAN_EDIT_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"subscription":{"endpoint":"https://example.test/ep","athlete":"kennet"}}'
```

Forventet for Intervals-testen: `dispatched` (200). Tjek derefter
**Actions**-fanen i repoet — "Intervals Webhook Receiver" skal have en ny
kørsel. Forventet for de fire øvrige: `{"ok":true,...}` (200), og
tilhørende workflow ("Plan-redigering (fase 3a)", "Check-in registrering",
"Modtag push-subscription") skal have en ny kørsel.

## Filer

- `worker.js` — selve Worker-koden (alle seks ruter)
- `wrangler.toml` — Wrangler-konfiguration til `npx wrangler deploy`
- `README.md` — denne fil
