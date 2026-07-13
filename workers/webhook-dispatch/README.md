# Fase 3 — Cloudflare Worker (token-fri trigger)

Modtager et webhook-kald når en ny aktivitet dukker op og udløser med det
samme `repository_dispatch` mod GitHub (`intervals-activity`), i stedet for
at vente på `update-kpi.yml`'s cron (hver 10.–30. min). `webhook-receiver.yml`
findes allerede i repoet og kører bare `update_kpi.py` på ny — Worker'en skal
derfor kun afgøre OM den skal trigge, ikke forstå hele payloaden.

Autentificering mod GitHub sker som en GitHub App (App ID `4259031`,
installation `145518829`) — ingen PAT i browseren. Koden er testet lokalt
(JWT-signering verificeret uafhængigt med `jsonwebtoken` + et testnøglepar,
plus 6 adfærdstests af auth/filtrering/verifikations-handshake) før den
committes her.

## Status

- [x] Worker-kode skrevet + testet (`worker.js`)
- [ ] Intervals.icu-webhook oprettet (afventer svar fra David — mailet 13/7)
- [ ] Deployet til Cloudflare
- [ ] Webhook-secret + callback-URL sat op hos Intervals.icu

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

I Cloudflare-dashboardet: **Workers & Pages → Create → Create Worker**. Giv
den et navn (fx `fast-as-50-webhook`), og erstat standard-koden med hele
indholdet af `worker.js`. Deploy.

### 3. Sæt vars og secrets

**Settings → Variables and Secrets** på Worker'en:

| Navn | Type | Værdi |
|---|---|---|
| `GITHUB_APP_ID` | Variable | `4259031` |
| `GITHUB_INSTALLATION_ID` | Variable | `145518829` |
| `GITHUB_REPO` | Variable | `hammerbamsen/fast-as-50` |
| `GITHUB_APP_PRIVATE_KEY` | **Secret** | hele indholdet af `github-app-pkcs8.pem` fra trin 1 |
| `WEBHOOK_SECRET` | **Secret** | den delte hemmelighed du aftaler med Intervals.icu (se trin 4) |

### 4. Konfigurér webhooken hos Intervals.icu

Når David har svaret og aktiveret webhook-adgang: sæt callback-URL til
Worker'ens adresse (`https://fast-as-50-webhook.<dit-subdomain>.workers.dev`)
og notér den delte hemmelighed han giver dig — den skal matche
`WEBHOOK_SECRET` fra trin 3.

`checkAuth()` i `worker.js` tjekker i dag tre almindelige varianter (Bearer-
header, `X-Webhook-Secret`-header, `?secret=`-query). Hvis Intervals.icu
bruger noget andet (fx en HMAC-signatur af body'en), justér `checkAuth()`
ud fra det David faktisk sender — kom tilbage, så retter vi den sammen.

### 5. Test

```bash
curl -X POST "https://fast-as-50-webhook.<dit-subdomain>.workers.dev/" \
  -H "X-Webhook-Secret: <din WEBHOOK_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"type":"ACTIVITY_UPLOADED"}'
```

Forventet: `dispatched` (200). Tjek derefter **Actions**-fanen i repoet —
"Intervals Webhook Receiver" skal have en ny kørsel.

## Filer

- `worker.js` — selve Worker-koden
- `worker-readme.md` — denne fil
