# -*- coding: utf-8 -*-
"""
EF paa fast rute — Fast as Fifty (27/11-2026).

`aerobic.py` maaler EF som median over 42 dage, men filtrerer stigningstunge
ture vaek (MAX_HM_PER_KM = 15), fordi GAP underkorrigerer paa stejlt terraen.
Fornalutx ligger paa 20-25 hm/km, saa ALLE Mallorca-ture er usynlige for EF —
netop de uger hvor basen bygges. Filteret er fagligt rigtigt: en bjergtur og en
flad grundtur kan ikke sammenlignes paa samme tal.

Loesningen er ikke at haeve graensen, men at maale paa SAMME rute: watt pr.
hjerteslag paa en kendt stigning, hvor laengde, stigning og retning er ens fra
gang til gang. Saa er tallet sammenligneligt fra lejr til lejr og aar til aar,
og det er den eneste maade EF kan sige noget om en bjerglejr.

Ruten findes i aktivitetens streams: det vindue hvor distancen og
hoejdemeterne matcher ruten inden for tolerancen. Ingen segment-API, ingen
manuel registrering.

Rene funktioner. Netvaerk og fil-I/O ligger i kalderen (update_kpi).
"""

try:
    from .vo2_dose import BIKE_TYPES
except ImportError:                       # tests importerer som top-level
    from vo2_dose import BIKE_TYPES

# Ruter. hm og km er ruten; tolerancerne skal rumme GPS-stoej og at man sjaeldent
# starter og stopper praecis ved skiltet.
ROUTES = {
    # Standardruten fra 28/11-2026 (Kennets eget tal): Fornalutx -> toppen.
    # Valgt frem for Sa Calobra fordi det er turen han faktisk koerer, og fordi
    # en laengere stigning giver et roligere W/slag — Sa Calobra blev aldrig
    # koert med puls og watt, saa serien stod tom.
    "puig_major": {
        "navn": "Puig Major",
        "km": 12.0, "hm": 700,
        "km_tol": 1.5, "hm_tol": 100,
        "note": "Fra Fornalutx til toppen. Maal det samme hver gang — tallet "
                "maa kun sammenlignes med sig selv.",
    },
    "sa_calobra": {
        "navn": "Sa Calobra",
        "km": 9.45, "hm": 627,
        "km_tol": 1.2, "hm_tol": 90,
        "note": "Fra Coll dels Reis-siden. PR 35:18 paa 275 W (2026).",
    },
}
# Ruten der maales paa, naar kalderen ikke siger andet. Gamle forsoeg paa andre
# ruter bliver liggende i serien — kortet filtrerer paa route.
DEFAULT_ROUTE = "puig_major"
MIN_ELEV_GAIN = 500        # billigt forfilter paa aktivitetsniveau
MIN_SAMPLES = 60           # under et minuts data er ikke en stigning
# Vinduet skal BEGYNDE hvor stigningen begynder og SLUTTE paa toppen. Uden det
# matcher et vilkaarligt 9,5 km-stykke midt paa en laengere stigning (Puig Major
# er 14 km / 800 hm og indeholder et stykke der ligner Sa Calobra), og et vindue
# der starter ude paa tilkoerslen udvander gennemsnitswatten.
FLAT_LOOKBACK = 120        # samples (ca. 2 min) foer start og efter top
FLAT_TOL_M = 15            # hoejdeaendring der stadig regnes som fladt


def _stream_map(streams):
    """Intervals' streams-svar -> {type: data}. Accepterer begge former."""
    if isinstance(streams, dict):
        return {k: (v or []) for k, v in streams.items()}
    out = {}
    for s in streams or []:
        if isinstance(s, dict) and s.get("type"):
            out[s["type"]] = s.get("data") or []
    return out


def _mean(xs):
    vals = [x for x in xs if isinstance(x, (int, float))]
    return sum(vals) / len(vals) if vals else None


