# -*- coding: utf-8 -*-
"""
Friels periodisering — tabel 6.5 og 6.6, Fast After 50 (1. udgave, 2015).

Tabellerne er kodet her i stedet for at ligge som tekst i ugeformaalene, saa
dashboardet, ugebriefen og Outlook-markeringen kan vise den SAMME prioritet, og
saa gaten kan maale en uges indhold mod den. Uden det staar prioriteterne kun i
en bog paa Kennets natbord.

To ting afgoer prioriteten: hvilken FASE man er i, og hvor laenge loebet varer.
Friel deler loeb i over 4 timer, 2-4 timer og under 2 timer, fordi varigheden
styrer intensiteten. Kennets to maal er Stelvio (5-6 t) og TdS Ultrafondo
(8-11 t) — begge i kolonnen over 4 timer.

Anden udgave (juni 2026) vender budskabet: masters-atleter laver nu for meget
intensitet og for lidt aerob base. Uphill Athlete beskriver det som en
rekalibrering, ikke en modsigelse — rammen staar. For loeb over 4 timer peger
tabellen i forvejen samme vej: aerob taerskel er nummer et i baade Preparation,
Build og Peak-optakten. Kennet har foerste udgave.

Rene funktioner. Ingen netvaerk, ingen fil-I/O.
"""

# Tabel 6.5 — fasernes varighed i uger (min, max). Transition er 3 dage-4 uger.
VARIGHED = {
    "Preparation": (1, 6),
    "Early Base": (3, 6),
    "Late Base": (3, 6),
    "Build": (6, 9),
    "Peak": (1, 2),
    "Race": (1, 1),
    "Transition": (1, 4),
}

# Tabel 6.5 — hvad fasen er til for.
FORMAAL = {
    "Preparation": "Genopbyg en fast træningsrutine, gradvist.",
    "Early Base": "Maksimér styrke og begynd at bygge den aerobe form.",
    "Late Base": "Øg højintensitetsarbejdet og hold styrken.",
    "Build": "Træn med løbslignende pas og hold styrken.",
    "Peak": "Taper og simulér små stykker af målløbet. Hold styrken.",
    "Race": "Løbsuge. Hvil før løbet, hold løbsformen.",
    "Transition": "Restituér mentalt og fysisk efter en alvorlig træningsperiode.",
}

AET = "Aerob tærskel"
LT = "Laktattærskel"
AC = "Aerob kapacitet"
ST = "Styrke"
HVIL = "Hvil"

# Tabel 6.6 — prioritet pr. fase og loebsvarighed.
PRIORITET = {
    ">4t": {
        "Preparation": [AET, ST, AC],
        "Early Base": [ST, AET, AC],
        "Late Base": [AC, AET, LT, ST],
        "Build": [AET, LT, AC, ST],
        "Peak": [LT, ST],
        "Race": [LT],
        "Transition": [HVIL],
    },
    "2-4t": {
        "Preparation": [AET, ST, AC],
        "Early Base": [ST, AET, AC],
        "Late Base": [LT, AC, AET, ST],
        "Build": [LT, AET, AC, ST],
        "Peak": [LT, ST],
        "Race": [LT],
        "Transition": [HVIL],
    },
    "<2t": {
        "Preparation": [AET, ST, AC],
        "Early Base": [ST, AET, AC],
        "Late Base": [LT, AC, AET, ST],
        "Build": [AC, LT, AET, ST],
        "Peak": [AC, ST],
        "Race": [AC],
        "Transition": [HVIL],
    },
}

# Fasenavne i planen kan baere et nummer (Build 1, Peak 2) eller vaere skrevet
# med store bogstaver. Her oversaettes til tabellens navne.
ALIAS = {
    "PREP": "Preparation", "PREPARATION": "Preparation", "TRANSITION": "Transition",
    "EARLY BASE": "Early Base", "EARLYBASE": "Early Base", "BASE": "Early Base",
    "LATE BASE": "Late Base", "LATEBASE": "Late Base", "BASE+": "Late Base",
    "BUILD": "Build", "SPECIFIK": "Build", "STELVIO": "Peak",
    "PEAK": "Peak", "RACE": "Race", "TAPER": "Peak", "REST": "Transition",
}


