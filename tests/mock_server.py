"""Fake Alessa 5.5 data calls, shaped like a real Alessa instance. All data is fictional.

Copies the real behaviour that matters for the extractor:
- session cookie from a sign-in page; data calls without it redirect to the login page;
- work item list paged by Start/PageSize; detail and profile are POSTs;
- the alerts call returns nothing unless a Sort parameter is sent (real Alessa quirk);
- paged calls return {data: {PageIndex, PageSize, TotalRecords, <List>: [...]}, total};
- an Add Comment POST exists and records any write, so tests can prove none happen.
"""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

E = "/ResultsManagement/EntityThreeSixty/"
WRITES: list[str] = []
CALLS: list[str] = []


def _guid(n: int) -> str:
    return f"{n:08x}-a670-43ed-b42b-97c5abaa{n:04x}"


TODAY = date.today()
WORK_ITEMS = []
TXNS: dict[str, list[dict]] = {}
ALERTS: dict[str, list[dict]] = {}
for i in range(1, 8):
    wid = 1779300 + i
    aid = _guid(i)
    state = "Closed" if i == 6 else "Assigned"
    module = "Screening" if i == 7 else "TM Alerts"
    WORK_ITEMS.append({
        "_Monitor_WorkItemID": wid, "_Monitor_WorkflowStateName": state, "_Monitor_AssignTo": "AML Investigator",
        "_Monitor_DateAssigned": "2026-08-26T10:02:00", "_Monitor_DateFirstDetected": "2026-08-26T09:32:00",
        "_Monitor_DueDate": None, "_Monitor_HasComments": i == 2, "_Monitor_HasAttachments": False,
        "ALESSA_ID": aid, "ENTITY_ID": aid, "NAME": f"Test Entity {i}", "ACCOUNT_TYPE": "", "BUSINESS_RELATIONSHIP": "c1-van",
        "OCCUPATION": "", "ADDRESS": "", "CITY": "", "STATE": "", "COUNTRY": "CA", "PHONE": "", "EMAIL": "",
        "IDENTIFICATION_TYPE": "", "IDENTIFICATION_VALUE": "", "CREATED_DATE": "", "RISK_SCORE": "0", "RISK_RANGE": "",
        "RISK_FLAG": "", "ASSESSED_ON": "", "PRIORITY": "1", "MODULES_UPDATED": module, "MODULES_UPDATED_ON": "2026-09-30T10:02:00",
    })
    n = 1203 if i == 3 else 3 + i  # entity 3 has more than one page of transactions
    TXNS[aid] = [{
        "TransactionId": f"C1260{i:02d}{k:05d}", "TransactionDate": (TODAY - timedelta(days=k % 300)).isoformat() + "T10:23:44",
        "BaseCurrencyAmount": 1000 + k, "PrimaryAmount": 1000 + k, "PrimaryCurrency": "CAD", "TransactionMethod": "Wire Payments",
        "TransactionType": "LYXCT", "TransactionStatus": "Complete", "TransactionSource": "InboundWire",
        "PrimaryEntityId": aid, "PrimaryInstitutionName": "Test Credit Union", "PrimaryInstitutionCountry": "CA",
        "SecondaryInstitutionName": "Other Bank", "SecondaryInstitutionCountry": "CA", "TransactionDescription": "test",
    } for k in range(n)]
    ALERTS[aid] = [{
        "AlessaId": aid, "AlertId": f"{aid}_BA03W_CU-COAST_now", "AlertType": 2, "Priority": 1,
        "Description": f"{2} transactions totalling $17944.6", "RuleName": None, "RulePattern": "Multiple Locations",
        "ReportId": f"{aid}_BA03W_CU-COAST_now", "Resolution": 1, "RunDate": "2026-08-25T00:00:00", "WorkItemId": wid + 1000,
        "_txn_ids": [TXNS[aid][0]["TransactionId"], TXNS[aid][1]["TransactionId"]],
    }]
# entity 4: one triggering transaction is older than any lookback window
ALERTS[_guid(4)][0]["_txn_ids"].append("C1260OLD00001")


