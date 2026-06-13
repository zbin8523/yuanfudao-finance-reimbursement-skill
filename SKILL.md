---
name: yuanfudao-finance-reimbursement
description: Automate company finance reimbursement workflows for company-reimbursement-domain.example, including travel reimbursement, daily reimbursement, entertainment/meal expenses, invoice discovery from folders, uploaded attachments, email clients such as NetEase Mail Master or corporate email, OCR/classification of invoice PDFs, browser form filling, invoice upload/association, and speed optimization. Use when the user asks to fill, prepare, validate, submit-for-review, automate, or build a reusable workflow for 财务报销, 差旅费申请, 日常报销, 招待费, 发票, 邮箱发票, 网易邮箱大师, 企业微信邮箱, or company reimbursement portal报销.
---

# Yuanfudao Finance Reimbursement

Use this skill to prepare company reimbursements in company reimbursement portal / `company-reimbursement-domain.example` from local files, uploaded attachments, email invoices, or natural language instructions.

## Non-Negotiable Safety

- State at startup: “我会填写并停在提交前，最终提交请你人工复核后点击。”
- Do not click final `提 交`, `通过`, `发送`, or equivalent side-effect buttons unless the user gives explicit action-time confirmation for that exact submission.
- Uploading invoice files to the reimbursement site is allowed when the user asked to prepare the reimbursement.
- Prefer the user’s already logged-in real Chrome session for `https://www.zhenguanyu.com/#/startapply`; do not use temporary browser profiles for logged-in company systems. If the page is not logged in, stop and ask the user to log in with their own account, then continue.

## Fast Path

1. Resolve invoice sources:
   - Folder or uploaded files: enumerate PDFs/images by mtime and filename.
   - Natural language email request: use the relevant mail client/search route, export/download invoice attachments, then continue from local files.
   - If email/browser automation is unavailable, ask for one blocking permission or ask the user to export the attachments to a folder.
2. Run `scripts/collect_invoices.py` for folders/downloads/mail attachment caches; use `references/email-sources.md` for real inbox search.
3. Run `scripts/invoice_extract.py` on candidate files to create structured JSON.
4. Run `scripts/plan_reimbursement.py` to produce a deterministic reimbursement plan.
5. Group invoices by reimbursement type:
   - Travel: flight/rail tickets → `火车/机票费`; hotel ordinary invoice → `住宿费(普票)`; taxi/local transport → `交通费`.
   - Daily reimbursement: meals/entertainment/team costs → `日常报销` appropriate expense type; keep invoice and payment screenshots separated.
6. Open `https://www.zhenguanyu.com/#/startapply` in the user's already logged-in real Chrome session if no target tab exists.
7. Use `scripts/zhenguanyu_apply.py dry-run <plan.json>` to verify totals before touching the page.
8. Use `scripts/zhenguanyu_apply.py fill <plan.json>` only after stating the final-submit guard.
9. Upload invoices through the form’s invoice area, select the uploaded invoices, verify invoice total equals application total.
10. Stop before final submit and report the verification checklist.

## Source Routing

Interpret the user's source instruction before running extraction:

| User says | Primary route | Fallback |
| --- | --- | --- |
| “这个文件夹/这些附件/上传的文件” | Run `run_reimbursement_pipeline.py <paths>` | Ask for the folder/file path once |
| “网易邮箱大师/邮箱大师/收件箱最近发票” | Run `run_reimbursement_pipeline.py --mailmaster --days <N>` | Use logged-in MailMaster/Chrome UI export, then run folder route |
| “企业微信邮箱/公司邮箱/webmail” | Use real logged-in Chrome to search/download attachments | Ask user to export attachments to a folder |
| “最近还未报销的发票” | Search last `10` days by default and dedupe invoice numbers | If duplicate/used status is only visible on finance site, upload/select and stop on duplicate warning |
| “日常招待/餐饮/团队活动” | Use workflow `daily` | Keep payment screenshots in other attachments |
| “付款申请/对公付款” | Use workflow `payment` | Ask for payee/payment evidence if invoice alone is insufficient |

Never inspect passwords, cookies, token stores, or credential databases. Local MailMaster SQLite message indexes and attachment blobs are allowed only as read-only invoice discovery sources.

## Workflow Routing

Set `--workflow` when the user names the reimbursement type:

- Travel: `--workflow travel` → `差旅费申请`.
- Daily reimbursement: `--workflow daily` → `日常报销申请`.
- Entertainment/meal/team expenses: `--workflow daily`, map invoice category to the closest form expense type.
- Payment request: `--workflow payment` → `付款申请`; invoices alone may not be enough, so require payee, bank/payment method, contract/order/supporting files if missing.

If the user does not name a workflow, infer it from invoices:

- Flight/rail/hotel/local transport → travel.
- Meal/restaurant/entertainment/team activity/general office cost → daily.
- Vendor payment, contract, purchase order, prepaid service → payment.

## Execution Commands

Fast dry run from MailMaster:

```bash
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --workflow travel --dry-run-browser
```

Fast live fill, still stopping before submit:

```bash
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --workflow travel --out-dir /tmp/reimb_run
scripts/zhenguanyu_apply.py open
scripts/zhenguanyu_apply.py fill /tmp/reimb_run/plan.json
scripts/zhenguanyu_apply.py read
```

For local files/folders:

```bash
scripts/run_reimbursement_pipeline.py --workflow daily /path/to/folder-or-files
```


## Reimbursement Portal Entry

- Primary entry URL: `https://www.zhenguanyu.com/#/startapply`.
- Use the user's existing logged-in Google Chrome profile first.
- If no matching tab exists, open the primary entry URL in real Chrome, not an isolated/in-app/temporary browser.
- After opening, check page text/state. If it appears to be a login page or the reimbursement workflow options are unavailable, stop and tell the user to log in, then resume from the same tab.
- Workflow-specific routes may add query parameters such as `pageType=startapply&type=165&status=3`, but the base entry above is the canonical starting point.

## Browser Requirements

For Chrome automation on macOS:

- Chrome menu must enable `显示` → `开发者` → `允许 Apple 事件中的 JavaScript`.
- If AppleScript reports JavaScript is disabled, ask the user to enable it; do not silently switch to an unauthenticated browser.
- If Chrome has no open reimbursement tab, open the target URL in the user’s real Chrome profile.

## Email Invoice Acquisition

Use the least invasive source route:

- For NetEase Mail Master / desktop mail: first try app search/export by visible UI or local download folder evidence; do not inspect passwords, cookies, or private stores.
- For webmail/corporate mail: use logged-in Chrome if the user asked to search that mailbox.
- Query examples: `发票 OR 电子发票 OR 行程单 OR 保险`, received in the last 10 days, with attachments `.pdf`, `.ofd`, `.jpg`, `.png`.
- Save candidate attachments to a dated staging folder, then run OCR/classification.

## Reimbursement Form Mapping

Travel reimbursement default:

- Company: `DEFAULT_COMPANY` unless user says otherwise.
- Payment method: `网银转账（工资卡）`.
- Currency: `CNY`.
- Dates: infer from ticket/hotel dates; otherwise ask one concise question.
- Expense rows:
  - `火车/机票费`: flight/rail ticket amount plus directly associated flight accident insurance when company practice allows it.
  - `住宿费(普票)`: hotel ordinary invoice tax-inclusive amount.
  - `交通费`: taxi/local transport.
- Description: include date range, route/city, and invoice/order identifiers.

Daily reimbursement default:

- Select the relevant finance/daily reimbursement workflow.
- Keep invoice attachments in `发票`; put payment screenshots or receipts in `其他附件`.
- Do not mix unrelated cost categories in one expense row when the form has separate categories.

## Speed Targets

- Use DOM selectors and form-state events before visual clicking.
- Use OCR/cache JSON before rereading PDF images.
- Use browser script helpers for repeated select/input/upload operations.
- Fall back to visual/DOM step-by-step only when the fast path fails.
- Target: after invoices are local and Chrome is prepared, fill + upload + verify within 5 minutes.


## One-Command Dry Run

Use this before touching a live form:

```bash
scripts/run_reimbursement_pipeline.py --days 10 --dry-run-browser ~/Downloads
```

Expected successful output includes `will_not_submit: true`, matching `row_total` and `invoice_total`, and elapsed time under 300 seconds.

## Validation Checklist

Before handing back:

- Company, payment method, currency are filled.
- Dates match invoice/trip evidence.
- Expense row totals equal invoice selected total.
- All required invoices are associated in `发票`.
- Non-invoice attachments are only in `其他附件`.
- Submit button is visible and untouched.
- Report any missing attachment, ambiguous category, or permission blocker.