def varighed_kolonne(timer):
    """Friels tre kolonner. `timer` er loebets forventede varighed."""
    if timer is None:
        return ">4t"
    if timer > 4:
        return ">4t"
    return "2-4t" if timer >= 2 else "<2t"


def normaliser(fase):
    """'Build 1' -> 'Build'. None hvis fasen ikke kan genkendes."""
    if not fase:
        return None
    t = str(fase).strip()
    # fjern et efterstillet nummer: "Build 2" -> "Build"
    dele = t.rsplit(" ", 1)
    if len(dele) == 2 and dele[1].isdigit():
        t = dele[0]
    return ALIAS.get(t.upper(), t if t in VARIGHED else None)


def prioriteter(fase, timer=None):
    """Prioriteret liste af pastyper for fasen. Tom liste hvis ukendt."""
    navn = normaliser(fase)
    if not navn:
        return []
    return list(PRIORITET[varighed_kolonne(timer)].get(navn, []))


def formaal(fase):
    return FORMAAL.get(normaliser(fase) or "", None)


def varighed_ok(fase, uger):
    """(ok, min, max) — ligger fasens laengde inden for Friels spaend?"""
    navn = normaliser(fase)
    if not navn or not isinstance(uger, int):
        return (None, None, None)
    lo, hi = VARIGHED[navn]
    return (lo <= uger <= hi, lo, hi)


def faser_i_plan(weeks):
    """Sammenhaengende faseafsnit af en liste uger med 'phase' og 'start'.

    [{navn, fase, fra, til, uger, start, ok, min, max}] i raekkefoelge. Bruges
    baade af dashboardet og af en QA der vil vide om en fase er for lang.
    """
    ud = []
    for w in weeks or []:
        f = w.get("phase")
        if ud and ud[-1]["fase"] == f:
            ud[-1]["til"] = w.get("week")
            ud[-1]["uger"] += 1
        else:
            ud.append({"fase": f, "navn": normaliser(f), "fra": w.get("week"),
                       "til": w.get("week"), "uger": 1, "start": w.get("start")})
    for a in ud:
        a["ok"], a["min"], a["max"] = varighed_ok(a["fase"], a["uger"])
    return ud


def kort(weeks, denne_uge=None, timer=None):
    """data.json-blokken til fasekortet.

    `denne_uge` er programugens nummer. Returnerer den aktive fase, hvor langt
    man er i den, hvornaar den slutter, og prioriteterne.
    """
    afsnit = faser_i_plan(weeks)
    if not afsnit:
        return None
    nu = None
    if denne_uge is not None:
        nu = next((a for a in afsnit if a["fra"] <= denne_uge <= a["til"]), None)
    nu = nu or afsnit[0]
    idx = afsnit.index(nu)
    naeste = afsnit[idx + 1] if idx + 1 < len(afsnit) else None
    i_fasen = (denne_uge - nu["fra"] + 1) if denne_uge is not None else None
    slut_uge = next((w for w in weeks if w.get("week") == nu["til"]), None)
    return {
        "fase": nu["fase"],
        "navn": nu["navn"],
        "formaal": formaal(nu["fase"]),
        "prioriteter": prioriteter(nu["fase"], timer),
        "uge_i_fasen": i_fasen,
        "uger_i_alt": nu["uger"],
        "tilbage": (nu["til"] - denne_uge) if denne_uge is not None else None,
        "slutter": (slut_uge or {}).get("start"),
        "naeste": naeste["fase"] if naeste else None,
        "varighed_ok": nu["ok"], "varighed_min": nu["min"], "varighed_max": nu["max"],
        "afsnit": afsnit,
        "kolonne": varighed_kolonne(timer),
    }
