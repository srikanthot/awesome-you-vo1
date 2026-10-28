"""Runs the Alessa flow on case files: mask -> triage agent -> review file.

    python -m alert_triage.pipeline              # all cases in data/alessa/cases, fake model
    python -m alert_triage.pipeline --limit 3
    MODEL=apim python -m alert_triage.pipeline   # real model through APIM, once access is in place

Reads   data/alessa/cases/<id>.json     (written by the extractor, UNMASKED)
Writes  data/alessa/masked/<id>.json    (what the model sees)
        data/alessa/tokens/<id>.json    (token map – sensitive, keep internal)
        data/alessa/results/<id>.json   (agent output, masked)
        data/alessa/review/<id>.json    (unmasked recommendation + comment for the analyst)

Later the same steps run as separate workers on AKS, with Blob Storage and Service Bus in between.
"""
from __future__ import annotations

import argparse
import json
import logging
import time

from alert_triage.agent.agent import load_sop_rules, triage
from alert_triage.llm import ChatModel, get_model
from alert_triage.settings import get_settings
from alert_triage.storage import Store, get_store
from alert_triage.masking.masker import Masker, unmask

USE_CASE = "alessa"
log = logging.getLogger("pipeline")


def process_case(store: Store, name: str, masker: Masker, model: ChatModel, sop: str) -> dict:
    raw = store.get(USE_CASE, "cases", name)
    masked, tm = masker.mask(raw)
    store.put(USE_CASE, "masked", name, masked)
    store.put(USE_CASE, "tokens", name, tm.to_dict())
    result = triage(masked, model, sop)
    store.put(USE_CASE, "results", name, result.model_dump())
    tokens = tm.to_dict()
    review = {
        "work_item_id": raw["work_item"]["work_item_id"],
        "recommendation": result.recommendation,
        "confidence": result.confidence,
        "reasons": [unmask(r, tokens) for r in result.reasons],
        "rules_applied": result.rules_applied,
        "transactions_cited": result.transactions_cited,
        "draft_comment": unmask(result.draft_comment, tokens),
        "status": "pending_review",
    }
    store.put(USE_CASE, "review", name, review)
    return review


def main(argv=None) -> list[dict]:
    ap = argparse.ArgumentParser(description="Alessa: mask -> triage -> review (local)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", action="append", help="work item id(s) to process")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = get_settings()
    store, model, masker, sop = get_store(s), get_model(s), Masker(), load_sop_rules()
    names = store.list(USE_CASE, "cases")
    if a.only:
        names = [n for n in names if n.removesuffix(".json") in a.only]
    names = names[: a.limit] if a.limit else names
    out = []
    for n in names:
        t0 = time.time()
        try:
            r = process_case(store, n, masker, model, sop)
            out.append({"case": n, "recommendation": r["recommendation"], "seconds": round(time.time() - t0, 2)})
        except Exception as e:  # one bad case must not stop the run
            log.error("%s failed: %s", n, e)
            out.append({"case": n, "error": f"{type(e).__name__}: {e}"[:300]})
    print(json.dumps({"model": s.model, "storage": s.storage, "cases": out}, indent=2))
    return out


if __name__ == "__main__":
    main()
