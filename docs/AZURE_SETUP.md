# Fase 3b.1 — Azure-opsætning (FORÆLDET — se workers/webhook-dispatch/README.md)

**Forældet 14/7:** MSAL/Entra ID-vejen beskrevet herunder er erstattet af en Cloudflare Worker med en delt hemmelighed (`data/auth_config.json` + `PLAN_EDIT_SECRET`) — ingen App Registration, ingen Function App. Denne fil er kun bevaret for historik.

---

Én-gangs opsætning så du aldrig indtaster GitHub-token igen. Efter dette login'er du automatisk via din Microsoft-konto (samme login som Outlook), og alle plan-ændringer går gennem en sikker Azure Function-proxy hvor dit PAT ligger server-side.

**Tid:** ca. 20 minutter. Kan afbrydes og genoptages.

---

## Trin 1 — Azure AD App Registration (5 min)

Åbn [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **+ New registration**.

- **Name:** `Fast as Fifty Plan Editor`
- **Supported account types:** Accounts in this organizational directory only (single tenant)
- **Redirect URI:**
  - Platform: **Single-page application (SPA)**
  - URI: `https://hammerbamsen.github.io/fast-as-50/plan.html`

Tryk **Register**.

På siden der åbnes: **noter Application (client) ID** og **Directory (tenant) ID** (top af Overview-fanen). Du skal bruge dem i trin 6.

### 1a — Redirect URI'er
Gå til **Authentication** i venstre menu → **Single-page application** → **+ Add URI**. Tilføj:
- `https://hammerbamsen.github.io/fast-as-50/eva.html`
- `https://hammerbamsen.github.io/fast-as-50/index.html`

Tryk **Save**.

### 1b — Expose an API
Gå til **Expose an API** → **+ Add a scope**.
- Set Application ID URI til default (`api://<client-id>`) — tryk **Save and continue**.
- **Scope name:** `plan.access`
- **Who can consent:** Admins and users
- **Admin consent display name:** Read and edit plan
- **Admin consent description:** Allow the client app to submit plan edits
- **State:** Enabled

Tryk **Add scope**.

### 1c — Godkend scope for din egen klient
Stadig i **Expose an API**: under scopet klik **+ Add a client application**.
- **Client ID:** Samme som Application (client) ID (samme app)
- Tjek scopet af

Tryk **Add application**.

---

## Trin 2 — Azure Function App (5 min)

Azure Portal → **Function App** → **+ Create**.

- **Subscription:** din sædvanlige
- **Resource Group:** ny → `fast-as-fifty-rg` (eller vælg eksisterende)
- **Function App name:** `fast-as-fifty-plan` (skal matche `AZURE_FUNCTIONAPP_NAME` i workflow'et)
- **Do you want to deploy code or container?** Code
- **Runtime stack:** Python
- **Version:** 3.11
- **Region:** **West Europe** (Amsterdam — tættest på DK)
- **Operating System:** Linux
- **Hosting plan:** Consumption (Serverless) — gratis for dit brug

**Review + create** → **Create**. Vent på deployment (~2 min).

---

## Trin 3 — App Settings (2 min)

Åbn Function App'en → **Settings** → **Environment variables** → **+ Add**. Tilføj disse fem (én ad gangen, tryk **Apply** efter hver):

| Name | Value |
|---|---|
| `AZURE_TENANT_ID` | Directory (tenant) ID fra trin 1 |
| `AZURE_APP_CLIENT_ID` | Application (client) ID fra trin 1 |
| `GH_TOKEN` | Dit fine-grained GitHub PAT (samme som du bruger nu) |
| `ALLOWED_UPNS` | `kennet@hammerby.com` |
| `ALLOWED_ORIGIN` | `https://hammerbamsen.github.io` |

Tryk **Apply** øverst når alle er tilføjet — Function App'en genstarter.

---

## Trin 4 — CORS (1 min)

Function App → **API** → **CORS** → tilføj under Allowed Origins:
- `https://hammerbamsen.github.io`

Sæt **Enable Access-Control-Allow-Credentials** til på. Tryk **Save**.

---

## Trin 5 — Publish profile → GitHub secret (3 min)

Function App → **Overview** → **Get publish profile** (top-menuen). En XML-fil downloades.

Åbn [GitHub → repo settings → Secrets and variables → Actions → New repository secret](https://github.com/hammerbamsen/fast-as-50/settings/secrets/actions/new):
- **Name:** `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`
- **Value:** hele indholdet af XML-filen (åbn i teksteditor, kopier alt, indsæt)

Tryk **Add secret**.

---

## Trin 6 — Aktivér MSAL på klienten (2 min)

Rediger `data/auth_config.json` direkte på GitHub (blyanten øverst højre på filens side):

```json
{
  "enabled": true,
  "tenantId": "<Directory (tenant) ID fra trin 1>",
  "clientId": "<Application (client) ID fra trin 1>",
  "functionAppUrl": "https://fast-as-fifty-plan.azurewebsites.net"
}
```

Commit direkte til main.

---

## Trin 7 — Verificér (2 min)

1. **Test health-endpointet:** Åbn `https://fast-as-fifty-plan.azurewebsites.net/api/health` i browseren. Skal svare:
   ```json
   {"ok": true, "tenant_configured": true, "client_configured": true, "gh_token_configured": true, "allowed_upns_count": 1}
   ```
   Hvis en er `false`: tjek App Settings i trin 3.

2. **Test login:** Åbn `https://hammerbamsen.github.io/fast-as-50/plan.html`. Første gang: bliver redirected til Microsoft-login, log ind med `kennet@hammerby.com`, redirected tilbage. Herefter loader planen som normalt.

3. **Test en ændring:** Tap en fremtidig dag → Justér → ændr en note → Gem. Verificér grønt "Opdateret."

---

## Fejlfinding

**"invalid_client" ved login:** SPA-platformen er ikke aktiveret i trin 1. Tilbage til App Registration → Authentication → verificér at Single-page application er valgt.

**"AADSTS50011: reply URL does not match":** Redirect URI'en er ikke tilføjet præcist. Skal være uden trailing slash: `https://hammerbamsen.github.io/fast-as-50/plan.html`.

**Function App returnerer 502 Bad Gateway ved plan-edit:** Deployment er ikke gennemført endnu. Tjek Actions-fanen — den første deploy sker automatisk efter Trin 5.

**"CORS policy blocked":** ALLOWED_ORIGIN eller CORS-listen har ikke `https://hammerbamsen.github.io` — tjek trin 3 og 4.

**Du vil rotere PAT'et:** Erstat `GH_TOKEN` i Function App's Environment variables. Klienten er upåvirket — samme login virker.

---

## Sådan virker det

```
plan.html på iPhone (Safari)
    ↓ (MSAL.js henter access token via din Outlook-session — tavs)
    ↓ POST med Bearer-token
Azure Function (West Europe)
    ↓ Validerer JWT mod Microsofts nøgler
    ↓ Tjekker at UPN er kennet@hammerby.com
    ↓ Læser GH_TOKEN fra App Setting
    ↓ Videresender som repository_dispatch
GitHub Actions (plan-edit workflow)
    ↓ Kører apply_edit.py (som før)
plan.json + Intervals + Outlook + Word + OneDrive synkroniseret
```

Dit token forlader aldrig Azure. Klienten kender kun din Microsoft-session — som du alligevel logger ind på via Outlook. Ingen credentials at miste.
