from modules import intervals_event as ie

SWIM = {"name": "Svøm 1500m", "type": "Swim", "moving_time": 2700,
        "description": "- 400m varm-op Z1 8m freeride", "workout_doc": {"steps": []}}
STYRKE = {"name": "Styrke A", "type": "WeightTraining", "moving_time": 2700, "description": "3x\n- x 1m"}
RIDE = {"name": "Tær 2x20", "type": "Ride", "moving_time": 4740, "description": "- a 20m 95%"}


def test_svoem_1200_min_rettes_til_45():
    fix = ie.corrections({"moving_time": 72000, "icu_training_load": None}, SWIM)
    assert fix == {"moving_time": 2700, "icu_training_load": 38}


def test_styrke_31_min_rettes_og_faar_load():
    fix = ie.corrections({"moving_time": 1860}, STYRKE)
    assert fix == {"moving_time": 2700, "icu_training_load": 30}


def test_cykel_med_korrekt_tid_og_tss_roeres_ikke():
    assert ie.corrections({"moving_time": 4740, "icu_training_load": 92}, RIDE) == {}


def test_planens_load_bruges_hvis_angivet():
    wo = dict(STYRKE, load=25)
    assert ie.corrections({"moving_time": 2700}, wo) == {"icu_training_load": 25}


def test_payload_har_external_id_og_workout_doc():
    p = ie.build_payload("2026-11-19", SWIM)
    assert p["external_id"] == "fas50-2026-11-19-swim"
    assert p["workout_doc"] == {"steps": []} and p["moving_time"] == 2700
    assert "workout_doc" not in ie.build_payload("2026-11-19", STYRKE)
