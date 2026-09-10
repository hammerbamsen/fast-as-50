# -*- coding: utf-8 -*-
"""Tests for scripts/health_report.py — ren logik, ingen netværk.

Køres af CI: python3 -m pytest scripts/modules/ scripts/test_health_report.py -q
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import health_report as hr  # noqa: E402

NOW = datetime(2026, 9, 7, 5, 10, 0, tzinfo=timezone.utc)


def _run(**kw):
    base = {
        "name": "Daglig dashboard-opdatering",
        "conclusion": "success",
        "event": "schedule",
        "html_url": "https://github.com/hammerbamsen/fast-as-50/actions/runs/123",
        "run_started_at": "2026-09-07T04:29:48Z",
        "updated_at": "2026-09-07T04:31:12Z",
    }
    base.update(kw)
    return base


def test_merge_into_empty_creates_entry_with_expected_every_min():
    out = hr.merge_run(None, _run(), NOW)
    w = out["workflows"]["Daglig dashboard-opdatering"]
    assert w["lastRun"] == "2026-09-07T04:31:12Z"
    assert w["conclusion"] == "success"
    assert w["event"] == "schedule"
    assert w["runUrl"].endswith("/runs/123")
    assert w["durationS"] == 84
    assert w["expectedEveryMin"] == 60
    assert out["generatedAt"] == "2026-09-07T05:10:00Z"
    assert out["secrets"]["PRIVATE_REPO_TOKEN"]["expires"] == "2026-10-15"
    assert "Send daglig push-påmindelse" in out["secrets"]["PRIVATE_REPO_TOKEN"]["usedBy"]


def test_merge_keeps_other_workflows_and_overwrites_same():
    health = {
        "generatedAt": "2026-09-01T00:00:00Z",
        "workflows": {
            "Byg workouts i Intervals.icu": {"lastRun": "2026-09-06T05:01:00Z", "conclusion": "success"},
            "Daglig dashboard-opdatering": {"lastRun": "2026-09-06T23:00:00Z", "conclusion": "failure",
                                            "expectedEveryMin": 60},
        },
        "secrets": {},
    }
    out = hr.merge_run(health, _run(), NOW)
    assert out["workflows"]["Byg workouts i Intervals.icu"]["lastRun"] == "2026-09-06T05:01:00Z"
    assert out["workflows"]["Daglig dashboard-opdatering"]["conclusion"] == "success"
    assert out["workflows"]["Daglig dashboard-opdatering"]["lastRun"] == "2026-09-07T04:31:12Z"
    # input må ikke muteres
    assert health["workflows"]["Daglig dashboard-opdatering"]["conclusion"] == "failure"
    assert health["generatedAt"] == "2026-09-01T00:00:00Z"


def test_workflow_without_expectation_has_no_expected_every_min():
    out = hr.merge_run(None, _run(name="Slet Outlook event", event="workflow_dispatch"), NOW)
    w = out["workflows"]["Slet Outlook event"]
    assert "expectedEveryMin" not in w
    assert w["conclusion"] == "success"


def test_weekly_workflows_get_week_expectation():
    out = hr.merge_run(None, _run(name="Sync workouts til Outlook kalender"), NOW)
    assert out["workflows"]["Sync workouts til Outlook kalender"]["expectedEveryMin"] == 7 * 24 * 60


def test_missing_timestamps_give_none_duration_and_now_as_last_run():
    out = hr.merge_run(None, _run(run_started_at="", updated_at=""), NOW)
    w = out["workflows"]["Daglig dashboard-opdatering"]
    assert w["durationS"] is None
    assert w["lastRun"] == "2026-09-07T05:10:00Z"


def test_manual_run_without_workflow_only_refreshes_meta():
    health = {"generatedAt": "x", "workflows": {"A": {"conclusion": "success"}}, "secrets": {}}
    out = hr.merge_run(health, None, NOW)
    assert out["workflows"] == {"A": {"conclusion": "success"}}
    assert out["generatedAt"] == "2026-09-07T05:10:00Z"
    assert "PRIVATE_REPO_TOKEN" in out["secrets"]


def test_needs_alert():
    assert not hr.needs_alert(_run(conclusion="success"))
    assert not hr.needs_alert(_run(conclusion="skipped"))
    assert not hr.needs_alert(None)
    assert hr.needs_alert(_run(conclusion="failure"))
    assert hr.needs_alert(_run(conclusion="timed_out"))
    assert not hr.needs_alert(_run(conclusion="cancelled"))  # concurrency-kø, ikke fejl


def test_alert_text_uses_local_time_and_conclusion():
    title, body = hr.alert_text(_run(conclusion="failure"), NOW)
    assert title == "Workflow fejlede: Daglig dashboard-opdatering"
    # 04:31 UTC = 06:31 CEST
    assert body.startswith("failure · 07/09 06:31 · ")
    assert body.endswith("tryk for at se System-kortet")


def test_run_from_env():
    env = {"RUN_NAME": "CI — pytest", "RUN_CONCLUSION": "failure", "RUN_EVENT": "push",
           "RUN_URL": "u", "RUN_STARTED_AT": "2026-09-07T04:00:00Z", "RUN_UPDATED_AT": "2026-09-07T04:02:30Z"}
    r = hr.run_from_env(env)
    assert r["name"] == "CI — pytest" and r["conclusion"] == "failure"
    assert hr.duration_s(r) == 150
    assert hr.run_from_env({}) is None


# ── Nøgler: PAT vs GitHub App-token (9/9-2026) ─────────────────────────────

def test_secrets_pat_er_standard_og_har_udloeb():
    for mode in ("pat", "", None, "noget-andet"):
        s = hr.secrets_for(mode)
        assert list(s) == ["PRIVATE_REPO_TOKEN"], mode
        assert s["PRIVATE_REPO_TOKEN"]["expires"] == "2026-10-15"
        assert "Send daglig push-påmindelse" in s["PRIVATE_REPO_TOKEN"]["usedBy"]


def test_secrets_app_har_intet_udloeb():
    s = hr.secrets_for("APP ")
    assert list(s) == ["GitHub App (privat repo)"]
    e = s["GitHub App (privat repo)"]
    assert "expires" not in e            # dashboardet viser "ingen udløbsdato"
    assert "udløber ikke" in e["note"]
    assert e["usedBy"] == hr.PRIVATE_REPO_USED_BY


def test_secrets_er_kopier_ikke_delt_tilstand():
    a = hr.secrets_for("pat")
    a["PRIVATE_REPO_TOKEN"]["usedBy"].append("noget")
    assert "noget" not in hr.secrets_for("pat")["PRIVATE_REPO_TOKEN"]["usedBy"]


def test_merge_run_skifter_noegleblok_med_auth_mode():
    h = hr.merge_run(hr.empty_health(), None, NOW, "app")
    assert list(h["secrets"]) == ["GitHub App (privat repo)"]
    # Skift tilbage til PAT rydder app-posten (ingen efterladt spøgelse)
    h2 = hr.merge_run(h, None, NOW, "pat")
    assert list(h2["secrets"]) == ["PRIVATE_REPO_TOKEN"]
