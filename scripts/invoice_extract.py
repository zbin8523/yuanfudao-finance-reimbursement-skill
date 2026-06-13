#!/usr/bin/env python3
"""Extract and classify invoice-like files for reimbursement automation.

This script is intentionally dependency-light. On macOS it can OCR images/PDF previews via
Vision when available; otherwise it falls back to filename heuristics and file metadata.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path


AMOUNT_RE = re.compile(r"(?:¥|CNY\s*)?([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)")
INVOICE_RE = re.compile(r"\b(\d{20})\b")


@dataclass
class InvoiceCandidate:
    path: str
    filename: str
    invoice_no: str | None
    amount: float | None
    category_hint: str
    text: str


def classify(name: str, text: str) -> str:
    combined = f"{name}\n{text}"
    if any(key in combined for key in ["行程单", "航空运输", "机票", "航班"]):
        return "火车/机票费"
    if any(key in combined for key in ["保险", "意外险"]):
        return "火车/机票费"
    if any(key in combined for key in ["酒店", "住宿", "代订住宿"]):
        return "住宿费(普票)"
    if any(key in combined for key in ["出租", "网约车", "交通"]):
        return "交通费"
    if any(key in combined for key in ["餐饮", "招待", "饭店", "餐费"]):
        return "日常报销/招待餐费"
    return "待确认"


def ocr_with_swift(path: Path) -> str:
    swift = Path("/usr/bin/swift")
    if not swift.exists():
        return ""
    script = r'''
import Foundation
import Vision
import AppKit
let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path), let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { exit(0) }
let request = VNRecognizeTextRequest { request, error in
    let observations = request.results as? [VNRecognizedTextObservation] ?? []
    let lines = observations.compactMap { $0.topCandidates(1).first?.string }
    print(lines.joined(separator: "\n"))
}
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "en-US"]
try? VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
'''
    with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as handle:
        handle.write(script)
        script_path = handle.name
    try:
        result = subprocess.run([str(swift), script_path, str(path)], text=True, capture_output=True, timeout=45)
        return result.stdout.strip()
    except Exception:
        return ""
    finally:
        Path(script_path).unlink(missing_ok=True)


def make_pdf_preview(path: Path) -> Path | None:
    with tempfile.TemporaryDirectory(prefix="invoice_preview_") as tmp:
        tmp_path = Path(tmp)
        try:
            subprocess.run(["/usr/bin/qlmanage", "-t", "-s", "1800", "-o", str(tmp_path), str(path)],
                           text=True, capture_output=True, timeout=30)
        except Exception:
            return None
        previews = list(tmp_path.glob("*.png"))
        if not previews:
            return None
        target = Path(tempfile.gettempdir()) / f"invoice_preview_{path.stem}_{int(time.time()*1000)}.png"
        previews[0].replace(target)
        return target


def extract_text(path: Path) -> str:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return ocr_with_swift(path)
    preview = path.with_suffix(path.suffix + ".png")
    if preview.exists():
        return ocr_with_swift(preview)
    if path.suffix.lower() == ".pdf":
        generated = make_pdf_preview(path)
        if generated:
            try:
                return ocr_with_swift(generated)
            finally:
                generated.unlink(missing_ok=True)
    return ""


def infer_amount(name: str, text: str) -> float | None:
    combined = f"{name}\n{text}"
    # The strongest signal in Chinese e-invoices is usually the value after
    # “（小写）”. Prefer it to avoid policy numbers such as PI157... being read
    # as amounts.
    small_matches = re.findall(r"(?:小写|小寫)\D{0,8}([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)", combined)
    for match in reversed(small_matches):
        try:
            value = float(match.replace(",", ""))
        except ValueError:
            continue
        if value > 0:
            return value
    patterns = [
        r"(?:价税合计|总额)\D{0,12}([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)",
        r"合计\D{0,30}([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)",
        r"CNY\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)",
        r"¥\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)",
    ]
    explicit_values: list[float] = []
    for pattern in patterns:
        matches = re.findall(pattern, combined)
        for match in matches:
            try:
                value = float(match.replace(",", ""))
            except ValueError:
                continue
            if value > 0:
                explicit_values.append(value)
    if explicit_values:
        return max(explicit_values)
    values = []
    for match in re.findall(r"(?<!\d)([0-9]{1,5}(?:\.[0-9]{2}))(?!\d)", combined):
        try:
            value = float(match)
        except ValueError:
            continue
        if 1 <= value <= 100000:
            values.append(value)
    return max(values) if values else None


def analyze(path: Path) -> InvoiceCandidate:
    text = extract_text(path)
    invoice_no = None
    match = INVOICE_RE.search(text)
    if match:
        invoice_no = match.group(1)
    return InvoiceCandidate(
        path=str(path),
        filename=path.name,
        invoice_no=invoice_no,
        amount=infer_amount(path.name, text),
        category_hint=classify(path.name, text),
        text=text[:4000],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Invoice files or directories")
    parser.add_argument("--days", type=int, default=None, help="Only include files modified in the last N days")
    args = parser.parse_args()
    files: list[Path] = []
    exts = {".pdf", ".png", ".jpg", ".jpeg", ".ofd"}
    cutoff = None
    if args.days:
        import time
        cutoff = time.time() - args.days * 86400
    for raw in args.paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            candidates = [p for p in path.iterdir() if p.suffix.lower() in exts]
        else:
            candidates = [path]
        for candidate in candidates:
            if cutoff and candidate.stat().st_mtime < cutoff:
                continue
            files.append(candidate)
    print(json.dumps([asdict(analyze(path)) for path in files], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