def find_effort(streams, route=DEFAULT_ROUTE):
    """Find rutens vindue i en aktivitets streams.

    Returnerer {start_idx, end_idx, secs, km, hm, watts, hr, ef} eller None.
    Vaelger det vindue med flest hoejdemeter inden for tolerancen; ved
    uafgjort det korteste i tid, fordi det er selve stigningen og ikke en
    stigning med en pause i.
    """
    r = ROUTES.get(route)
    if not r:
        return None
    st = _stream_map(streams)
    dist, alt = st.get("distance") or [], st.get("altitude") or []
    if len(dist) < MIN_SAMPLES or len(alt) < MIN_SAMPLES:
        return None
    n = min(len(dist), len(alt))
    tid = st.get("time") or list(range(n))
    watts, hr = st.get("watts") or [], st.get("heartrate") or []

    lo_m, hi_m = (r["km"] - r["km_tol"]) * 1000, (r["km"] + r["km_tol"]) * 1000
    lo_hm, hi_hm = r["hm"] - r["hm_tol"], r["hm"] + r["hm_tol"]

    def starter_stigning(i):
        """Foer start var det fladt eller nedad — ellers er vi midt paa en stigning."""
        if i < FLAT_LOOKBACK:
            return True
        return (alt[i] or 0) - (alt[i - FLAT_LOOKBACK] or 0) <= FLAT_TOL_M

    def slutter_paa_top(k):
        """Efter slut gaar det ikke videre opad — ellers er toppen laengere fremme."""
        if k + FLAT_LOOKBACK >= n:
            return True
        return (alt[k + FLAT_LOOKBACK] or 0) - (alt[k] or 0) <= FLAT_TOL_M

    bedst, j = None, 0
    for i in range(n):
        if dist[i] is None or not starter_stigning(i):
            continue
        # ryk j frem til vinduet er langt nok
        while j < n and (dist[j] is None or dist[j] - dist[i] < lo_m):
            j += 1
        k = j
        while k < n and dist[k] is not None and dist[k] - dist[i] <= hi_m:
            gain = (alt[k] or 0) - (alt[i] or 0)
            if lo_hm <= gain <= hi_hm and slutter_paa_top(k):
                secs = (tid[k] if k < len(tid) else k) - (tid[i] if i < len(tid) else i)
                km = (dist[k] - dist[i]) / 1000
                kand = {"start_idx": i, "end_idx": k, "secs": int(secs),
                        "km": round(km, 2), "hm": int(round(gain))}
                # Stejlest vinder: det trimmer tilkoerslen af vinduet, saa
                # gennemsnitswatten er stigningens og ikke turens.
                kand["_grad"] = gain / km if km else 0
                if bedst is None or (kand["_grad"], kand["hm"]) > (bedst["_grad"], bedst["hm"]):
                    bedst = kand
            k += 1
    if bedst is None:
        return None
    bedst.pop("_grad", None)

    # Stejlest-reglen kan trimme de foerste og sidste minutter af stigningen med.
    # Udvid vinduet til stigningens rigtige graenser, saa tiden kan sammenlignes
    # med PR'en og ikke kun EF'en.
    STEP = 10
    i, k = bedst["start_idx"], bedst["end_idx"]
    while i - STEP >= 0 and (alt[i] or 0) - (alt[i - STEP] or 0) > 1:
        i -= STEP
    while k + STEP < n and (alt[k + STEP] or 0) - (alt[k] or 0) > 1:
        k += STEP
    bedst["start_idx"], bedst["end_idx"] = i, k
    bedst["secs"] = int((tid[k] if k < len(tid) else k) - (tid[i] if i < len(tid) else i))
    bedst["km"] = round(((dist[k] or 0) - (dist[i] or 0)) / 1000, 2)
    bedst["hm"] = int(round((alt[k] or 0) - (alt[i] or 0)))

    w = _mean(watts[i:k + 1]) if watts else None
    h = _mean(hr[i:k + 1]) if hr else None
    bedst["watts"] = round(w) if w else None
    bedst["hr"] = round(h) if h else None
    # EF paa fast rute: watt pr. hjerteslag. Samme enhed som aerobic.bike_ef,
    # saa tallene kan laeses side om side — men KUN sammenlignes rute for rute.
    bedst["ef"] = round(w / h, 3) if (w and h) else None
    return bedst


def is_candidate(act, bike_types=None):
    """Billigt forfilter: er det vaerd at hente streams for denne aktivitet?"""
    bike_types = BIKE_TYPES if bike_types is None else bike_types
    if bike_types and (act.get("type") or "") not in bike_types:
        return False
    gain = act.get("total_elevation_gain") or act.get("icu_elevation_gain") or 0
    return gain >= MIN_ELEV_GAIN


def record(act, effort, route=DEFAULT_ROUTE):
    """En raekke til serien. Noegle er aktivitetens id, saa en genkoersel ikke
    laver dubletter."""
    r = ROUTES.get(route) or {}
    return {
        "id": act.get("id"), "route": route, "navn": r.get("navn") or route,
        "date": (act.get("start_date_local") or act.get("start_date") or "")[:10],
        "secs": effort["secs"], "km": effort["km"], "hm": effort["hm"],
        "watts": effort["watts"], "hr": effort["hr"], "ef": effort["ef"],
        "actName": act.get("name"),
    }


def merge(serie, nye):
    """Flet nye raekker ind i serien paa aktivitets-id, sorteret paa dato."""
    ved = {r.get("id"): r for r in (serie or []) if r.get("id") is not None}
    for r in nye or []:
        if r.get("id") is not None:
            ved[r["id"]] = r
    return sorted(ved.values(), key=lambda r: (r.get("date") or "", r.get("id") or 0))


def card(serie, route=DEFAULT_ROUTE):
    """data.json-blokken. Farven sættes her, ikke i UI'et.

    Retningen er det eneste der betyder noget: stiger watt pr. hjerteslag paa
    samme stigning, er motoren blevet bedre. To forsoeg er minimum for en
    retning; med ett vises tallet uden dom.
    """
    rows = [r for r in (serie or []) if r.get("route") == route and r.get("ef")]
    r = ROUTES.get(route) or {}
    ud = {"navn": r.get("navn") or route, "note": r.get("note"),
          "efforts": rows, "n": len(rows), "color": "#7F8C8D", "status": None,
          "ef": None, "pct": None, "best_secs": None}
    if not rows:
        ud["status"] = "ingen forsøg endnu"
        return ud
    ud["ef"] = rows[-1]["ef"]
    ud["best_secs"] = min(x["secs"] for x in rows)
    if len(rows) == 1:
        ud["status"] = "første forsøg — ingen retning endnu"
        return ud
    pct = (rows[-1]["ef"] - rows[-2]["ef"]) / rows[-2]["ef"] * 100
    ud["pct"] = round(pct, 1)
    if pct >= 2:
        ud["color"], ud["status"] = "#27AE60", "motoren er blevet bedre"
    elif pct <= -2:
        ud["color"], ud["status"] = "#C0392B", "dyrere i puls end sidst"
    else:
        ud["color"], ud["status"] = "#F39C12", "uændret inden for støjen"
    return ud
