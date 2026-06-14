# Yuanfudao Finance Reimbursement Skill

A Codex Skill for preparing company reimbursement forms from invoice attachments, local folders, NetEase Mail Master attachments, or natural-language source descriptions.

## What It Does

- Finds invoice-like files from folders, uploads, MailMaster local indexes, or browser-based webmail workflows.
- Extracts invoice numbers, amounts, dates, and expense categories from PDF/image/OFD-adjacent evidence.
- Builds a deterministic reimbursement `plan.json` for travel, daily reimbursement, entertainment/meals, or payment workflows.
- Opens the authenticated company reimbursement portal in the user's real Chrome session.
- Fills the form and stops before final submission.

## Portal

- Portal entry: `https://www.zhenguanyu.com/#/startapply`.
- Use the user's existing logged-in Chrome profile first. If not logged in, ask the user to log in and resume; do not use a temporary browser.

## Safety

The final submit action is intentionally not automated. The user must review and click submit manually.

## Typical Commands

```bash
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --workflow travel --dry-run-browser
scripts/run_reimbursement_pipeline.py --workflow daily ~/Downloads
scripts/zhenguanyu_apply.py open
scripts/zhenguanyu_apply.py fill /tmp/reimb_run/plan.json
```


## Batch Mode

Prepare multiple reimbursement drafts from a CSV or JSON batch file. Each row is filled in a separate real Chrome tab and stops before final submit.

Example `batch.csv`:

```csv
supplier,business_option,workflow,paths,description
Vendor A,Marketing,daily,/path/to/vendor-a-invoices,June campaign expenses
Vendor B,Procurement,payment,/path/to/vendor-b-invoices; /path/to/contract.pdf,Service payment
```

Commands:

```bash
scripts/batch_reimbursement.py batch.csv --out-dir /tmp/reimb_batch
scripts/batch_reimbursement.py batch.csv --fill --concurrency 3 --out-dir /tmp/reimb_batch
```

Concurrency is capped at `5`; final submit is always manual.

## Portability

The Skill separates source discovery, invoice extraction, planning, and browser filling so the browser adapter can be replaced for OpenClaw, Hermes, Claude App, or other agent runtimes.

## Notes

This export is sanitized: company domain, sample invoice numbers, amounts, account names, and personal identifiers are replaced with placeholders. Configure `TARGET_URL`, company defaults, and workflow mappings for your environment before reuse.
