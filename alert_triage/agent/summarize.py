"""Turns a masked Alessa case into a compact view for the model: what fired, the triggering
transactions, a profile of the entity's activity, and the history. Keeps prompts short and focused."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def _amount(t: dict) -> float:
    for k in ("BaseCurrencyAmount", "BaseAmount", "PrimaryAmount", "Amount"):
        v = t.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0


def _txn(t: dict) -> dict:
    return {
        "id": t.get("TransactionId"),
        "date": (t.get("TransactionDate") or t.get("TransactionDateTime") or "")[:10],
        "amount": _amount(t),
        "currency": t.get("PrimaryCurrency") or t.get("BaseCurrency"),
        "method": t.get("TransactionMethod"),
        "type": t.get("TransactionType"),
        "source": t.get("TransactionSource"),
        "counterparty": t.get("SecondaryEntityName") or t.get("SecondaryEntityId"),
        "counterparty_country": t.get("SecondaryInstitutionCountry"),
        "description": t.get("TransactionDescription"),
    }


def activity_profile(txns: list[dict]) -> dict:
    by_method: dict[str, list[float]] = defaultdict(list)
    by_month: dict[str, float] = defaultdict(float)
    countries: Counter = Counter()
    counterparties: Counter = Counter()
    for t in txns:
        a = _amount(t)
        by_method[t.get("TransactionMethod") or "unknown"].append(a)
        by_month[(t.get("TransactionDate") or "")[:7]] += a
        if t.get("SecondaryInstitutionCountry"):
            countries[t["SecondaryInstitutionCountry"]] += 1
        cp = t.get("SecondaryEntityName") or t.get("SecondaryEntityId")
        if cp:
            counterparties[cp] += 1
    dates = sorted((t.get("TransactionDate") or "")[:10] for t in txns if t.get("TransactionDate"))
    return {
        "count": len(txns),
        "total_amount": round(sum(_amount(t) for t in txns), 2),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "by_method": {m: {"count": len(v), "total": round(sum(v), 2)} for m, v in by_method.items()},
        "by_month": {m: round(v, 2) for m, v in sorted(by_month.items()) if m},
        "counterparty_countries": dict(countries.most_common(10)),
        "top_counterparties": dict(counterparties.most_common(10)),
    }


def summarize(case: dict) -> dict[str, Any]:
    e, w = case.get("entity", {}), case.get("work_item", {})
    return {
        "work_item": {k: w.get(k) for k in ("work_item_id", "priority", "date_first_detected", "date_assigned", "state")},
        "entity": {k: e.get(k) for k in ("name", "business_relationship", "occupation", "account_type", "country",
                                         "risk_score", "risk_range", "risk_flag", "created_date")},
        "alerts": [{
            "alert_id": a.get("alert_id"), "rule_pattern": a.get("rule_pattern"), "rule_name": a.get("rule_name"),
            "description": a.get("description"), "run_date": a.get("run_date"), "priority": a.get("priority"),
            "triggering_transactions": [_txn(t) for t in a.get("triggering_transactions", [])],
        } for a in case.get("alerts", [])],
        "activity": activity_profile(case.get("transactions", [])),
        "history": [{k: h.get(k) for k in ("date", "performed_by", "action", "comment")} for h in case.get("history", [])
                    if h.get("comment") or h.get("action")],
        "prior_regulatory_reports": len(case.get("regulatory_reports") or []),
        "warnings": (case.get("meta") or {}).get("warnings", []),
    }
