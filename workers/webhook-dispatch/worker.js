// Fast as Fifty — Fase 3 token-fri trigger (Cloudflare Worker)
//
// Modtager et webhook-kald fra Intervals.icu (eller en anden aktivitets-
// kilde) når en ny aktivitet dukker op, og udløser med det samme
// repository_dispatch (event_type: "intervals-activity") mod GitHub —
// i stedet for at vente på update-kpi.yml's cron (hver 10.-30. min).
//
// webhook-receiver.yml (allerede i repoet) ignorerer selve payloaden og
// kører bare update_kpi.py på ny — så Worker'en behøver ikke forstå
// providerens fulde event-format, kun at afgøre OM den skal trigge.
//
// Autentificering mod GitHub sker som en GitHub App (ikke en PAT i
// browseren): Worker'en signerer en kortlivet JWT med App'ens private
// nøgle, bytter den til et installation-access-token, og bruger DET til
// selve dispatch-kaldet. Ingen langlivet hemmelighed rører browseren.
//
// ── Cloudflare-konfiguration (sættes i dashboardet, IKKE her) ──────────
// Vars (kan være almindelige, ikke-hemmelige):
//   GITHUB_APP_ID          = 4259031
//   GITHUB_INSTALLATION_ID = 145518829
//   GITHUB_REPO            = hammerbamsen/fast-as-50
// Secrets (Settings → Variables and Secrets → tilføj som "Secret"):
//   GITHUB_APP_PRIVATE_KEY = indholdet af .pem-filen, KONVERTERET til
//                            PKCS#8 først (se README i denne mappe — GitHub
//                            leverer PKCS#1, Web Crypto kræver PKCS#8):
//                              openssl pkcs8 -topk8 -inform PEM -outform PEM \
//                                -nocrypt -in original.pem -out pkcs8.pem
//   WEBHOOK_SECRET         = den delte hemmelighed du sætter op sammen med
//                            David (Intervals.icu) ved webhook-konfiguration
//
// ── Verifikations-TODO når Intervals.icu-webhooken er klar ─────────────
// Vi kender endnu ikke Intervals.icu's præcise verifikations-håndtryk
// (nogle providere bruger en GET med et "challenge"-query-param, andre en
// header med en delt hemmelighed, andre en HMAC-signatur af body'en).
// checkAuth() nedenfor tjekker de mest almindelige varianter (Bearer-token,
// X-Webhook-Secret-header, ?secret=-query) — juster den ud fra hvad David
// faktisk sender, når svaret kommer.

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Nogle webhook-providere verificerer endpointet med et GET-kald der
    // indeholder en "challenge", som skal ekkoes tilbage uændret.
    if (request.method === "GET") {
      const challenge =
        url.searchParams.get("hub.challenge") || url.searchParams.get("challenge");
      if (challenge) {
        return new Response(JSON.stringify({ "hub.challenge": challenge }), {
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("ok", { status: 200 });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    if (!checkAuth(request, url, env)) {
      return new Response("Unauthorized", { status: 401 });
    }

    let payload = {};
    try {
      payload = await request.json();
    } catch {
      // Tom body ved en evt. verifikations-ping — ingen fejl, bare ack.
      return new Response("ok (no body)", { status: 200 });
    }

    // Best-effort filter: udløs kun på aktivitets-agtige events. Kan ikke
    // vi genkende typen, udløser vi alligevel (sikker fallback — receiveren
    // trækker bare frisk data fra Intervals uanset payload-indhold).
    const eventType = String(
      payload.type || payload.event_type || payload.eventType || ""
    ).toLowerCase();
    if (eventType && !eventType.includes("activity")) {
      return new Response(`ignoreret event-type: ${eventType}`, { status: 200 });
    }

    try {
      const token = await getInstallationToken(env);
      await dispatchGitHub(env, token);
      return new Response("dispatched", { status: 200 });
    } catch (err) {
      console.error(err);
      return new Response(`fejl: ${err.message}`, { status: 500 });
    }
  },
};

function checkAuth(request, url, env) {
  if (!env.WEBHOOK_SECRET) return false;
  const authHeader = request.headers.get("authorization") || "";
  const bearer = authHeader.match(/^Bearer\s+(.+)$/i);
  const candidates = [
    bearer && bearer[1],
    request.headers.get("x-webhook-secret"),
    url.searchParams.get("secret"),
  ].filter(Boolean);
  return candidates.some((c) => c === env.WEBHOOK_SECRET);
}

async function getInstallationToken(env) {
  const jwt = await createAppJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
  const resp = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_INSTALLATION_ID}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fast-as-50-worker",
      },
    }
  );
  if (!resp.ok) {
    throw new Error(`installation-token fejlede: ${resp.status} ${await resp.text()}`);
  }
  const data = await resp.json();
  return data.token;
}

async function dispatchGitHub(env, token) {
  const resp = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "fast-as-50-worker",
      "content-type": "application/json",
    },
    body: JSON.stringify({ event_type: "intervals-activity" }),
  });
  if (!resp.ok) {
    throw new Error(`repository_dispatch fejlede: ${resp.status} ${await resp.text()}`);
  }
}

// ── GitHub App JWT (RS256), signeret med Web Crypto (ingen npm-pakker) ──

export async function createAppJwt(appId, privateKeyPem) {
  const header = { alg: "RS256", typ: "JWT" };
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iat: now - 60, // beskyt mod clock drift
    exp: now + 9 * 60, // maks 10 min tilladt af GitHub
    iss: String(appId),
  };

  const encHeader = base64url(JSON.stringify(header));
  const encPayload = base64url(JSON.stringify(payload));
  const signingInput = `${encHeader}.${encPayload}`;

  const key = await importPrivateKey(privateKeyPem);
  const signature = await crypto.subtle.sign(
    { name: "RSASSA-PKCS1-v1_5" },
    key,
    new TextEncoder().encode(signingInput)
  );

  return `${signingInput}.${base64urlFromBuffer(signature)}`;
}

async function importPrivateKey(pem) {
  const pkcs8 = pemToArrayBuffer(pem);
  return crypto.subtle.importKey(
    "pkcs8",
    pkcs8,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );
}

function pemToArrayBuffer(pem) {
  const b64 = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\r?\n|\r/g, "")
    .trim();
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function base64url(str) {
  return base64urlFromBuffer(new TextEncoder().encode(str));
}

function base64urlFromBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
