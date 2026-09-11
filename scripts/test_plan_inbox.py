# -*- coding: utf-8 -*-
"""Tests for scripts/plan_inbox.py::decode_payload — ren logik."""
import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_inbox as pi  # noqa: E402


def _ev(payload, html=False):
    b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
    content = f"<html><body><p>{b64[:50]}<br>{b64[50:]}</p></body></html>" if html else b64
    return {"id": "x", "subject": "FAF-INBOX t1",
            "body": {"contentType": "html" if html else "text", "content": content}}


def test_decode_text_and_html():
    p = {"action": "apply_proposal", "entryId": "proposal:t1", "params": {"proposal": {"id": "t1"}}}
    for html in (False, True):
        out = pi.decode_payload(_ev(p, html))
        assert out["action"] == "apply_proposal" and out["entryId"] == "proposal:t1"
        assert out["params"]["proposal"]["id"] == "t1"
        assert out["athlete"] == "kennet" and out["requestId"].startswith("inbox-")


def test_decode_rejects_missing_fields_and_garbage():
    with pytest.raises(ValueError):
        pi.decode_payload(_ev({"entryId": "x"}))
    with pytest.raises(ValueError):
        pi.decode_payload({"subject": "FAF-INBOX t", "body": {"content": "hej med dig"}})
