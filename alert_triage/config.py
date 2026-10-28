"""Configuration for the Alessa endpoint extractor (config/alessa.yaml)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class SessionCfg(BaseModel):
    profile_dir: str = ".alessa-profile"  # browser profile that keeps the signed-in session (keep private)
    browser_channel: Optional[str] = None  # "msedge" to use installed Edge; None = bundled Chromium
    home_path: str = "/Home/Index"
    ready_selector: str = "text=Work Items"  # visible once Alessa has loaded after sign-in
    sign_in_timeout_s: int = 300  # time the analyst has to sign in (authenticator code)
    headless: bool = False  # sign-in needs a visible browser


class ResultSetCfg(BaseModel):
    """Entity 360 Master result set. Instance-specific values come from config/alessa.yaml."""
    result_set_id: int = 0          # set in config/alessa.yaml
    process_id: int = 0             # set in config/alessa.yaml
    work_item_type_id: int = 11
    resolution_type: int = 1
    work_item_type: int = 2
    table_name: str = ""            # set in config/alessa.yaml
    extra_params: dict = Field(default_factory=lambda: {
        "TimePeriodId": 0, "RiskId": -1, "WorkitemPropertyId": 0, "PrincipalId": 0, "IndicatorId": 0,
        "IndicatorValue": "", "UserId": 0, "DatabaseDateType": 0, "EntityId": 0, "IncludeChildrenInCount": "false",
        "ObjectId": 0, "ObjectTypeId": 0, "RunDateId": 0, "WorkItemTotalsProperty": 0, "ViewingFromProcessDashboard": 0,
        "ViewingSearchWorkItems": "", "StartDate": "0001-01-01T00:00:00", "EndDate": "0001-01-01T00:00:00",
        "WorkflowStateIdFieldTableName": "[WorkflowStates].[WorkflowStateID]", "WorkItemIdFieldTableName": "[wi].[WorkItemID]",
        "WorkflowAttachmentsFieldTableName": "[wi].[HasAttachments]", "WorkItemCommentsFieldTableName": "[wi].[HasComments]",
        "WorkItemWatchFieldTableName": "[wwl].[WorkItemID]", "WorkItemAssignToPrincipalFieldTableName": "[wi].[AssignTo]",
        "WorkItemDateAssignedFieldTableName": "[wi].[DateAssigned]", "WorkItemDateFirstDetectedFieldName": "wi.[DateFirstDetected]",
        "WorkItemDueDateFieldTableName": "[wi].[DueDate]", "WorkItemIndicatorFieldTableName": "[wi].[HasIndicator]",
        "IsGeneric": "false", "FilterCondition": "", "GenericFilterColumns": "", "WorkflowId": -1, "WorkflowStateId": -1,
        "SearchFilterCondition": "", "ResetCache": "false",
    })


class SelectionCfg(BaseModel):
    """Which work items to extract. Filters apply to the list rows."""
    workflow_states: list[str] = ["Assigned"]  # _Monitor_WorkflowStateName values to include
    assigned_to: list[str] = []  # _Monitor_AssignTo values (e.g. the queue/user that holds items for AI); empty = any
    modules: list[str] = ["TM Alerts"]  # MODULES_UPDATED values; empty = any
    max_items: int = 5
    page_size: int = 100
    max_pages: int = 50


class CaseCfg(BaseModel):
    transaction_lookback_days: int = 365
    include: list[str] = ["accounts", "regulatory_reports", "risk_scores", "entity_resolution", "profile"]
    page_size: int = 1000


class ApiConfig(BaseModel):
    base_url: str
    timeout_ms: int = 30000
    pause_between_calls_ms: int = 150  # be gentle with the server
    session: SessionCfg = Field(default_factory=SessionCfg)
    result_set: ResultSetCfg = Field(default_factory=ResultSetCfg)
    selection: SelectionCfg = Field(default_factory=SelectionCfg)
    case: CaseCfg = Field(default_factory=CaseCfg)
    output_dir: str = "out"

    def url(self, path: str) -> str:
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")


def load_api_config(path: str | Path, **overrides) -> ApiConfig:
    """Load config/alessa.yaml. ALESSA_BASE_URL (env) overrides base_url; explicit overrides win last."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    env_base = os.environ.get("ALESSA_BASE_URL")
    if env_base:
        data["base_url"] = env_base
    data.update({k: v for k, v in overrides.items() if v is not None})
    return ApiConfig.model_validate(data)
