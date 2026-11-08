"""Ren logik til at oprette planlagte pas i Intervals fra plan-edit (apply_edit).

Baggrund (8/11-2026): Intervals udleder varighed af description-teksten, når den
kan. For svøm læses "400m" som 400 minutter (1200 min for et 45-min pas), og for
styrke summeres kun de linjer der har en tid (31 min i stedet for 45). Derfor
sendes planens moving_time og load efter oprettelsen med en PUT, når Intervals'
tal afviger. Samme load-estimat som build_workouts.estimate_load.
"""

_LOAD_IF2 = {"Ride": 0.45, "VirtualRide": 0.45, "Run": 0.55, "Swim": 0.50,
             "OpenWaterSwim": 0.50, "WeightTraining": 0.40, "Hike": 0.18, "Walk": 0.12}


def estimate_load(wo: dict) -> int:
    hours = (wo.get("moving_time") or 3600) / 3600.0
    return max(round(hours * _LOAD_IF2.get(wo.get("type"), 0.45) * 100), 1)


def build_payload(day_iso: str, wo: dict) -> dict:
    p = {
        "start_date_local": f"{day_iso}T06:00:00",
        "category": "WORKOUT",
        "type": wo.get("type") or "Workout",
        "name": wo["name"],
        "moving_time": wo.get("moving_time", 0),
        "description": wo.get("description", ""),
        "external_id": f"fas50-{day_iso}-{(wo.get('type') or 'workout').lower()}",
    }
    if wo.get("workout_doc"):
        p["workout_doc"] = wo["workout_doc"]
    return p


def corrections(created: dict, wo: dict) -> dict:
    """Felter der skal PUT'es efter oprettelsen. Tom dict = intet at rette."""
    fix = {}
    planned = wo.get("moving_time") or 0
    if planned and abs((created.get("moving_time") or 0) - planned) > 60:
        fix["moving_time"] = planned
    if not created.get("icu_training_load") or "moving_time" in fix:
        load = wo.get("load")
        if not isinstance(load, (int, float)) or load <= 0:
            load = estimate_load(wo)
        if created.get("icu_training_load") and "moving_time" in fix \
                and wo.get("type") in ("Ride", "VirtualRide", "Run"):
            load = created["icu_training_load"]  # Intervals' TSS fra trin er bedre
        fix["icu_training_load"] = load
    return fix
