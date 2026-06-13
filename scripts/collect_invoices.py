#!/usr/bin/env python3
"""Collect candidate invoice attachments from safe local sources.

This script does not read passwords, cookies, or mail account databases. It scans user-approved
folders and known exported/downloaded attachment locations.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

KEYWORDS = ["发票", "行程单", "invoice", "保险", "电子客票", "receipt", "报销"]
EXTS = {".pdf", ".ofd", ".png", ".jpg", ".jpeg", ".zip"}
DEFAULT_DIRS = ["~/Downloads", "~/Desktop", "~/Documents"]
MAIL_HINT_DIRS = [
    # NetEase Mail Master shared container. Only exported/cached attachment files are scanned.
    "~/Library/Group Containers/group.com.netease.macmail",
    "~/Library/Group Containers/group.com.netease.macmail/Library/Caches",
    "~/Library/Containers/com.netease.macmail/Data",
    "~/Library/Containers/com.netease.macmail/Data/tmp",
    # WeCom mail/temporary attachment locations. No cookies, credentials, or DB contents are read.
    "~/Library/Containers/com.tencent.WeWorkMac/Data/ATencent.WXWork.IPC-WeMail",
    "~/Library/Containers/com.tencent.WeWorkMac/Data/tmp",
    "~/Library/Containers/com.tencent.WeWorkMac/Data/Library/WecomPrivate",
]


@dataclass
class Candidate:
    path: str
    filename: str
    source: str
    mtime: float
    size: int


def is_candidate(path: Path) -> bool:
    if path.suffix.lower() not in EXTS:
        return False
    name = path.name.lower()
    return any(keyword.lower() in name for keyword in KEYWORDS)


def scan_dir(root: Path, days: int, source: str, max_depth: int) -> list[Candidate]:
    cutoff = time.time() - days * 86400
    results: list[Candidate] = []
    if not root.exists():
        return results
    root_depth = len(root.parts)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if len(path.parts) - root_depth > max_depth:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            continue
        if is_candidate(path):
            results.append(Candidate(str(path), path.name, source, stat.st_mtime, stat.st_size))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="Folders/files to scan first")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--include-mail-caches", action="store_true", help="Also scan known mail attachment/cache folders")
    parser.add_argument("--stage-dir", default=None, help="Copy candidates to this folder")
    parser.add_argument("--max-depth", type=int, default=5)
    args = parser.parse_args()

    scan_roots = [Path(p).expanduser() for p in args.paths] if args.paths else [Path(p).expanduser() for p in DEFAULT_DIRS]
    if args.include_mail_caches:
        scan_roots.extend(Path(p).expanduser() for p in MAIL_HINT_DIRS)

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for root in scan_roots:
        if root.is_file():
            if is_candidate(root):
                stat = root.stat()
                candidates.append(Candidate(str(root), root.name, "explicit", stat.st_mtime, stat.st_size))
            continue
        for candidate in scan_dir(root, args.days, str(root), args.max_depth):
            real = str(Path(candidate.path).resolve())
            if real not in seen:
                seen.add(real)
                candidates.append(candidate)

    candidates.sort(key=lambda item: item.mtime, reverse=True)
    if args.stage_dir:
        stage = Path(args.stage_dir).expanduser()
        stage.mkdir(parents=True, exist_ok=True)
        staged: list[Candidate] = []
        for candidate in candidates:
            src = Path(candidate.path)
            dst = stage / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
            candidate.path = str(dst)
            candidate.source = f"staged:{candidate.source}"
            staged.append(candidate)
            if dst.suffix.lower() == ".zip":
                unzip_dir = stage / (dst.stem + "_unzipped")
                unzip_dir.mkdir(exist_ok=True)
                try:
                    with zipfile.ZipFile(dst) as archive:
                        archive.extractall(unzip_dir)
                    for extracted in unzip_dir.rglob("*"):
                        if extracted.is_file() and is_candidate(extracted):
                            stat = extracted.stat()
                            staged.append(Candidate(str(extracted), extracted.name, f"unzipped:{candidate.source}", stat.st_mtime, stat.st_size))
                except Exception:
                    pass
        candidates = staged
    print(json.dumps([asdict(candidate) for candidate in candidates], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
