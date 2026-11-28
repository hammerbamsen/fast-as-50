# -*- coding: utf-8 -*-
"""Tests af orkestratoren scripts/apply_edit.py (ikke modulet edit_apply).

Baggrund 28/11-2026: en dublet-dispatch af forslaget 2026-11-28-hegnet-c-loeb
(allerede accepteret kl. 12:53) faeldte plan-edit kl. 12:58 med rc=1. Kennet saa
en roed alarm i systemkortet for en anmodning der bare var overfloedig, og
klienten fik intet svar at polle.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    """apply_edit.py laeser secrets paa modul-niveau, saa env saettes foerst."""
    os.environ.setdefault("GITHUB_TOKEN", "test-token")
    os.environ.setdefault("GITHUB_REPOSITORY", "hammerbamsen/fast-as-50")
    os.environ.setdefault("INTERVALS_API_KEY", "test-key")
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "faf_apply_edit_entry", ROOT / "scripts" / "apply_edit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, raiser):
    mod = _load_module()
    written = {}
    monkeypatch.setattr(mod, "gh_get", lambda path, ref=None: ("sha123", "{}"))
    monkeypatch.setattr(mod, "write_result",
                        lambda rid, payload: written.update({"rid": rid, **payload}))
    monkeypatch.setattr(mod.edit_apply, "apply_edit", raiser)
    monkeypatch.setenv("GH_EVENT_PAYLOAD", json.dumps({"client_payload": {
        "requestId": "rtest1",
        "action": "apply_proposal",
        "entryId": "proposal:2026-11-28-hegnet-c-loeb",
        "params": {},
        "athlete": "kennet",
    }}))
    return mod, written


def test_afgjort_forslag_giver_reject_ikke_crash(monkeypatch):
    def raiser(*a, **kw):
        raise ValueError("Forslag '2026-11-28-hegnet-c-loeb' er allerede afgjort (accepted)")

    mod, written = _run(monkeypatch, raiser)
    mod.main()   # maa ikke kaste: koerslen skal blive groen

    assert written["rid"] == "rtest1"
    assert written["status"] == "reject"
    assert written["action"] == "apply_proposal"
    assert "allerede afgjort" in written["gate"]["msg"]
    assert written["gate"]["flags"] == []      # klienten forventer objekter, ikke strenge
    assert written["dates_changed"] == []
    assert "plan_commit" not in written        # planen maa ikke vaere roert


def test_aegte_kodefejl_faelder_stadig_koerslen(monkeypatch):
    def raiser(*a, **kw):
        raise KeyError("status")

    mod, written = _run(monkeypatch, raiser)
    with pytest.raises(KeyError):
        mod.main()
    assert written == {}
