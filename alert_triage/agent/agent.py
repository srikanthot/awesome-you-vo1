"""Alessa triage agent: masked case -> recommendation + draft comment.

For now this is a single model call with a checked JSON answer. When Foundry access is in place it
moves into a Microsoft Agent Framework workflow (triage agent + commentary agent, SOP retrieval from
Azure AI Search); the inputs and the TriageResult output stay the same.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from alert_triage.llm import ChatModel
from .schema import TriageResult
from .summarize import summarize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SYSTEM_PROMPT = (HERE / "prompts" / "triage_system.md").read_text(encoding="utf-8")


def load_sop_rules(path: Path = ROOT / "config" / "sop" / "alessa_rules.md") -> str:
    return path.read_text(encoding="utf-8")


def triage(masked_case: dict, model: ChatModel, sop_rules: str | None = None, retries: int = 1) -> TriageResult:
    system = SYSTEM_PROMPT.replace("{sop_rules}", sop_rules or load_sop_rules())
    user = json.dumps(summarize(masked_case), default=str)
    last_err = None
    for _ in range(retries + 1):
        answer = model.complete_json(system, user)
        try:
            return TriageResult.model_validate(answer)
        except ValidationError as e:  # ask again with the error, once
            last_err = e
            system = system + "\n\nYour previous answer was not valid JSON for this format: " + str(e)[:500]
    raise RuntimeError(f"model did not return a valid TriageResult: {last_err}")
