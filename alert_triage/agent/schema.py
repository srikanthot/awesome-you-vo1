"""What the triage agent must return. Checked before anything is stored or shown to an analyst."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TriageResult(BaseModel):
    recommendation: Literal["close", "escalate", "needs_review"]
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(min_length=1)
    rules_applied: list[str] = []          # SOP rules / alert patterns the decision relied on
    transactions_cited: list[str] = []     # transaction IDs the reasons refer to
    draft_comment: str                     # analyst-style comment, still masked
