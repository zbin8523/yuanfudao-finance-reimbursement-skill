# Email Source Acquisition

## Implemented Local Acquisition

Use `scripts/collect_invoices.py`:

```bash
scripts/collect_invoices.py --days 10 ~/Downloads
scripts/collect_invoices.py --days 10 --include-mail-caches ~/Downloads
```

The script scans only local files and known attachment/cache folders. It does not read passwords, cookies, or mail account databases.

Known local app evidence on Bin's Mac:

- NetEase Mail Master app: `/Applications/MailMaster.app`
- NetEase group container: `~/Library/Group Containers/group.com.netease.macmail`
- WeCom app: `/Applications/企业微信.app`
- WeCom mail/cache hints: `~/Library/Containers/com.tencent.WeWorkMac/Data/ATencent.WXWork.IPC-WeMail`

## Real Inbox Search Workflow

When the user asks “去网易邮箱大师/企业微信邮箱找最近 10 天未报销发票”:

1. Use the logged-in desktop app or real Chrome session; do not inspect credentials or raw cookie stores.
2. Search keywords: `发票`, `电子发票`, `行程单`, `保险`, `报销`, `invoice`.
3. Filter date: last 10 days.
4. Download/export attachments to a staging folder.
5. Run `collect_invoices.py`, `invoice_extract.py`, `plan_reimbursement.py` on the staging folder.
6. Continue to zhenguanyu filling; stop before final submit.

If app UI automation or screen permissions are unavailable, ask the user to export matching attachments to a folder and continue from that folder.

## <sample_date> MailMaster UI Attempt Log

Observed app:

- `/Applications/MailMaster.app`
- Process/window: `MailMaster`, window `网易邮箱大师`
- Accessible search dialog text field description: `输入正文关键词进行搜索`

Attempts:

1. Local cache scan under `~/Library/Group Containers/group.com.netease.macmail` and WeCom mail hints: no recent invoice attachment files beyond already-downloaded files.
2. `Cmd+F` / menu `编辑 → 查找` with keyword `发票`: search dialog exposed `0/0`, no attachment export appeared.
3. Scripted setting of search field for `发票`, `电子发票`, `行程单`, `保险`: UI automation became unstable and was interrupted.

Recommended fallback for MailMaster until a stronger adapter exists:

- Ask user to search/export invoice attachments from MailMaster to `~/Downloads` or a staging folder.
- Then run `scripts/run_reimbursement_pipeline.py --days 10 --dry-run-browser <folder>`.

Do not attempt to read MailMaster account databases or credentials.

## MailMaster SQLite Adapter

A stable non-UI adapter is available:

```bash
scripts/mailmaster_invoice_index.py --days 10 --export-dir /tmp/mailmaster_invoice_export --downloaded-only
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --dry-run-browser
```

Observed MailMaster data root:

`~/Library/Containers/com.netease.macmail/Data/Library/Application Support/data`

Relevant tables:

- `<account>/mail.db: MailMeta`
- `<account>/mail.db: MailAttachment`
- Attachment blobs: `<account>/parts/<LocalPath>`
- View/export copies: `~/Library/Containers/com.netease.macmail/Data/Library/Application Support/view/...`

Safety:

- The adapter opens SQLite in read-only mode.
- It does not read account passwords, cookies, or authentication stores.
- It exports only invoice-like attachment blobs/files discovered from `MailAttachment` metadata.

<sample_date> verification:

- `scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --dry-run-browser`
- Elapsed: `5.17s`
- Exported/recovered from MailMaster: 5 reimbursement PDFs after duplicate filtering
- Invoice total: `<sample_total>`
- Browser dry-run: `will_not_submit: true`

## Natural-Language Source Routing

Default interpretation:

- “去网易邮箱大师找最近发票”: use `mailmaster_invoice_index.py --days 10 --downloaded-only --export-dir <dir>` first.
- “各个邮件箱”: scan all MailMaster account folders under `~/Library/Containers/com.netease.macmail/Data/Library/Application Support/data`, not only inbox names.
- “企业微信邮箱/公司邮箱”: use the user's real Chrome login state to search the web mailbox; do not open a temporary browser profile.
- “还未报销”: first dedupe locally by invoice number; final already-used status may only be visible after upload/select on zhenguanyu, so stop and report any duplicate/used warning.

Recommended query terms:

- `发票`, `电子发票`, `数电票`, `行程单`, `电子客票`, `报销凭证`, `保险`, `酒店`, `携程`, `航旅纵横`, `滴滴`, `餐饮`.
- Time window defaults to last `10` days unless the user specifies another range.
- Attachment suffixes: `.pdf`, `.ofd`, `.zip`, `.xml`, `.jpg`, `.jpeg`, `.png`.

MailMaster verified route:

```bash
scripts/mailmaster_invoice_index.py --days 10 --downloaded-only --export-dir /tmp/mailmaster_invoice_export
scripts/run_reimbursement_pipeline.py --mailmaster --days 10 --out-dir /tmp/reimb_run
```

If the local MailMaster index has records but no attachment blob is downloaded, ask the user to open/download the message attachments in MailMaster, then rerun the same command.
