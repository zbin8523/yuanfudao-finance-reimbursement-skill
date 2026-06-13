# Zhenguanyu Reimbursement Notes

Observed travel workflow URL: `https://company-reimbursement-domain.example/#/startapply?pageType=startapply&type=165&status=3`.

Known fields:

- `公司名称`: `DEFAULT_COMPANY`
- `付款方式`: `网银转账（工资卡）`
- `币种`: `CNY`
- `出差开始日期` / `出差结束日期`: use date picker; direct value assignment may be cleared by validation.
- `费用类型`: travel observed options include `火车/机票费`, `住宿费(普票)`, `交通费`, `住宿费(专用发票不含税)`, `住宿费(专用发票进项税)`.
- `发票`: upload/select invoice PDFs here.
- `其他附件`: payment screenshots and non-invoice evidence only.

Fast-fill implementation notes:

- Use visible labels to select the workflow; hidden `流程名称` text can cause false positives.
- When injecting JavaScript into Chrome via AppleScript, write JS to a UTF-8 temp file and read it as `«class utf8»` to avoid Chinese mojibake.
- Ant Design date picker cell titles use non-padded Chinese dates such as `2026年6月11日`, not `2026年06月11日`.
- Avoid repeated fill runs on the same page unless extra empty rows are cleaned up first.
- Never click final `提 交`; stop with the page ready for manual review.

Recent successful example:

- Travel dates: `<sample_start_date>` to `<sample_end_date>`
- Row 1: `火车/机票费`, `<sample_travel_amount>`, description `<sample trip description>`
- Row 2: `住宿费(普票)`, `<sample_hotel_amount>`, description `<sample hotel description>`
- Invoice total: `<sample_total>`; tax total `166.66`

<sample_date> live validation result:

- The form accepted company, payment method, currency, dates, two expense rows, descriptions, and total `<sample_total>`.
- Invoice upload dispatched five files, but the site reported duplicate collection for already采集 invoice numbers; do not bypass this guard.
