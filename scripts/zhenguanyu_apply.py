#!/usr/bin/env python3
"""Chrome/AppleScript helpers for zhenguanyu reimbursement pages.

This helper opens/reads/fills the page but never clicks final submit.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path

TARGET_URL = "https://company-reimbursement-domain.example/#/startapply?pageType=startapply&type=165&status=3"


def chrome_js(js: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as js_handle:
        js_handle.write(js)
        js_path = Path(js_handle.name)
    script = f'''tell application "Google Chrome"
  if (count of windows) = 0 then make new window
  activate
  set jsSource to read POSIX file "{js_path}" as «class utf8»
  tell active tab of front window
    return execute javascript jsSource
  end tell
end tell
'''
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        result = subprocess.run(["osascript", str(script_path)], text=True, capture_output=True, timeout=20)
    finally:
        script_path.unlink(missing_ok=True)
        js_path.unlink(missing_ok=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    out = result.stdout.strip()
    return out if out and out != "missing value" else ""


def open_target() -> None:
    script = f'''tell application "Google Chrome"
  if (count of windows) = 0 then make new window
  set matched to false
  repeat with w from 1 to count of windows
    repeat with i from 1 to count of tabs of window w
      set t to tab i of window w
      if (URL of t) contains "company-reimbursement-domain.example" then
        set active tab index of window w to i
        set index of window w to 1
        set matched to true
        exit repeat
      end if
    end repeat
  end repeat
  if matched is false then set URL of active tab of front window to "{TARGET_URL}"
  if matched is true then set URL of active tab of front window to "{TARGET_URL}"
  activate
end tell
'''
    subprocess.run(["osascript", "-e", script], check=True)


def read_state() -> str:
    for _ in range(10):
        state = chrome_js(r"""
JSON.stringify({
  title: document.title,
  href: location.href,
  ready: document.readyState,
  text: (document.body && document.body.innerText || '').slice(0, 5000),
  inputs: [...document.querySelectorAll('input,textarea')].slice(0,80).map((e,i)=>({i, tag:e.tagName, value:e.value||'', placeholder:e.placeholder||'', cls:String(e.className||'')})),
  selects: [...document.querySelectorAll('.ant-select-selection--single')].slice(0,40).map((e,i)=>({i, text:(e.innerText||'').trim(), cls:String(e.className||'')})),
  buttons: [...document.querySelectorAll('button')].slice(0,80).map((e,i)=>({i, text:(e.innerText||'').trim(), cls:String(e.className||'')}))
}, null, 2)
""")
        if state:
            try:
                parsed = json.loads(state)
                if len(parsed.get("text") or "") > 20:
                    return state
            except Exception:
                return state
        time.sleep(1)
    return ""

def load_plan(path: str) -> dict:
    return json.loads(Path(path).expanduser().read_text())


def dry_run(plan: dict) -> str:
    total = sum(float(row.get("amount") or 0) for row in plan.get("rows", []))
    return json.dumps({
        "action": "dry-run",
        "target_url": TARGET_URL,
        "will_not_submit": True,
        "workflow": plan.get("workflow") or "差旅费申请",
        "company": plan.get("company"),
        "payment_method": plan.get("payment_method"),
        "currency": plan.get("currency"),
        "date_range": [plan.get("start_date"), plan.get("end_date")],
        "rows": plan.get("rows", []),
        "row_total": round(total, 2),
        "invoice_total": plan.get("invoice_total"),
        "invoice_count": len(plan.get("invoice_nos", [])),
    }, ensure_ascii=False, indent=2)


def upload_files_to_page(files: list[str]) -> str:
    # Assumes the invoice upload modal is open and the multi-file input is present.
    payload = []
    for raw in files:
        path = Path(raw).expanduser()
        payload.append({
            "name": path.name,
            "type": "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream",
            "b64": base64.b64encode(path.read_bytes()).decode(),
        })
    payload_json = json.dumps(payload, ensure_ascii=False)
    js = r"""
(() => {
  const payload = __PAYLOAD__;
  function b64ToBytes(b64) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }
  const input = [...document.querySelectorAll('input[type=file]')].find(e => e.multiple) || [...document.querySelectorAll('input[type=file]')].at(-1);
  if (!input) return 'NO_FILE_INPUT';
  const dt = new DataTransfer();
  for (const item of payload) dt.items.add(new File([b64ToBytes(item.b64)], item.name, {type:item.type||'application/pdf'}));
  input.files = dt.files;
  input.dispatchEvent(new Event('input', {bubbles:true}));
  input.dispatchEvent(new Event('change', {bubbles:true}));
  return 'DISPATCHED ' + input.files.length;
})()
""".replace("__PAYLOAD__", payload_json)
    return chrome_js(js)



def select_workflow(workflow: str = "差旅费申请") -> str:
    workflow_json = json.dumps(workflow, ensure_ascii=False)
    js = r"""
