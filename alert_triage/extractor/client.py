"""Read-only client for Alessa's data calls, using the signed-in browser session's cookies."""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

from playwright.sync_api import APIRequestContext

from . import endpoints as ep
from ..config import ApiConfig

log = logging.getLogger("alessa")


class ForbiddenCall(RuntimeError):
    """Raised for any call that is not one of the known read endpoints."""


class SessionExpired(RuntimeError):
    """Alessa answered with a login page or 401/403 – the analyst needs to sign in again."""


class AlessaApi:
    def __init__(self, request: APIRequestContext, cfg: ApiConfig):
        self.req = request
        self.cfg = cfg
        self.calls = 0

    # ---- low level -------------------------------------------------------------------------
    def _call(self, e: ep.Endpoint, params: dict | None = None, body: dict | None = None) -> Any:
        if (e.method, e.path) not in ep.ALLOWED:
            raise ForbiddenCall(f"{e.method} {e.path} is not an allowed read call")
        q = {"_dc": int(time.time() * 1000), **ep.PAGING, **e.defaults, **(params or {})}
        if e.sort and e.method == "GET":
            q["Sort"] = json.dumps([{"property": e.sort, "direction": "DESC"}])
        url = self.cfg.url(e.path) + ("?" + urlencode(q) if e.method == "GET" else "")
        kw = {"timeout": self.cfg.timeout_ms, "max_redirects": 0, "fail_on_status_code": False}
        if e.method == "GET":
            resp = self.req.get(url, **kw)
        else:
            resp = self.req.post(url, data=json.dumps(body or {}), headers={"Content-Type": "application/json"}, **kw)
        self.calls += 1
        time.sleep(self.cfg.pause_between_calls_ms / 1000)
        ctype = resp.headers.get("content-type", "")
        if resp.status in (301, 302, 401, 403) or "json" not in ctype:
            raise SessionExpired(f"{e.name}: HTTP {resp.status} ({ctype or 'no content-type'}) – sign in again")
        if resp.status >= 400:
            raise RuntimeError(f"{e.name}: HTTP {resp.status}")
        return resp.json()

    def _paged(self, e: ep.Endpoint, key: str, params: dict) -> list[dict]:
        """Paged calls return {data: {TotalRecords, <key>: [...]}}; reads all pages."""
        size = self.cfg.case.page_size
        out: list[dict] = []
        for page in range(1, 51):
            j = self._call(e, {**params, "page": page, "PageIndex": page, "start": (page - 1) * size,
                               "Start": (page - 1) * size, "PageSize": size})
            data = j.get("data") or {}
            rows = data.get(key) or []
            out += rows
            total = data.get("TotalRecords") or j.get("total") or 0
            if len(rows) < size or len(out) >= total:
                break
        return out

    # ---- work items ---------------------------------------------------------------------
    def list_work_items(self, page: int, size: int) -> list[dict]:
        rs = self.cfg.result_set
        params = {
            **rs.extra_params, "ResultSetId": rs.result_set_id, "ProcessId": rs.process_id,
            "WorkItemTypeId": rs.work_item_type_id, "ResolutionType": rs.resolution_type,
            "WorkItemType": rs.work_item_type, "ResultSetTableName": rs.table_name,
            "page": page, "PageIndex": page, "start": (page - 1) * size, "Start": (page - 1) * size,
            "PageSize": size, "limit": size,
        }
        return self._call(ep.WORK_ITEM_LIST, params).get("data") or []

    def work_item_detail(self, work_item_id: int) -> dict:
        rs = self.cfg.result_set
        body = {**ep.DETAIL_BODY_TEMPLATE, "ResultSetId": str(rs.result_set_id), "ProcessId": str(rs.process_id),
                "WorkItemTypeId": rs.work_item_type_id, "WorkItems": [work_item_id], "WorkItemId": work_item_id}
        j = self._call(ep.WORK_ITEM_DETAIL, body=body)
        return ((j.get("result") or {}).get("model")) or {}

    def profile(self, work_item_id: int) -> Any:
        return self._call(ep.PROFILE, body={"workItemId": work_item_id})

    # ---- entity data --------------------------------------------------------------------
    def alerts(self, alessa_id: str, entity_id: str) -> list[dict]:
        return self._paged(ep.ALERTS, "TransMonAlerts", {"alessaId": alessa_id, "entityId": entity_id})

    def alert_transactions(self, alessa_id: str, alert_id: str) -> list[dict]:
        return self._paged(ep.ALERT_TRANSACTIONS, "TransMonAlertDetails", {"alessaId": alessa_id, "alertId": alert_id})

    def transactions(self, alessa_id: str, entity_id: str, start: str, end: str) -> list[dict]:
        return self._paged(ep.TRANSACTIONS, "Transactions", {"alessaId": alessa_id, "entityId": entity_id,
                                                             "transactionStartDate": start, "transactionEndDate": end})

    def accounts(self, alessa_id: str, entity_id: str) -> list[dict]:
        return self._paged(ep.ACCOUNTS, "Accounts", {"alessaId": alessa_id, "entityId": entity_id})

    def regulatory_reports(self, alessa_id: str, entity_id: str) -> list[dict]:
        return self._paged(ep.REG_REPORTS, "RegReports", {"alessaId": alessa_id, "entityId": entity_id})

    def risk_scores(self, alessa_id: str, entity_id: str, start: str, end: str) -> list[dict]:
        return self._paged(ep.RISK_SCORES, "RiskScores", {"alessaId": alessa_id, "entityId": entity_id,
                                                          "startDate": start, "endDate": end})

    def entity_resolution(self, alessa_id: str, entity_id: str) -> list[dict]:
        return self._paged(ep.RESOLUTIONS, "Resolutions", {"alessaId": alessa_id, "entityId": entity_id})
