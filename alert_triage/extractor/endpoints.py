"""Alessa 5.5 read endpoints used by the extractor.

These are the same calls the Alessa screens make. Only the calls listed here may be sent;
anything else (Add Comment, Assign, Action, STR, ...) is refused by the client.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BASE = "/ResultsManagement"
E360 = BASE + "/EntityThreeSixty"


@dataclass(frozen=True)
class Endpoint:
    name: str
    method: str  # GET or POST (the two POSTs below are reads)
    path: str
    sort: str | None = None  # Alessa needs a Sort parameter on paged calls (alerts return 0 without it)
    defaults: dict = field(default_factory=dict)


PAGING = {"action": "read", "start": 0, "page": 1, "PageIndex": 1, "Start": 0}

WORK_ITEM_LIST = Endpoint("work_item_list", "GET", BASE + "/GridView/GetResultSetPage", "_Monitor_WorkItemID")
WORK_ITEM_DETAIL = Endpoint("work_item_detail", "POST", E360 + "/GetEntityThreeSixtyResultSetInitialInformation")
PROFILE = Endpoint("profile", "POST", E360 + "/GetEntityThreeSixtyProfileByWorkItemId")
ALERTS = Endpoint("alerts", "GET", E360 + "/GetPagedEntityThreeSixtyTransMonAlerts", "run_date",
                  {"alertType": "All", "searchText": ""})
ALERT_TRANSACTIONS = Endpoint("alert_transactions", "GET", E360 + "/GetEntityThreeSixtyTransMonAlertDetails",
                              "transaction_datetime")
TRANSACTIONS = Endpoint("transactions", "GET", E360 + "/GetPagedEntityThreeSixtyTransactions", "transaction_datetime",
                        {"searchText": "", "accountId": "", "accountType": ""})
ACCOUNTS = Endpoint("accounts", "GET", E360 + "/GetPagedEntityThreeSixtyAccounts", "account_created_date",
                    {"searchText": ""})
REG_REPORTS = Endpoint("regulatory_reports", "GET", E360 + "/GetPagedEntityThreeSixtyRegReports", "workitem_id",
                       {"searchText": ""})
RISK_SCORES = Endpoint("risk_scores", "GET", E360 + "/GetPagedEntityRiskScores", "assessed_on")
RESOLUTIONS = Endpoint("entity_resolution", "GET", E360 + "/GetPagedEntityThreeSixtyResolutions", "match_level",
                       {"searchText": ""})

ALL = [WORK_ITEM_LIST, WORK_ITEM_DETAIL, PROFILE, ALERTS, ALERT_TRANSACTIONS, TRANSACTIONS,
       ACCOUNTS, REG_REPORTS, RISK_SCORES, RESOLUTIONS]
ALLOWED = {(e.method, e.path) for e in ALL}

# Detail POST body, as the Alessa UI sends it (values from the Entity 360 Master result set).
DETAIL_BODY_TEMPLATE = {
    "WorkitemPropertyId": 0, "RiskId": -1, "TimePeriodId": 0, "WorkflowStateId": -1, "IndicatorId": 0,
    "IndicatorValue": None, "UserId": 0, "WorkItemTypeId": 11, "ResultSetId": "0", "WorkflowId": -1,
    "ResolutionType": 1, "WorkItemType": 2, "StartDate": "0001-01-01T00:00:00", "EndDate": "0001-01-01T00:00:00",
    "StartDateMS": "0001-01-01T00:00:00", "EndDateMS": "0001-01-01T00:00:00", "PrincipalId": 0, "ProcessId": "0",
    "DatabaseDateType": 0, "EntityId": 0, "IncludeChildrenInCount": False, "ObjectId": 0, "ObjectTypeId": 0,
    "RunDateId": 0, "WorkItemTotalsProperty": 0, "PageIndex": 1, "PageSize": 1, "IsGeneric": False,
    "FilterCondition": None, "GenericFilterColumns": None, "IsEntityThreeSixty": True,
}
