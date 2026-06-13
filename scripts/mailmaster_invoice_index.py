#!/usr/bin/env python3
"""Read MailMaster local indexes for recent invoice-like emails.

Read-only: does not read credentials or mutate mail databases. It reports attachment metadata and
local paths when attachments have already been downloaded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path

KEYWORDS = ["发票", "电子发票", "行程单", "保险", "invoice", "报销"]
BASE = Path.home() / "Library/Containers/com.netease.macmail/Data/Library/Application Support/data"


@dataclass
class MailInvoiceAttachment:
    account: str
    mail_id: int
    mailbox: str | None
    subject: str | None
    froms: str | None
    received_raw: int | float | None
    received_guess: str | None
    attachment: str | None
    content_type: str | None
    size: int | None
    transferred_size: int | None
    local_path: str | None
    existing_paths: list[str]
    downloaded: bool


def table_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    return {row[1] for row in cur.execute(f"pragma table_info({table})")}


def guess_ts(value: int | float | None) -> float | None:
    if not value:
        return None
    candidates = []
    for div in [1, 1000, 1000000]:
        ts = value / div
        if 946684800 < ts < 4102444800:
            candidates.append(ts)
    return max(candidates) if candidates else None


def scan_account(account_dir: Path, days: int) -> list[MailInvoiceAttachment]:
    db = account_dir / "mail.db"
    if not db.exists():
        return []
    cutoff = time.time() - days * 86400
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    attachment_cols = table_columns(cur, "MailAttachment")
    disposition_expr = "a.DispositionFileName" if "DispositionFileName" in attachment_cols else "NULL"
    local_expr = "a.LocalPath" if "LocalPath" in attachment_cols else "NULL"
    transferred_expr = "a.TransferredSize" if "TransferredSize" in attachment_cols else "NULL"
    content_expr = "a.ContentType" if "ContentType" in attachment_cols else "NULL"
    query = f"""
      select m.LocalId,m.OrigDate,m.ReceivedDate,m.Mailbox,m.Subject,m.Froms,m.HasAttachments,
             a.Name as Name,{disposition_expr} as DispositionFileName,{local_expr} as LocalPath,
             a.Size as Size,{transferred_expr} as TransferredSize,{content_expr} as ContentType
      from MailMeta m left join MailAttachment a on a.MailId=m.LocalId
      where m.HasAttachments=1
      order by m.ReceivedDate desc
    """
    results: list[MailInvoiceAttachment] = []
    for row in cur.execute(query):
        subject = row["Subject"] or ""
        attachment = row["Name"] or row["DispositionFileName"] or ""
        haystack = f"{subject} {attachment}".lower()
        if not any(keyword.lower() in haystack for keyword in KEYWORDS):
            continue
        ts = guess_ts(row["ReceivedDate"] or row["OrigDate"])
        if ts and ts < cutoff:
            continue
        local = row["LocalPath"] or ""
        paths: list[Path] = []
        if local:
            raw = Path(local).expanduser()
            rel = local.lstrip("/")
            paths.extend([raw, account_dir / local, account_dir / rel, account_dir / "parts" / rel, account_dir / "attachments" / rel])
        # Some attachments are stored by name under account/view subfolders; search only relevant roots.
        if attachment:
            paths.extend(account_dir.rglob(attachment))
            view_root = account_dir.parents[1] / "view"
            if view_root.exists():
                paths.extend(view_root.rglob(attachment))
        existing = sorted({str(path) for path in paths if path.exists() and path.is_file()})
        results.append(MailInvoiceAttachment(
            account=account_dir.name,
            mail_id=row["LocalId"],
            mailbox=row["Mailbox"],
            subject=subject,
            froms=row["Froms"],
            received_raw=row["ReceivedDate"] or row["OrigDate"],
            received_guess=dt.datetime.fromtimestamp(ts).isoformat() if ts else None,
            attachment=attachment,
            content_type=row["ContentType"],
            size=row["Size"],
            transferred_size=row["TransferredSize"],
            local_path=local or None,
            existing_paths=existing,
            downloaded=bool(existing),
        ))
    con.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--base", default=str(BASE))
    parser.add_argument("--downloaded-only", action="store_true")
    parser.add_argument("--export-dir", default=None, help="Copy discovered attachment blobs/files to this folder using attachment names")
    args = parser.parse_args()
    base = Path(args.base).expanduser()
    all_results: list[MailInvoiceAttachment] = []
    for account_dir in sorted(path for path in base.iterdir() if path.is_dir()):
        all_results.extend(scan_account(account_dir, args.days))
    if args.export_dir:
        export_dir = Path(args.export_dir).expanduser()
        export_dir.mkdir(parents=True, exist_ok=True)
        for item in all_results:
            if not item.attachment or not item.existing_paths:
                continue
            src = Path(item.existing_paths[0])
            dst = export_dir / item.attachment
            if not dst.exists():
                shutil.copy2(src, dst)
            item.existing_paths = [str(dst)]
            item.local_path = str(dst)
            item.downloaded = True
    if args.downloaded_only:
        all_results = [item for item in all_results if item.downloaded]
    print(json.dumps([asdict(item) for item in all_results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