(function run(workflow){
  const text=document.body.innerText||'';
  const labels=[...document.querySelectorAll('label')].filter(e=>(e.innerText||e.textContent||'').trim()===workflow);
  const target=labels.find(e=>{const r=e.getBoundingClientRect(); return r.width>0&&r.height>0&&r.x>=0&&r.x<window.innerWidth;});
  if(!target && (!text.includes('选择流程') || text.includes('流程名称:'))) return 'ALREADY_IN_FORM';
  if(!target) return 'NO_WORKFLOW '+workflow;
  target.click();
  const next=[...document.querySelectorAll('button')].find(b=>(b.innerText||'').trim()==='下一步');
  if(!next) return 'NO_NEXT';
  next.click();
  return 'SELECTED '+workflow;
})(__WORKFLOW__)
""".replace("__WORKFLOW__", workflow_json)
    result = ""
    for _ in range(8):
        result = chrome_js(js)
        if not result.startswith("NO_WORKFLOW"):
            break
        time.sleep(0.75)
    time.sleep(2)
    return result

def fill_from_plan(plan: dict, upload: bool) -> str:
    # Fast fill requires the correct form page visible. It avoids final submit.
    workflow_result = select_workflow(plan.get("workflow") or "差旅费申请")
    time.sleep(1)
    js = r"""
async function wait(ms){return new Promise(r=>setTimeout(r,ms));}
function visibleSelects(){return [...document.querySelectorAll('.ant-select-selection--single')].filter(e=>{const r=e.getBoundingClientRect(); return r.width>0&&r.height>0&&r.x>=0&&r.x<window.innerWidth&&r.y>250;});}
function setVal(el,val){ const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; const setter=Object.getOwnPropertyDescriptor(proto,'value').set; setter.call(el,String(val)); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.dispatchEvent(new Event('blur',{bubbles:true})); }
async function chooseSelectByY(yMin,yMax,text){ const e=visibleSelects().find(s=>{const r=s.getBoundingClientRect(); return r.y>=yMin&&r.y<=yMax;}); if(!e) return 'NO_SELECT '+text; e.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window})); e.click(); await wait(250); const d=[...document.querySelectorAll('.ant-select-dropdown')].find(x=>getComputedStyle(x).display!=='none'); if(!d) return 'NO_DROPDOWN '+text; const opt=[...d.querySelectorAll('li[role=option],.ant-select-dropdown-menu-item')].find(o=>(o.innerText||o.textContent||'').trim()===text && !String(o.className||'').includes('disabled')); if(!opt) return 'NO_OPTION '+text; opt.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window})); opt.click(); await wait(250); return 'OK '+text;}
function dateTitle(value){ const parts=String(value).split('-').map(Number); return `${parts[0]}年${parts[1]}月${parts[2]}日`; }
async function pickDate(index,title){ const inputs=[...document.querySelectorAll('input.ant-calendar-picker-input')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.y>250;}); const inp=inputs[index]; if(!inp) return 'NO_DATE_INPUT'; inp.click(); await wait(200); const cell=[...document.querySelectorAll('td[title]')].find(td=>td.getAttribute('title')===title); if(!cell) return 'NO_DATE_CELL '+title; cell.click(); await wait(250); return 'OK_DATE '+title;}
async function run(plan){ let out=[]; out.push(await chooseSelectByY(300,370,plan.company)); out.push(await chooseSelectByY(380,440,plan.payment_method)); out.push(await chooseSelectByY(430,500,plan.currency)); if(plan.start_date) out.push(await pickDate(0, dateTitle(plan.start_date))); if(plan.end_date) out.push(await pickDate(1, dateTitle(plan.end_date)));
 const rows=plan.rows||[];
 for(let i=0;i<rows.length;i++){ const row=rows[i]; const y=600+i*143; if(i>0){ const add=[...document.querySelectorAll('button')].find(b=>(b.innerText||'').trim()==='添加'); if(add) add.click(); await wait(300); }
   out.push(await chooseSelectByY(y-20,y+60,row.expense_type));
   const amount=[...document.querySelectorAll('input.ant-input:not(.ant-calendar-picker-input):not(.ant-input-disabled)')].find(e=>{const r=e.getBoundingClientRect(); return r.y>=y-20&&r.y<=y+80&&e.placeholder==='请输入';}); if(amount) setVal(amount,row.amount); else out.push('NO_AMOUNT '+i);
   const ta=[...document.querySelectorAll('textarea.ant-input')].find(e=>{const r=e.getBoundingClientRect(); return r.y>=y+20&&r.y<=y+130;}); if(ta) setVal(ta,row.description||''); else out.push('NO_DESC '+i);
 }
 return out.join('\n');}
run(ARG_PLAN)
""".replace("ARG_PLAN", json.dumps(plan, ensure_ascii=False))
    result = workflow_result + "\n" + chrome_js(js)
    if upload:
        files: list[str] = []
        for row in plan.get("rows", []):
            files.extend(row.get("files") or [])
        result += "\nUPLOAD_HELPER_AVAILABLE files=" + str(len(files))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("open")
    sub.add_parser("read")
    dry = sub.add_parser("dry-run")
    dry.add_argument("plan_json")
    fill = sub.add_parser("fill")
    fill.add_argument("plan_json")
    fill.add_argument("--upload", action="store_true", help="Only prepares upload helper; never submits")
    upload = sub.add_parser("upload-modal-files")
    upload.add_argument("files", nargs="+")
    args = parser.parse_args()
    if args.cmd == "open":
        open_target(); print("opened")
    elif args.cmd == "read":
        state = read_state()
        if not state:
            raise RuntimeError("Chrome returned empty page state. Ensure the zhenguanyu tab is active, page loaded, and Apple Events JavaScript is enabled.")
        print(state)
    elif args.cmd == "dry-run":
        print(dry_run(load_plan(args.plan_json)))
    elif args.cmd == "fill":
        print(fill_from_plan(load_plan(args.plan_json), args.upload))
    elif args.cmd == "upload-modal-files":
        print(upload_files_to_page(args.files))
        time.sleep(2)
        print((chrome_js("(document.body.innerText||'').slice(-1500)") or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
