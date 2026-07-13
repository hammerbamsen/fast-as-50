# -*- coding: utf-8 -*-
"""
Fueling-ramme — Fase 2 (ernærings-substans).

Beregner mål for carb/time, væske/time og natrium/time for et givet løb,
baseret på standard evidensbaserede defaults (IKKE individuelt kalibreret
endnu — det kræver svedtest/erfaring, som gennemgås med Martin senere).

Kilder til defaultværdier (bredt anerkendte ranges i sportsernærings-
litteraturen, fx Jeukendrup/IOC-konsensus 2011 om kulhydratindtag under
udholdenhed, ACSM om væske- og natriumbehov):
  - Kulhydrat: 60-90 g/t for events > 2.5t (kræver multiple transportable
    carbs — glucose+fructose-blanding — for at ramme 90g/t)
  - Væske: 500-750 ml/t som udgangspunkt, justeret for klima
  - Natrium: 300-700 mg/t som udgangspunkt, justeret for klima

Ren beregning — ingen I/O. Tal er BEVIDST konservative standardværdier,
ikke individuelt kalibrerede — markeres tydeligt i output via 'note'-feltet.
"""

RACES = {
    "medoc": {
        "name": "Marathon du Médoc",
        "discipline": "run",
        "est_duration_h": 4.5,
        "climate": "hot",       # september, Bordeaux, ofte 20-28C
    },
    "stelvio": {
        "name": "Stelvio",
        "discipline": "bike",
        "est_duration_h": 7.0,
        "climate": "variable",  # højde + stort temperaturspænd op ad passet
    },
}

DEFAULT_CARB_G_PER_H = (60, 90)
DEFAULT_FLUID_ML_PER_H = (500, 750)
DEFAULT_SODIUM_MG_PER_H = (300, 700)

CLIMATE_FLUID_ADJUST = {"cool": 0.85, "variable": 1.0, "hot": 1.25}
CLIMATE_SODIUM_ADJUST = {"cool": 0.85, "variable": 1.0, "hot": 1.3}


def fueling_targets(race_key, duration_h=None, climate=None):
    """Returnerer et dict med carb/væske/natrium-mål (lav/høj) for løbet.

    race_key: nøgle i RACES ("medoc" eller "stelvio"), eller ukendt/None
              for generisk brug (falder tilbage på 3t/variable klima).
    duration_h/climate: override af racets defaults hvis givet eksplicit.
    """
    race = RACES.get(race_key, {})
    dur = duration_h if duration_h is not None else race.get("est_duration_h", 3.0)
    clim = climate if climate is not None else race.get("climate", "variable")

    fluid_factor = CLIMATE_FLUID_ADJUST.get(clim, 1.0)
    sodium_factor = CLIMATE_SODIUM_ADJUST.get(clim, 1.0)

    carb_lo, carb_hi = DEFAULT_CARB_G_PER_H
    fluid_lo, fluid_hi = DEFAULT_FLUID_ML_PER_H
    sodium_lo, sodium_hi = DEFAULT_SODIUM_MG_PER_H

    if dur < 2.5:
        carb_lo, carb_hi = 30, 60

    return {
        "race_key": race_key,
        "race": race.get("name", race_key or "generisk"),
        "duration_h": dur,
        "climate": clim,
        "carb_g_per_h": {"low": carb_lo, "high": carb_hi},
        "fluid_ml_per_h": {
            "low": round(fluid_lo * fluid_factor),
            "high": round(fluid_hi * fluid_factor),
        },
        "sodium_mg_per_h": {
            "low": round(sodium_lo * sodium_factor),
            "high": round(sodium_hi * sodium_factor),
        },
        "total_carb_g": {
            "low": round(carb_lo * dur),
            "high": round(carb_hi * dur),
        },
        "note": "Standarddefaults — ikke individuelt kalibreret endnu (svedtest/erfaring m. Martin)",
    }


def all_race_targets():
    """Bekvemmelighedsfunktion: mål for begge nøgleløb (Médoc + Stelvio)."""
    return {key: fueling_targets(key) for key in RACES}
