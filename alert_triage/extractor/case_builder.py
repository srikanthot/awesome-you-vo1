"""Builds one 'case package' per work item – everything the triage and commentary agents need."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from .client import AlessaApi
from ..config import ApiConfig

ROW_WORK_ITEM = {
    "work_item_id": "_Monitor_WorkItemID", "state": "_Monitor_WorkflowStateName", "assigned_to": "_Monitor_AssignTo",
    "date_assigned": "_Monitor_DateAssigned", "date_first_detected": "_Monitor_DateFirstDetected",
    "due_date": "_Monitor_DueDate", "has_comments": "_Monitor_HasComments", "has_attachments": "_Monitor_HasAttachments",
    "priority": "PRIORITY", "modules_updated": "MODULES_UPDATED", "modules_updated_on": "MODULES_UPDATED_ON",
}
ROW_ENTITY = {
    "alessa_id": "ALESSA_ID", "entity_id": "ENTITY_ID", "name": "NAME", "account_type": "ACCOUNT_TYPE",
    "business_relationship": "BUSINESS_RELATIONSHIP", "occupation": "OCCUPATION", "address": "ADDRESS",
    "city": "CITY", "state": "STATE", "country": "COUNTRY", "phone": "PHONE", "email": "EMAIL",
    "identification_type": "IDENTIFICATION_TYPE", "identification_value": "IDENTIFICATION_VALUE",
    "created_date": "CREATED_DATE", "risk_score": "RISK_SCORE", "risk_range": "RISK_RANGE", "risk_flag": "RISK_FLAG",
    "assessed_on": "ASSESSED_ON",
}
ALERT_FIELDS = {
    "alert_id": "AlertId", "rule_pattern": "RulePattern", "rule_name": "RuleName", "description": "Description",
    "priority": "Priority", "run_date": "RunDate", "resolution": "Resolution", "alert_type": "AlertType",
    "report_id": "ReportId", "work_item_id": "WorkItemId",
}
HISTORY_FIELDS = {
    "date": "DatePerformed", "performed_by": "PerformedByText", "action": "ActionDetails", "is_action": "IsAction",
    "comment": "CommentText", "manual_comments": "ManualComments", "predefined_comments": "PreDefinedComments",
    "attachments": "AttachmentsText",
}


def _pick(src: dict, mapping: dict) -> dict:
    return {k: _clean(src.get(v)) for k, v in mapping.items()}


def _clean(v: Any) -> Any:
    return None if v in ("", "--") else v


def record_to_dict(model: dict) -> dict:
    """Detail model 'Record' is a list of {Key, Value}; turn it into a dict."""
    return {r.get("Key"): _clean(r.get("Value")) for r in (model.get("Record") or []) if r.get("Key")}


def build_case(api: AlessaApi, cfg: ApiConfig, row: Optional[dict] = None, work_item_id: Optional[int] = None) -> dict:
    t0 = time.time()
    warnings: list[str] = []
    wid = int(work_item_id or row["_Monitor_WorkItemID"])
    detail = api.work_item_detail(wid)
    record = record_to_dict(detail)
    src = {**record, **(row or {})}  # list row wins where both have a value
    alessa_id = src.get("ALESSA_ID")
    entity_id = src.get("ENTITY_ID") or alessa_id
    if not alessa_id:
        raise RuntimeError(f"work item {wid}: no ALESSA_ID in list row or detail")

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=cfg.case.transaction_lookback_days)
    fmt = lambda d: d.strftime("%Y-%m-%dT00:00:00")  # noqa: E731

    transactions = api.transactions(alessa_id, entity_id, fmt(start), fmt(end))
    by_id = {t.get("TransactionId"): t for t in transactions}
    alerts = []
    for a in api.alerts(alessa_id, entity_id):
        trig = api.alert_transactions(alessa_id, a.get("AlertId"))
        full = []
        for t in trig:
            match = by_id.get(t.get("TransactionId"))
            if match is None:
                warnings.append(f"alert transaction {t.get('TransactionId')} is outside the {cfg.case.transaction_lookback_days}-day window; only id/amount/date included")
            full.append(match or t)
        alerts.append({**_pick(a, ALERT_FIELDS), "triggering_transactions": full})
    if not alerts:
        warnings.append("no TM alerts returned for this entity")

    case: dict[str, Any] = {
        "work_item": {**_pick(src, ROW_WORK_ITEM), "work_item_id": wid,
                      "result_set": detail.get("ResultSetName") or cfg.result_set.result_set_id},
        "entity": _pick(src, ROW_ENTITY),
        "alerts": alerts,
        "transactions": transactions,
        "history": [_pick(h, HISTORY_FIELDS) for h in (detail.get("ActionsTakenModels") or [])],
        "detail_record": record,
    }
    inc = set(cfg.case.include)
    if "accounts" in inc:
        case["accounts"] = api.accounts(alessa_id, entity_id)
    if "regulatory_reports" in inc:
        case["regulatory_reports"] = api.regulatory_reports(alessa_id, entity_id)
    if "risk_scores" in inc:
        case["risk_scores"] = api.risk_scores(alessa_id, entity_id, fmt(start), fmt(end))
    if "entity_resolution" in inc:
        case["entity_resolution"] = api.entity_resolution(alessa_id, entity_id)
    if "profile" in inc:
        case["profile"] = api.profile(wid)
    case["meta"] = {
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Alessa data endpoints (read-only)",
        "transaction_window": [fmt(start), fmt(end)],
        "counts": {"alerts": len(alerts), "triggering_transactions": sum(len(a["triggering_transactions"]) for a in alerts),
                   "transactions": len(transactions), "history": len(case["history"])},
        "warnings": warnings,
        "seconds": round(time.time() - t0, 2),
        "pii": "UNMASKED – send to the masking step before any AI call",
    }
    return case


def select_rows(rows: list[dict], cfg: ApiConfig) -> list[dict]:
    s = cfg.selection
    keep = []
    for r in rows:
        if s.workflow_states and r.get("_Monitor_WorkflowStateName") not in s.workflow_states:
            continue
        if s.assigned_to and r.get("_Monitor_AssignTo") not in s.assigned_to:
            continue
        if s.modules and r.get("MODULES_UPDATED") not in s.modules:
            continue
        keep.append(r)
    return keep
