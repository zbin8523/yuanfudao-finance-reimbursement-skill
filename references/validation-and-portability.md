# Validation and Portability

## Current Validation Evidence

Tested on the 2026-06 travel reimbursement sample with five PDFs:

- Hotel invoice: `<invoice_no_hotel>`, `<sample_hotel_amount>`, `住宿费(普票)`
- Flight itinerary: `<invoice_no_flight_1>`, `<sample_flight_amount_1>`, `火车/机票费`
- Flight itinerary: `<invoice_no_flight_2>`, `<sample_flight_amount_2>`, `火车/机票费`
- Flight insurance invoice: `<invoice_no_insurance_1>`, `<sample_insurance_amount>`, `火车/机票费`
- Flight insurance invoice: `<invoice_no_insurance_2>`, `<sample_insurance_amount>`, `火车/机票费`

Generated plan:

- Company: `DEFAULT_COMPANY`
- Payment method: `网银转账（工资卡）`
- Currency: `CNY`
- Dates: `<sample_start_date>` to `<sample_end_date>`
- Rows: `火车/机票费 <sample_travel_amount>`, `住宿费(普票) <sample_hotel_amount>`
- Invoice total: `<sample_total>`

## Portability

The core assets are portable to OpenClaw, Hermes, Claude App, or other agents:

- `SKILL.md`: policy and workflow instructions.
- `scripts/invoice_extract.py`: local invoice OCR/classification.
- `scripts/plan_reimbursement.py`: deterministic reimbursement row planning.
- `scripts/zhenguanyu_apply.py`: Chrome/AppleScript page helper. Replace this adapter on non-macOS or non-Chrome runtimes.

Keep the final submit guard in every runtime.

## Known Limits

- macOS OCR uses QuickLook + Vision; non-macOS runtimes need a PDF/OCR replacement.
- Email acquisition is workflow-defined but not fully implemented as a universal adapter; use logged-in browser/app automation or exported attachments.
- The form-filling helper performs the travel form fast fill from a JSON plan and stops before final submit.
- Invoice upload/association can be blocked by the finance system duplicate-invoice guard. If the page says an invoice has already been collected, stop and report instead of forcing reuse.
- The “last 10 days mailbox search” validation requires user mailbox/app access and should be run only in the user’s authenticated environment.

## <sample_date> Pipeline Validation

Command:

```bash
scripts/run_reimbursement_pipeline.py --days 10 --dry-run-browser ~/Downloads
```

Result:

- Wall time: `8s`
- Internal elapsed: `7.84s`
- Candidate files: `5`
- Invoices recognized: `5`
- Invoice total: `<sample_total>`
- Browser dry-run: `will_not_submit: true`
- Generated rows: `住宿费(普票) <sample_hotel_amount>`, `火车/机票费 <sample_travel_amount>`

Assertion used:

```bash
jq -e '.invoice_count == 5 and .invoice_total == <sample_total> and (.elapsed_seconds < 300) and (.browser_dry_run.will_not_submit == true) and (.browser_dry_run.row_total == <sample_total>)' /tmp/finance_pipeline_final.json
```

Mail-cache smoke test:

```bash
scripts/collect_invoices.py --days 10 --include-mail-caches ~/Downloads | jq 'length'
```

Result: `5` local invoice-like files found in the current environment.

## <sample_date> Final Goal-Run Evidence

Command:

```bash
scripts/run_reimbursement_pipeline.py --days 10 --dry-run-browser ~/Downloads
```

Result:

- Elapsed: `5.25s`
- Candidate files: `5`
- Recognized invoices: `5`
- Invoice total: `<sample_total>`
- Browser dry-run: `will_not_submit: true`
- Validation assertion: passed
- Skill validation: `Skill is valid!`

Superseded by later validation:

- The first pass only validated exported/local attachments.
- The later MailMaster integrated validation below proves read-only MailMaster index discovery and attachment blob export for already-cached/downloaded invoice attachments.

## <sample_date> MailMaster Integrated Validation

Command:

```bash
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --dry-run-browser
```

Result:

- Elapsed: `5.17s`
- Candidate files after filtering/deduplication: `5`
- Recognized invoices: `5`
- Invoice total: `<sample_total>`
- Browser dry-run: `will_not_submit: true`
- Validation assertion: passed

This proves the MailMaster-source path for already-cached/downloaded attachment blobs:
MailMaster SQLite index → attachment blob recovery/export → ZIP expansion → invoice filtering → OCR → reimbursement plan → browser dry-run.

