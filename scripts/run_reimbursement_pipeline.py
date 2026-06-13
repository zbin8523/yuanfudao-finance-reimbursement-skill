#!/usr/bin/env python3
"""Run collect -> extract -> plan -> dry-run for reimbursement automation."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(args: list[str], capture: bool = True) -> str:
    result = subprocess.run(args, text=True, capture_output=capture)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout if capture else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="Invoice source folders/files; defaults to ~/Downloads unless --mailmaster is used")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--include-mail-caches", action="store_true")
    parser.add_argument("--mailmaster", action="store_true", help="Export invoice-like attachments from MailMaster local indexes first")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--dry-run-browser", action="store_true")
    parser.add_argument("--workflow", default=None, help="travel/daily/payment or exact workflow name")
    args = parser.parse_args()

    started = time.time()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else Path(tempfile.mkdtemp(prefix="finance_reimb_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    collect_json = out_dir / "candidates.json"
    extract_json = out_dir / "invoices.json"
    plan_json = out_dir / "plan.json"

    source_paths = list(args.paths) if args.paths else ([] if args.mailmaster else ["~/Downloads"])
    mailmaster_export = None
    if args.mailmaster:
        mailmaster_export = out_dir / "mailmaster_export"
        mailmaster_export.mkdir(exist_ok=True)
        mail_json = out_dir / "mailmaster_index.json"
        mail_json.write_text(run([str(SCRIPTS / "mailmaster_invoice_index.py"), "--days", str(args.days), "--export-dir", str(mailmaster_export), "--downloaded-only"]), encoding="utf-8")
        source_paths = [str(mailmaster_export)] + source_paths

    collect_cmd = [str(SCRIPTS / "collect_invoices.py"), "--days", str(args.days), "--stage-dir", str(out_dir / "stage")]
    if args.include_mail_caches:
        collect_cmd.append("--include-mail-caches")
    collect_cmd.extend(source_paths)
    collect_json.write_text(run(collect_cmd), encoding="utf-8")
    candidates = json.loads(collect_json.read_text())
    def keep_candidate(item: dict) -> bool:
        name = item["filename"]
        if "电子行程单" in name and name.lower().endswith(".pdf"):
            return True
        if "保险" in name and name.lower().endswith(".pdf"):
            return True
        if "酒店" in name and "发票" in name and name.lower().endswith(".pdf"):
            return True
        if not args.mailmaster:
            return name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))
        return False
    filtered_candidates = [item for item in candidates if keep_candidate(item)]
    if filtered_candidates:
        candidates = filtered_candidates
    files = [item["path"] for item in candidates]
    if not files:
        raise RuntimeError("No invoice-like files found")

    extract_json.write_text(run([str(SCRIPTS / "invoice_extract.py"), *files]), encoding="utf-8")
    extracted_items = json.loads(extract_json.read_text())
    deduped_items = []
    seen_invoice_nos: set[str] = set()
    seen_files: set[str] = set()
    for item in extracted_items:
        invoice_no = item.get("invoice_no")
        if invoice_no:
            if invoice_no in seen_invoice_nos:
                continue
            seen_invoice_nos.add(invoice_no)
        else:
            key = item.get("filename") or item.get("path")
            if key in seen_files:
                continue
            seen_files.add(key)
        deduped_items.append(item)
    extract_json.write_text(json.dumps(deduped_items, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_cmd = [str(SCRIPTS / "plan_reimbursement.py"), str(extract_json)]
    if args.workflow:
        plan_cmd.extend(["--workflow", args.workflow])
    plan_json.write_text(run(plan_cmd), encoding="utf-8")
    plan = json.loads(plan_json.read_text())

    browser_dry_run = None
    if args.dry_run_browser:
        browser_dry_run = json.loads(run([str(SCRIPTS / "zhenguanyu_apply.py"), "dry-run", str(plan_json)]))

    summary = {
        "out_dir": str(out_dir),
        "elapsed_seconds": round(time.time() - started, 2),
        "candidate_count": len(candidates),
        "mailmaster_export": str(mailmaster_export) if mailmaster_export else None,
        "invoice_count": len(plan.get("invoice_nos", [])),
        "invoice_total": plan.get("invoice_total"),
        "rows": plan.get("rows", []),
        "plan_json": str(plan_json),
        "browser_dry_run": browser_dry_run,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
