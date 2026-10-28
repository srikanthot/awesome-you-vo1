"""Extract Entity 360 Master work items from Alessa through its data calls (read-only).

    python -m alert_triage.extractor.run --config config/alessa.yaml --max-items 3
    python -m alert_triage.extractor.run --config config/alessa.yaml --work-item 1779228

A browser window opens; sign in with your authenticator code if asked. The extractor then reads
the work items and writes one case package per work item to <output_dir>/cases/<id>.json,
plus <output_dir>/run_summary.json. Output is UNMASKED - it goes to the masking step next and
must stay inside the secure environment.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from .client import AlessaApi, SessionExpired
from ..config import ApiConfig, load_api_config
from .case_builder import build_case, select_rows
from .session import open_session

log = logging.getLogger("alessa")


def find_work_items(api: AlessaApi, cfg: ApiConfig, max_items: int) -> list[dict]:
    s = cfg.selection
    picked: list[dict] = []
    for page in range(1, s.max_pages + 1):
        rows = api.list_work_items(page, s.page_size)
        picked += select_rows(rows, cfg)
        if len(picked) >= max_items or len(rows) < s.page_size:
            break
    return picked[:max_items]


def extract(api: AlessaApi, cfg: ApiConfig, max_items: int, work_item_ids: list[int] | None = None) -> dict:
    out = Path(cfg.output_dir)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    summary = {"started_at": started.isoformat(timespec="seconds"), "found": 0, "extracted": 0, "failed": 0,
               "errors": {}, "warnings": {}, "seconds_per_item": None, "calls": 0}
    targets = [{"_Monitor_WorkItemID": w} for w in work_item_ids] if work_item_ids else find_work_items(api, cfg, max_items)
    summary["found"] = len(targets)
    times = []
    for row in targets:
        wid = row["_Monitor_WorkItemID"]
        try:
            case = build_case(api, cfg, row=row if not work_item_ids else None, work_item_id=wid)
            (out / "cases" / f"{wid}.json").write_text(json.dumps(case, indent=2, default=str))
            summary["extracted"] += 1
            times.append(case["meta"]["seconds"])
            if case["meta"]["warnings"]:
                summary["warnings"][str(wid)] = case["meta"]["warnings"]
            log.info("%s ok - %s", wid, case["meta"]["counts"])
        except SessionExpired:
            raise
        except Exception as exc:  # one bad work item must not stop the run
            summary["failed"] += 1
            summary["errors"][str(wid)] = f"{type(exc).__name__}: {exc}"[:400]
            log.error("%s failed: %s", wid, exc)
    summary["seconds_per_item"] = round(sum(times) / len(times), 2) if times else None
    summary["calls"] = api.calls
    summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="Read-only Alessa extractor (data calls)")
    ap.add_argument("--config", required=True)
    ap.add_argument("--max-items", type=int)
    ap.add_argument("--work-item", type=int, action="append", help="extract these work item IDs only")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_api_config(a.config)
    if "<" in cfg.base_url or not cfg.result_set.result_set_id or not cfg.result_set.table_name:
        raise SystemExit("Fill config/alessa.yaml (copied from config/alessa.example.yaml) and .env first: "
                         "base_url, result_set_id, process_id, table_name.")
    with sync_playwright() as pw:
        ctx = open_session(pw, cfg)
        try:
            api = AlessaApi(ctx.request, cfg)
            s = extract(api, cfg, a.max_items or cfg.selection.max_items, a.work_item)
        finally:
            ctx.close()
    print(json.dumps({k: v for k, v in s.items() if k not in ("errors", "warnings")}, indent=2))
    return s


if __name__ == "__main__":
    main()