def paged(rows: list, q: dict, key: str) -> dict:
    size = int(q.get("PageSize", ["1000"])[0])
    start = int(q.get("Start", q.get("start", ["0"]))[0])
    chunk = rows[start:start + size]
    return {"data": {"PageIndex": int(q.get("PageIndex", ["1"])[0]), "PageSize": size, "TotalRecords": len(rows), key: chunk},
            "total": len(rows)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html, code=200, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(html.encode())

    def _authed(self):
        return "session=ok" in (self.headers.get("Cookie") or "")

    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query, keep_blank_values=True)
        if p == "/__writes":
            return self._json(WRITES)
        if p == "/__calls":
            return self._json(CALLS)
        if p == "/Account/Login":
            return self._html("<form method=post action=/Account/Login><input id=user name=u><input id=code name=c>"
                              "<button id=signin type=submit>Sign in</button></form>")
        if not self._authed():
            return self._html("", 302, {"Location": "/Account/Login"})
        CALLS.append("GET " + p)
        if p == "/Home/Index":
            return self._html("<div id=app><a>Dashboards</a> <a>Work Items</a></div>")
        if p == "/ResultsManagement/GridView/GetResultSetPage":
            if q.get("ResultSetId", [""])[0] != "9001":
                return self._json({"data": [], "total": 0})
            size = int(q.get("PageSize", ["100"])[0]); start = int(q.get("Start", ["0"])[0])
            return self._json({"data": WORK_ITEMS[start:start + size], "message": "{}", "total": 0})
        aid = q.get("alessaId", [""])[0]
        if p == E + "GetPagedEntityThreeSixtyTransMonAlerts":
            rows = [{k: v for k, v in a.items() if not k.startswith("_")} for a in ALERTS.get(aid, [])] if q.get("Sort") else []
            return self._json(paged(rows, q, "TransMonAlerts"))
        if p == E + "GetEntityThreeSixtyTransMonAlertDetails":
            alert = next((a for a in ALERTS.get(aid, []) if a["AlertId"] == q.get("alertId", [""])[0]), None)
            ids = alert["_txn_ids"] if alert else []
            rows = [{"TransactionId": t, "BaseAmount": 8972.3, "TransactionDate": "2020-01-01T00:00:00"} for t in ids]
            return self._json(paged(rows, q, "TransMonAlertDetails"))
        if p == E + "GetPagedEntityThreeSixtyTransactions":
            s, e = q["transactionStartDate"][0][:10], q["transactionEndDate"][0][:10]
            rows = [t for t in TXNS.get(aid, []) if s <= t["TransactionDate"][:10] <= e]
            return self._json(paged(rows, q, "Transactions"))
        if p == E + "GetPagedEntityThreeSixtyAccounts":
            return self._json(paged([{"AccountId": "01234567", "AccountType": "Chequing", "Currency": "CAD"}], q, "Accounts"))
        if p == E + "GetPagedEntityThreeSixtyRegReports":
            return self._json(paged([], q, "RegReports"))
        if p == E + "GetPagedEntityRiskScores":
            return self._json(paged([{"Score": 0, "AssessedOn": None}], q, "RiskScores"))
        if p == E + "GetPagedEntityThreeSixtyResolutions":
            return self._json(paged([], q, "Resolutions"))
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        if p == "/Account/Login":
            return self._html("", 302, {"Location": "/Home/Index", "Set-Cookie": "session=ok; Path=/; Max-Age=3600"})
        if not self._authed():
            return self._html("", 302, {"Location": "/Account/Login"})
        CALLS.append("POST " + p)
        if p == E + "GetEntityThreeSixtyResultSetInitialInformation":
            wid = json.loads(body or "{}").get("WorkItemId")
            row = next((w for w in WORK_ITEMS if w["_Monitor_WorkItemID"] == wid), None)
            if not row:
                return self._json({"result": None, "errorMessage": "not found"})
            history = [{"DatePerformed": "2026-08-26T10:02:23", "PerformedByText": "System", "ActionDetails": "Assign",
                        "IsAction": True, "CommentText": "", "ManualComments": None, "PreDefinedComments": None, "AttachmentsText": ""}]
            if row["_Monitor_HasComments"]:
                history.append({"DatePerformed": "2026-09-01T09:00:00", "PerformedByText": "Analyst A", "ActionDetails": "Add Comment",
                                "IsAction": False, "CommentText": "Reviewed prior activity; pattern consistent with payroll.",
                                "ManualComments": None, "PreDefinedComments": None, "AttachmentsText": ""})
            model = {"Id": wid, "ResultSetName": "Entity 360 Master", "ActionsTakenModels": history,
                     "Record": [{"Key": k, "Value": v} for k, v in row.items() if not k.startswith("_")]}
            return self._json({"result": {"model": model}, "errorMessage": ""})
        if p == E + "GetEntityThreeSixtyProfileByWorkItemId":
            return self._json({"result": {"Name": "Test", "CustomerSince": None}, "errorMessage": ""})
        WRITES.append(p)  # anything else is a write
        self._json({"ok": True})


def start(port: int = 0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


if __name__ == "__main__":
    s, url = start(8766)
    print("Mock Alessa data calls at", url)
    threading.Event().wait()
