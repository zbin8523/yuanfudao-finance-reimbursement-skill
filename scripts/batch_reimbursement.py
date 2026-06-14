#!/usr/bin/env python3
"""Build and optionally fill multiple reimbursement plans from a batch file.

Input CSV columns or JSON object keys:
- supplier: supplier/vendor name for grouping and summary
- business_option: business/project/category option shown to humans
- workflow: travel/daily/payment or exact workflow name
- paths: semicolon-separated files/folders containing invoices for this reimbursement
- description: optional extra description appended to each generated row
- company/payment_method/currency/start_date/end_date: optional plan overrides

This script never submits; browser filling stops before final submit.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(args: list[str]) -> str:
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout


def split_paths(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).replace("\n", ";").split(";") if part.strip()]


def load_batch(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = data.get("items") or data.get("rows") or []
        if not isinstance(data, list):
            raise ValueError("JSON batch must be a list or contain items/rows list")
        return [dict(item) for item in data]
    with path.open(newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def enrich_plan(plan: dict, item: dict, source_paths: list[str]) -> dict:
    overrides = ["company", "payment_method", "currency", "start_date", "end_date"]
    for key in overrides:
        if item.get(key):
            plan[key] = item[key]
    meta = {
        "supplier": item.get("supplier") or item.get("vendor") or "",
        "business_option": item.get("business_option") or item.get("business") or item.get("project") or "",
        "batch_id": item.get("batch_id") or item.get("id") or "",
        "source_paths": source_paths,
    }
    plan["batch_meta"] = meta
    extra_description = item.get("description") or item.get("memo") or ""
    prefix_parts = [part for part in [meta["supplier"], meta["business_option"], extra_description] if part]
    if prefix_parts:
        prefix = "；".join(prefix_parts)
        for row in plan.get("rows", []):
            row["description"] = f"{prefix}；{row.get('description') or ''}".strip("；")
    return plan


def build_one(item: dict, index: int, out_dir: Path, days: int) -> dict:
    source_paths = split_paths(item.get("paths") or item.get("files") or item.get("folder") or item.get("source"))
    if not source_paths:
        raise ValueError(f"Batch row {index} has no paths/files/folder/source")
    item_dir = out_dir / f"item_{index:03d}"
    item_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(SCRIPTS / "run_reimbursement_pipeline.py"), "--days", str(days), "--out-dir", str(item_dir)]
    if item.get("workflow"):
        cmd.extend(["--workflow", str(item["workflow"])])
    cmd.extend(source_paths)
    summary = json.loads(run(cmd))
    plan_path = item_dir / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan = enrich_plan(plan, item, source_paths)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "index": index,
        "supplier": plan.get("batch_meta", {}).get("supplier"),
        "business_option": plan.get("batch_meta", {}).get("business_option"),
        "workflow": plan.get("workflow"),
        "invoice_count": len(plan.get("invoice_nos", [])),
        "invoice_total": plan.get("invoice_total"),
        "plan_json": str(plan_path),
        "out_dir": str(item_dir),
        "pipeline_elapsed_seconds": summary.get("elapsed_seconds"),
        "status": "planned",
    }


def fill_plans(items: list[dict], concurrency: int) -> list[dict]:
    results = []
    browser = SCRIPTS / "zhenguanyu_apply.py"
    run([str(browser), "open"])
    for start in range(0, len(items), concurrency):
        chunk = items[start:start + concurrency]
        for item in chunk:
            output = run([str(browser), "fill-new-tab", item["plan_json"]])
            item = dict(item)
            item["fill_output"] = output.strip()
            item["status"] = "filled_before_submit"
            results.append(item)
        if start + concurrency < len(items):
            time.sleep(1)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_file", help="CSV or JSON batch file")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--fill", action="store_true", help="Open one tab per item and fill to pre-submit state; never submits")
    parser.add_argument("--concurrency", type=int, default=3, help="How many tabs to prepare per wave")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else Path(tempfile.mkdtemp(prefix="finance_batch_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    batch_rows = load_batch(Path(args.batch_file).expanduser())
    planned = [build_one(row, index + 1, out_dir, args.days) for index, row in enumerate(batch_rows)]
    filled = fill_plans(planned, max(1, min(args.concurrency, 5))) if args.fill else planned
    summary = {
        "out_dir": str(out_dir),
        "count": len(filled),
        "will_not_submit": True,
        "items": filled,
    }
    (out_dir / "batch_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
