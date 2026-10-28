"""Model client. 'fake' for local work (no Azure needed); 'apim' calls the Foundry models in Canada
through the APIM AI Gateway once access is in place.

Only masked text is ever sent to a model.
"""
from __future__ import annotations

import json
from typing import Protocol

from .settings import Settings


class ChatModel(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


class FakeModel:
    """Returns a fixed, valid answer so the pipeline can be built and tested without Foundry.
    Keeps every prompt it receives so tests can check that no PII was sent."""

    def __init__(self):
        self.prompts: list[str] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.prompts.append(system + "\n" + user)
        case = json.loads(user)
        alerts = case.get("alerts") or []
        trig = [t.get("id") for a in alerts for t in a.get("triggering_transactions", [])][:5]
        return {
            "recommendation": "needs_review",
            "confidence": 0.0,
            "reasons": ["Fake model – no real analysis. Replace with MODEL=apim once Foundry access is ready."],
            "rules_applied": [a.get("rule_pattern") for a in alerts if a.get("rule_pattern")],
            "transactions_cited": trig,
            "draft_comment": f"{case['entity'].get('name')} – {len(alerts)} alert(s) reviewed. Placeholder comment from the fake model.",
        }


class ApimModel:
    def __init__(self, s: Settings):
        from openai import AzureOpenAI  # installed from requirements-azure.txt
        self.client = AzureOpenAI(azure_endpoint=s.apim_endpoint, api_key=s.apim_key, api_version=s.api_version)
        self.deployment = s.model_deployment

    def complete_json(self, system: str, user: str) -> dict:
        r = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(r.choices[0].message.content)


def get_model(s: Settings) -> ChatModel:
    return ApimModel(s) if s.model == "apim" else FakeModel()
