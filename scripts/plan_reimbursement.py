#!/usr/bin/env python3
"""Build reimbursement rows from extracted invoice JSON."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def infer_dates(items: list[dict]) -> tuple[str | None, str | None]:
    dates: list[str] = []
    for item in items:
        text = item.get("text", "")
        for line in text.splitlines():
            if any(skip in line for skip in ["开票日期", "填开日期"]):
                continue
            for year, month, day in re.findall(r"(20\d{2})年(\d{2})月(\d{2})日", line):
                dates.append(f"{year}-{month}-{day}")
        for year, month, day in re.findall(r"日期\s*\n?(20\d{2})年(\d{2})月(\d{2})日", text):
            dates.append(f"{year}-{month}-{day}")
    return (min(dates), max(dates)) if dates else (None, None)


WORKFLOW_ALIASES = {
    "travel": "差旅费申请",
    "trip": "差旅费申请",
    "差旅": "差旅费申请",
    "差旅费": "差旅费申请",
    "差旅费申请": "差旅费申请",
    "daily": "日常报销申请",
    "日常": "日常报销申请",
    "日常报销": "日常报销申请",
    "日常报销申请": "日常报销申请",
    "entertainment": "日常报销申请",
    "招待": "日常报销申请",
    "招待费": "日常报销申请",
    "payment": "付款申请",
    "付款": "付款申请",
    "付款申请": "付款申请",
}


def normalize_workflow(value: str | None, items: list[dict]) -> str:
    if value:
        return WORKFLOW_ALIASES.get(value.strip(), value.strip())
    categories = {item.get("category_hint") or "" for item in items}
    if any(category.startswith("日常报销") for category in categories):
        return "日常报销申请"
    if any(category in {"火车/机票费", "住宿费(普票)", "交通费"} for category in categories):
        return "差旅费申请"
    return "日常报销申请"


def map_category_for_workflow(category: str, workflow: str) -> str:
    if workflow == "日常报销申请" and category.startswith("日常报销/"):
        return category.split("/", 1)[1]
    return category


def build_plan(items: list[dict], workflow: str | None = None) -> dict:
    workflow_name = normalize_workflow(workflow, items)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        category = map_category_for_workflow(item.get("category_hint") or "待确认", workflow_name)
        grouped[category].append(item)
    rows = []
    for category, group in grouped.items():
        amount = round(sum(float(item.get("amount") or 0) for item in group), 2)
        invoice_nos = [item.get("invoice_no") for item in group if item.get("invoice_no")]
        filenames = [item.get("filename") for item in group]
        if category == "火车/机票费":
            description = f"往返机票及相关保险：{'+'.join(str(item.get('amount')) for item in group if item.get('amount'))}"
        elif category.startswith("住宿费"):
            description = "住宿费：" + "、".join(filenames[:3])
        else:
            description = "、".join(filenames[:3])
        rows.append({
            "expense_type": category,
            "amount": amount,
            "description": description,
            "invoice_nos": invoice_nos,
            "files": [item.get("path") for item in group],
        })
    start_date, end_date = infer_dates(items)
    return {
        "workflow": workflow_name,
        "company": "DEFAULT_COMPANY",
        "payment_method": "网银转账（工资卡）",
        "currency": "CNY",
        "start_date": start_date,
        "end_date": end_date,
        "rows": rows,
        "invoice_total": round(sum(float(item.get("amount") or 0) for item in items), 2),
        "invoice_nos": [item.get("invoice_no") for item in items if item.get("invoice_no")],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", help="Output from invoice_extract.py")
    parser.add_argument("--workflow", default=None, help="travel/daily/payment or exact workflow name")
    args = parser.parse_args()
    items = json.loads(Path(args.json_file).read_text())
    print(json.dumps(build_plan(items, args.workflow), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
