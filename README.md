# Finance Reimbursement Automation Skill

A Codex Skill for preparing company reimbursement forms from invoice attachments, local folders, NetEase Mail Master attachments, or natural-language source descriptions.

## What It Does

- Finds invoice-like files from folders, uploads, MailMaster local indexes, or browser-based webmail workflows.
- Extracts invoice numbers, amounts, dates, and expense categories from PDF/image/OFD-adjacent evidence.
- Builds a deterministic reimbursement `plan.json` for travel, daily reimbursement, entertainment/meals, or payment workflows.
- Opens the authenticated company reimbursement portal in the user's real Chrome session.
- Fills the form and stops before final submission.

## Safety

The final submit action is intentionally not automated. The user must review and click submit manually.

## Typical Commands

```bash
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --workflow travel --dry-run-browser
scripts/run_reimbursement_pipeline.py --workflow daily ~/Downloads
scripts/zhenguanyu_apply.py open
scripts/zhenguanyu_apply.py fill /tmp/reimb_run/plan.json
```

## Portability

The Skill separates source discovery, invoice extraction, planning, and browser filling so the browser adapter can be replaced for OpenClaw, Hermes, Claude App, or other agent runtimes.

## Notes

This export is sanitized: company domain, sample invoice numbers, amounts, account names, and personal identifiers are replaced with placeholders. Configure `TARGET_URL`, company defaults, and workflow mappings for your environment before reuse.