## <sample_date> Live Form Fill Validation

Commands:

```bash
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --out-dir /tmp/reimb_run
scripts/zhenguanyu_apply.py open
scripts/zhenguanyu_apply.py fill /tmp/reimb_run/plan.json
scripts/zhenguanyu_apply.py read
```

Result:

- MailMaster elapsed: `5.49s`
- Candidate files: `5`
- Recognized invoices: `5`
- Invoice total: `<sample_total>`
- Form workflow selected: `差旅费申请`
- Company/payment/currency filled: `DEFAULT_COMPANY`, `网银转账（工资卡）`, `CNY`
- Dates filled: `<sample_start_date>` to `<sample_end_date>`
- Expense rows filled: `住宿费(普票) <sample_hotel_amount>`, `火车/机票费 <sample_travel_amount>`
- Page total after fill: `<sample_total>`
- Final submit guard: `提 交` button remained visible and was not clicked.

Invoice association note:

- Upload dispatch succeeded for `5` files.
- Finance system returned duplicate-collection warnings for already collected invoice numbers, so the automation stopped without forcing invoice association.
- User should manually review invoice association and final submit when duplicate collection appears.

## <sample_date> Workflow Routing Validation

Command:

```bash
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --workflow travel --dry-run-browser
scripts/plan_reimbursement.py /tmp/sample_daily_invoices.json --workflow daily
scripts/plan_reimbursement.py /tmp/sample_daily_invoices.json --workflow payment
```

Result:

- Travel route: `差旅费申请`, `5` invoices, total `<sample_total>`, browser dry-run `will_not_submit: true`.
- Daily route: `日常报销申请`, sample restaurant/entertainment invoice mapped to `招待餐费`.
- Payment route: `付款申请`, workflow selection is represented in `plan.json`; payee/payment evidence still needs user data when absent.

## Speed Strategy and Fallback Ladder

Target: finish source discovery → invoice extraction → plan generation → browser fill in under `5` minutes for typical small batches.

Priority order:

1. Local index/file scan: MailMaster SQLite read-only index or provided folder paths.
2. Local extraction: reuse staged files and invoice JSON; avoid repeated OCR when invoice numbers match.
3. Deterministic planning: group by workflow and expense category before opening the browser.
4. Browser DOM adapter: open real Chrome, select workflow, batch-fill fields by selectors and Ant Design events.
5. Upload/select invoices: use bulk `DataTransfer` dispatch, not chunked per-12KB JavaScript calls.
6. Visual/manual fallback: only when selectors fail or the website changes; stop after clear evidence and report the exact missing field.

Stop conditions:

- Success: form filled, invoice totals match or duplicate warning is clearly reported, final `提 交` not clicked.
- Safety stop: duplicate/used invoice warning, missing required payee/payment info, or invoice total mismatch that cannot be resolved automatically.
- Failure stop: 10 failed attempts or repeated selector/page-state failure; preserve logs and screenshots/page text if available.

Measured improvements:

- MailMaster integrated path: about `5.17–5.49s` for the verified five-invoice sample.
- Bulk upload dispatch: `DISPATCHED 5` in one browser call; old per-chunk upload helper could hang for minutes.
- Live fill: DOM path fills company, payment, currency, dates, two rows, descriptions, and total without visual clicking.

## Cross-Runtime Porting Contract

To migrate to OpenClaw, Hermes, Claude App, or another agent runtime, keep these layers separate:

- Source adapters: implement `folder`, `uploaded_attachments`, `mailmaster`, `webmail/corporate_mail` and output local invoice-like files.
- Extraction adapter: output the same JSON fields as `invoice_extract.py`: `path`, `filename`, `invoice_no`, `amount`, `category_hint`, `text`.
- Planning adapter: output `plan.json` with `workflow`, `company`, `payment_method`, `currency`, `start_date`, `end_date`, `rows`, `invoice_total`, `invoice_nos`.
- Browser adapter: implement `open`, `read`, `dry-run`, `fill`, and optional `upload-modal-files`; never implement final submit by default.
- Safety policy: announce submit guard at startup and require manual final review/submit.

Runtime-specific replacements:

- macOS/Codex: use `zhenguanyu_apply.py` with real Google Chrome Apple Events JavaScript.
- OpenClaw/Hermes: replace browser adapter with their real-browser/session controller, keeping `plan.json` unchanged.
- Claude App: use browser automation or ask user to open the authenticated Chrome tab; do not use unauthenticated temporary browsers for company systems.
