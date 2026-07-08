# -*- coding: utf-8 -*-
"""
Integrationstest af send_push.run_send — den afsendelses-sti der IKKE kunne
verificeres via Actions (i dag var hviledag). Mocker afsendelsen via en
injiceret sender; ingen netværk, ingen VAPID. Køres af CI (X4).
"""
import json
import sys
from pathlib import Path

# send_push ligger i scripts/ (ét niveau op fra modules/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import send_push


def _plan(kennet_day=True, eva_day=True):
    days_k = []
    days_e = []
    if kennet_day:
        days_k.append({"date": "2026-07-14", "entries": [
            {"id": "k1", "workout": {"name": "Løb VO2 5×3 min Z4", "type": "Run"}}]})
    if eva_day:
        days_e.append({"date": "2026-07-14", "entries": [
            {"id": "e1", "workout": {"name": "Løbetur — 30 min", "type": "Run"}}]})
    return {"athletes": {"kennet": {"days": days_k}, "eva": {"days": days_e}}}


def _subs():
    return [
        {"endpoint": "https://push/kennet-1", "keys": {"p256dh": "a", "auth": "b"}, "athlete": "kennet"},
        {"endpoint": "https://push/eva-1", "keys": {"p256dh": "c", "auth": "d"}, "athlete": "eva"},
    ]


# ── afsendelse på en dag MED pas (den ikke-testede sti) ──────────

def test_sends_to_all_on_workout_day():
    calls = []
    def sender(sub, payload):
        calls.append((sub["endpoint"], json.loads(payload)))
        return True
    sent, dead, pruned = send_push.run_send(_plan(), _subs(), "2026-07-14", sender)
    assert sent == 2
    assert dead == set()
    assert pruned is None
    # Rigtig payload pr. atlet
    by = {ep: p for ep, p in calls}
    assert by["https://push/kennet-1"]["title"] == "I dag: Løb VO2 5×3 min Z4"
    assert by["https://push/eva-1"]["title"] == "I dag: Løbetur — 30 min"
    assert by["https://push/eva-1"]["url"] == "eva.html"


def test_payload_is_valid_json_with_required_fields():
    seen = {}
    def sender(sub, payload):
        seen["p"] = json.loads(payload); return True
    send_push.run_send(_plan(kennet_day=True, eva_day=False), _subs(), "2026-07-14", sender)
    p = seen["p"]
    for k in ("title", "body", "tag", "url"):
        assert k in p, f"payload mangler {k}"
    assert p["tag"] == "fast50-daily"


# ── hviledag: intet sendes ──────────────────────────────────────

def test_rest_day_sends_nothing():
    calls = []
    def sender(sub, payload):
        calls.append(sub); return True
    sent, dead, pruned = send_push.run_send(_plan(kennet_day=False, eva_day=False),
                                            _subs(), "2026-07-14", sender)
    assert sent == 0 and not calls


# ── dead-subscription cleanup ───────────────────────────────────

def test_dead_410_is_pruned():
    def sender(sub, payload):
        return 410 if "kennet" in sub["endpoint"] else True
    sent, dead, pruned = send_push.run_send(_plan(), _subs(), "2026-07-14", sender)
    assert sent == 1
    assert dead == {"https://push/kennet-1"}
    assert pruned is not None
    assert [s["endpoint"] for s in pruned] == ["https://push/eva-1"]


def test_transient_500_not_pruned():
    def sender(sub, payload):
        return 500   # midlertidig fejl — må IKKE fjerne subscription
    sent, dead, pruned = send_push.run_send(_plan(), _subs(), "2026-07-14", sender)
    assert sent == 0
    assert dead == set()
    assert pruned is None   # ingen oprydning ved forbigående fejl


def test_only_matching_athlete_gets_message():
    # Kun kennet har pas i dag -> kun kennets subscription rammes
    calls = []
    def sender(sub, payload):
        calls.append(sub["athlete"]); return True
    send_push.run_send(_plan(kennet_day=True, eva_day=False), _subs(), "2026-07-14", sender)
    assert calls == ["kennet"]
