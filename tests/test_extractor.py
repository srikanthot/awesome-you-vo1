"""Alessa extractor and the Power Automate script, tested against tests/mock_server.py.

Set PW_CHANNEL=msedge to use the installed Edge instead of a downloaded Chromium.
"""
import json
import os
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from alert_triage.extractor import endpoints as ep
from alert_triage.extractor.client import AlessaApi, ForbiddenCall, SessionExpired
from alert_triage.config import load_api_config
from alert_triage.extractor.run import extract
from alert_triage.extractor.session import open_session
from tests import mock_server as mock

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = os.environ.get("PW_CHANNEL") or None


@pytest.fixture(scope="module")
def url():
    srv, u = mock.start(0)
    yield u
    srv.shutdown()


@pytest.fixture()
def cfg(url, tmp_path):
    c = load_api_config(ROOT / "config" / "alessa.example.yaml", base_url=url)
    c.result_set.result_set_id = 9001           # match the mock
    c.result_set.process_id = 8001
    c.result_set.table_name = "RPT_TEST_Archive"
    c.session.browser_channel = CHANNEL
    c.session.headless = True
    c.session.profile_dir = str(tmp_path / "profile")
    c.session.sign_in_timeout_s = 5
    c.pause_between_calls_ms = 0
    c.output_dir = str(tmp_path / "out")
    return c


def sign_in(pw, cfg):
    """Stands in for the analyst signing in (authenticator code) in the opened window."""
    ctx = pw.chromium.launch_persistent_context(cfg.session.profile_dir, headless=True, channel=CHANNEL)
    p = ctx.new_page()
    p.goto(cfg.url("/Account/Login"))
    p.fill("#user", "analyst"); p.fill("#code", "123456"); p.click("#signin")
    p.wait_for_url("**/Home/Index")
    ctx.close()


def writes(url):
    return json.loads(urllib.request.urlopen(url + "/__writes").read())


def test_end_to_end_cases(cfg, url):
    with sync_playwright() as pw:
        sign_in(pw, cfg)
        ctx = open_session(pw, cfg)  # reuses the signed-in profile
        s = extract(AlessaApi(ctx.request, cfg), cfg, max_items=10)
        ctx.close()
    assert s["found"] == 5 and s["extracted"] == 5 and s["failed"] == 0  # Closed and non-TM items filtered out
    out = Path(cfg.output_dir) / "cases"
    c3 = json.loads((out / "1779303.json").read_text())
    assert len(c3["transactions"]) == 1203  # two pages of 1000
    a = c3["alerts"][0]
    assert a["rule_pattern"] == "Multiple Locations" and len(a["triggering_transactions"]) == 2
    assert "TransactionMethod" in a["triggering_transactions"][0]  # full transaction, not just id/amount/date
    assert c3["entity"]["alessa_id"] and c3["work_item"]["state"] == "Assigned"
    assert c3["accounts"] and "risk_scores" in c3 and "profile" in c3
    c2 = json.loads((out / "1779302.json").read_text())
    assert any(h["comment"] for h in c2["history"])  # analyst comment carried into history
    c4 = json.loads((out / "1779304.json").read_text())
    assert any("outside" in w for w in c4["meta"]["warnings"])  # old triggering txn flagged
    assert writes(url) == []


def test_single_work_item_by_id(cfg, url):
    with sync_playwright() as pw:
        sign_in(pw, cfg)
        ctx = open_session(pw, cfg)
        s = extract(AlessaApi(ctx.request, cfg), cfg, max_items=1, work_item_ids=[1779305])
        ctx.close()
    assert s["extracted"] == 1
    c = json.loads((Path(cfg.output_dir) / "cases" / "1779305.json").read_text())
    assert c["entity"]["alessa_id"] and c["alerts"]


def test_alerts_call_needs_sort(url):
    """Real Alessa quirk reproduced by the mock: without Sort the alerts call returns nothing."""
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=CHANNEL); ctx = b.new_context(); p = ctx.new_page()
        p.goto(url + "/Account/Login"); p.fill("#user", "a"); p.fill("#code", "1"); p.click("#signin")
        aid = mock.WORK_ITEMS[0]["ALESSA_ID"]
        r = ctx.request.get(f"{url}{ep.ALERTS.path}?alessaId={aid}&entityId={aid}&PageSize=1000").json()
        b.close()
    assert r["data"]["TransMonAlerts"] == []


def test_guard_refuses_writes(cfg, url):
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=CHANNEL); ctx = b.new_context()
        api = AlessaApi(ctx.request, cfg)
        with pytest.raises(ForbiddenCall):
            api._call(ep.Endpoint("add_comment", "POST", "/ResultsManagement/Comment/AddComment"), body={"text": "x"})
        b.close()
    assert writes(url) == []


def test_session_expired_is_detected(cfg):
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=CHANNEL); ctx = b.new_context()  # not signed in
        with pytest.raises(SessionExpired):
            AlessaApi(ctx.request, cfg).list_work_items(1, 10)
        b.close()


def test_power_automate_script(url):
    js = (ROOT / "automation" / "alessa_extract.js").read_text()
    js = (js.replace("%MaxItems%", "3").replace("%LookbackDays%", "365")
            .replace("%ResultSetId%", "9001").replace("%ProcessId%", "8001").replace("%ResultSetTable%", "RPT_TEST_Archive"))
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=CHANNEL); p = b.new_page()
        p.goto(url + "/Account/Login"); p.fill("#user", "a"); p.fill("#code", "1"); p.click("#signin")
        p.wait_for_url("**/Home/Index")
        out = json.loads(p.evaluate("(() => {" + js + "\nreturn ExecuteScript();})()"))
        b.close()
    assert out["count"] == 3
    c = out["cases"][0]
    assert c["alerts"] and c["alerts"][0]["triggering_transactions"] and c["transactions"]
    assert "TransactionMethod" in c["alerts"][0]["triggering_transactions"][0]
    assert writes(url) == []
