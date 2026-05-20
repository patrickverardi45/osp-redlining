"""PE.1 orchestrator — per-page parser probe with hard subprocess timeout.

Iterates every PDF in PDF_DIR, asks the worker for a page count, then
spawns one subprocess per page with a hard wallclock budget. On expiry,
TerminateProcess (Windows) / SIGKILL (POSIX) reclaims the worker;
orchestrator records 'timeout' and moves to the next page.

Outputs two artifacts in scripts/:
- pe1-page-probe-result.json   machine-readable per-page records
- pe1-page-probe-result.md     human-readable summary + pathological-page list

Scope: scripts-only. No backend imports. No production touch. No env flag
changes. No Render. Read-only against the configured PDF_DIR.

Run
---
    venv\\Scripts\\python.exe scripts\\pe1_page_probe.py

Optional env overrides:
    PE1_PDF_DIR         alternate PDF directory (default: Brenham wiki path)
    PE1_PAGE_TIMEOUT    seconds budget per page (default: 30)
    PE1_COUNT_TIMEOUT   seconds budget for page-count call (default: 60)
    PE1_MAX_PDFS        process only first N PDFs (default: all)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER = REPO_ROOT / "scripts" / "pe1_page_probe_worker.py"

PDF_DIR = Path(os.environ.get(
    "PE1_PDF_DIR",
    r"C:\Nova\knowledge\TrueLine-Wiki\raw\trueline\engineering-plans\brenham",
))
PAGE_TIMEOUT_SEC = int(os.environ.get("PE1_PAGE_TIMEOUT", "30"))
COUNT_TIMEOUT_SEC = int(os.environ.get("PE1_COUNT_TIMEOUT", "60"))
MAX_PDFS = int(os.environ.get("PE1_MAX_PDFS", "0"))  # 0 = no limit

OUTPUT_JSON = REPO_ROOT / "scripts" / "pe1-page-probe-result.json"
OUTPUT_MD = REPO_ROOT / "scripts" / "pe1-page-probe-result.md"


def _run_worker(args: List[str], timeout_sec: int) -> Tuple[str, Optional[Dict[str, Any]], str, int]:
    """Spawn worker subprocess. Returns (status, payload, stderr, wallclock_ms).

    status is one of: 'ok', 'err', 'timeout', 'unparseable'.
    """
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(WORKER)] + args,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return ("timeout", None, "", elapsed_ms)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    last_line = stdout.splitlines()[-1] if stdout else ""
    try:
        payload = json.loads(last_line) if last_line else None
    except json.JSONDecodeError:
        return ("unparseable", None, stderr, elapsed_ms)

    if proc.returncode == 0 and payload and payload.get("ok"):
        return ("ok", payload, stderr, elapsed_ms)
    return ("err", payload, stderr, elapsed_ms)


def _discover_pdfs() -> List[Path]:
    if not PDF_DIR.is_dir():
        return []
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if MAX_PDFS > 0:
        pdfs = pdfs[:MAX_PDFS]
    return pdfs


def _probe_one_pdf(pdf_index: int, pdf_path: Path) -> Dict[str, Any]:
    size_kb = pdf_path.stat().st_size // 1024
    print(f"=== PDF_{pdf_index}: {pdf_path.name} ({size_kb} KB) ===", flush=True)

    count_status, count_payload, count_stderr, count_ms = _run_worker(
        ["count", str(pdf_path)], COUNT_TIMEOUT_SEC,
    )

    record: Dict[str, Any] = {
        "index": pdf_index,
        "path": pdf_path.name,
        "size_kb": size_kb,
        "count_status": count_status,
        "count_payload": count_payload,
        "count_stderr": count_stderr[:500] if count_stderr else "",
        "count_elapsed_ms": count_ms,
        "pages": [],
    }

    if count_status != "ok" or not count_payload or not isinstance(count_payload.get("page_count"), int):
        print(f"  count failed: status={count_status} payload={count_payload} ({count_ms} ms)", flush=True)
        return record

    page_count = count_payload["page_count"]
    print(f"  page_count={page_count} ({count_ms} ms)", flush=True)

    for page_index in range(page_count):
        p_status, p_payload, p_stderr, p_ms = _run_worker(
            ["extract", str(pdf_path), str(page_index)],
            PAGE_TIMEOUT_SEC,
        )
        page_record = {
            "page_index": page_index,
            "status": p_status,
            "payload": p_payload,
            "stderr": p_stderr[:500] if p_stderr else "",
            "elapsed_ms": p_ms,
        }
        record["pages"].append(page_record)

        if p_status == "ok" and p_payload and p_payload.get("ok"):
            text_len = p_payload.get("text_len", 0)
            worker_ms = p_payload.get("elapsed_ms", 0)
            peak_kb = p_payload.get("peak_kb", 0)
            print(
                f"  page {page_index:>3}  OK       {text_len:>6} chars  "
                f"worker={worker_ms:>5} ms  peak={peak_kb:>7} KB  total={p_ms:>5} ms",
                flush=True,
            )
        elif p_status == "timeout":
            print(f"  page {page_index:>3}  TIMEOUT  after {p_ms} ms (budget={PAGE_TIMEOUT_SEC}s)", flush=True)
        elif p_status == "err":
            err = (p_payload or {}).get("error", "(no payload)")
            print(f"  page {page_index:>3}  ERR      {err[:80]}", flush=True)
        else:
            print(f"  page {page_index:>3}  {p_status:<8} ({p_ms} ms)", flush=True)

    return record


def _classify_page(page: Dict[str, Any]) -> str:
    s = page["status"]
    if s == "ok":
        return "ok"
    if s == "timeout":
        return "timeout"
    return "error"


def _write_markdown(results: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# PE.1 — Per-Page Parser Probe Results")
    lines.append("")
    lines.append(f"**Run:** {results['run_at']}")
    lines.append(f"**Python:** {sys.version.splitlines()[0]}")
    lines.append(f"**PDF source:** `{results['pdf_dir']}`")
    lines.append(f"**Worker:** `{WORKER.name}`")
    lines.append(f"**Page timeout budget:** {results['page_timeout_sec']} s")
    lines.append(f"**Count timeout budget:** {results['count_timeout_sec']} s")
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")

    total_pages = 0
    ok_pages = 0
    timeout_pages = 0
    err_pages = 0
    pathological: List[Tuple[str, int, str, int]] = []  # (pdf, page, classification, wallclock_ms)

    for pdf in results["pdfs"]:
        for page in pdf["pages"]:
            total_pages += 1
            cls = _classify_page(page)
            if cls == "ok":
                ok_pages += 1
            elif cls == "timeout":
                timeout_pages += 1
                pathological.append((pdf["path"], page["page_index"], "timeout", page["elapsed_ms"]))
            else:
                err_pages += 1
                pathological.append((pdf["path"], page["page_index"], "error", page["elapsed_ms"]))

    lines.append(f"- PDFs processed: **{len(results['pdfs'])}**")
    lines.append(f"- Pages attempted: **{total_pages}**")
    lines.append(f"- Pages OK: **{ok_pages}**")
    lines.append(f"- Pages TIMEOUT: **{timeout_pages}**")
    lines.append(f"- Pages ERROR: **{err_pages}**")
    if total_pages > 0:
        ok_pct = (ok_pages * 100) // total_pages
        lines.append(f"- OK rate: **{ok_pct}%**")
    lines.append("")

    if pathological:
        lines.append("## Pathological pages")
        lines.append("")
        lines.append("| PDF | Page | Class | Wallclock (ms) |")
        lines.append("|---|---:|---|---:|")
        for path, page_index, cls, ms in pathological:
            lines.append(f"| `{path}` | {page_index} | {cls} | {ms} |")
        lines.append("")
    else:
        lines.append("## Pathological pages")
        lines.append("")
        lines.append("_(none — every attempted page returned OK)_")
        lines.append("")

    lines.append("## Per-PDF detail")
    lines.append("")
    for pdf in results["pdfs"]:
        lines.append(f"### PDF_{pdf['index']}: `{pdf['path']}`  ({pdf['size_kb']} KB)")
        lines.append("")
        if pdf["count_status"] != "ok":
            err_msg = (pdf.get("count_payload") or {}).get("error", "(no payload)")
            lines.append(f"_Page count failed: status={pdf['count_status']}, error={err_msg}_")
            lines.append("")
            continue

        lines.append("| Page | Status | Text len | Worker ms | Peak KB | Total ms | Error |")
        lines.append("|---:|---|---:|---:|---:|---:|---|")
        for page in pdf["pages"]:
            p_payload = page.get("payload") or {}
            status = page["status"]
            if status == "ok" and p_payload.get("ok"):
                lines.append(
                    f"| {page['page_index']} | ok | "
                    f"{p_payload.get('text_len', 0)} | "
                    f"{p_payload.get('elapsed_ms', 0)} | "
                    f"{p_payload.get('peak_kb', 0)} | "
                    f"{page['elapsed_ms']} | — |"
                )
            elif status == "timeout":
                lines.append(
                    f"| {page['page_index']} | **timeout** | — | — | — | "
                    f"{page['elapsed_ms']} | (killed by orchestrator) |"
                )
            else:
                err = (p_payload or {}).get("error", "(no payload)")
                lines.append(
                    f"| {page['page_index']} | **{status}** | — | — | — | "
                    f"{page['elapsed_ms']} | {err[:80]} |"
                )
        lines.append("")

    lines.append("## Interpretation guide")
    lines.append("")
    lines.append("| Observation | Verdict |")
    lines.append("|---|---|")
    lines.append("| All pages OK | parser is bounded on this PDF set |")
    lines.append("| Any page TIMEOUT | pdfminer pathological-input class confirmed for that page; capture for PE.2 design |")
    lines.append("| Any page ERROR | non-timeout exception in extraction; capture error string |")
    lines.append("| Peak KB consistently small across OK pages | parser memory cost is modest at this PDF scale |")
    lines.append("| Worker ms > 5000 on OK pages | slow but bounded; consider tighter budget in production wrapper |")
    lines.append("")
    lines.append("## Stop conditions encoded in this run")
    lines.append("")
    lines.append(f"- Per-page hard timeout: **{results['page_timeout_sec']} s** — exceeded → page recorded as TIMEOUT, orchestrator continues")
    lines.append(f"- Per-count hard timeout: **{results['count_timeout_sec']} s** — exceeded → PDF skipped, orchestrator continues to next PDF")
    lines.append("- Worker exception → recorded as ERROR with stderr captured (first 500 chars); orchestrator continues")
    lines.append("- Unparseable worker output → recorded as 'unparseable'; orchestrator continues")
    lines.append("")

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("=" * 60, flush=True)
    print("PE.1 — Per-Page Parser Probe", flush=True)
    print("=" * 60, flush=True)
    print(f"REPO_ROOT    {REPO_ROOT}", flush=True)
    print(f"PDF_DIR      {PDF_DIR}", flush=True)
    print(f"WORKER       {WORKER}", flush=True)
    print(f"PYTHON       {sys.executable}", flush=True)
    print(f"PAGE_TO      {PAGE_TIMEOUT_SEC} s/page", flush=True)
    print(f"COUNT_TO     {COUNT_TIMEOUT_SEC} s/count", flush=True)
    print(f"MAX_PDFS     {MAX_PDFS or 'all'}", flush=True)
    print(flush=True)

    if not WORKER.is_file():
        print(f"ABORT: worker not found at {WORKER}", flush=True)
        return 1

    pdfs = _discover_pdfs()
    if not pdfs:
        print(f"ABORT: no PDFs found in {PDF_DIR}", flush=True)
        return 1

    print(f"PDFS         {len(pdfs)} found", flush=True)
    print(flush=True)

    results: Dict[str, Any] = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "page_timeout_sec": PAGE_TIMEOUT_SEC,
        "count_timeout_sec": COUNT_TIMEOUT_SEC,
        "pdf_dir": str(PDF_DIR),
        "pdfs": [],
    }

    for i, pdf_path in enumerate(pdfs):
        record = _probe_one_pdf(i, pdf_path)
        results["pdfs"].append(record)
        print(flush=True)

    OUTPUT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"JSON_WRITTEN  {OUTPUT_JSON}", flush=True)

    _write_markdown(results)
    print(f"MD_WRITTEN    {OUTPUT_MD}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
