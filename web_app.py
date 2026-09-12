"""
Local Web Application for Tamil Nadu School Textbooks Auto-Downloader.
STRICT REQUIREMENT: TAMIL MEDIUM ONLY.
Runs a responsive server supporting both Desktop and Mobile browsers.
"""

import sys
import os
import re
import json
import time
import socket
import zipfile
import io
import threading
import webbrowser
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import List, Dict, Any, Optional

# Ensure UTF-8 output handling
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper import TamilTextbookScraper
from downloader import TamilTextbookDownloader
from models import TextbookResource, MediumStatus
from config import SUPPORTED_CLASSES, SUPPORTED_TERMS, DEFAULT_DOWNLOAD_DIR


# Global state
app_state = {
    "is_scanning": False,
    "is_downloading": False,
    "is_paused": False,
    "is_cancelled": False,
    "discovered_books": [],
    "ambiguous_books": [],
    "logs": [],
    "overall_progress": {"current": 0, "total": 0, "pct": 0},
    "file_progress": {"book": "", "current_bytes": 0, "total_bytes": 0, "pct": 0},
    "download_results": None,
}

downloader_instance: Optional[TamilTextbookDownloader] = None
state_lock = threading.Lock()


def add_log(msg: str):
    with state_lock:
        app_state["logs"].append(msg)
        if len(app_state["logs"]) > 2000:
            app_state["logs"] = app_state["logs"][-2000:]


def get_local_ip() -> str:
    """Detects local LAN IP for mobile Wi-Fi connection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class TextbookWebHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Silence default request logging to keep console clean
        pass

    def send_json_response(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.serve_html()
        elif path == "/api/status":
            with state_lock:
                self.send_json_response(app_state)
        elif path == "/api/system_info":
            self.handle_system_info()
        elif path == "/api/direct_download":
            self.handle_direct_download(query)
        elif path == "/api/download_zip":
            self.handle_download_zip()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            params = json.loads(post_data.decode("utf-8"))
        except Exception:
            params = {}

        if self.path == "/api/scan":
            self.handle_scan(params)
        elif self.path == "/api/download":
            self.handle_download(params)
        elif self.path == "/api/pause":
            self.handle_pause()
        elif self.path == "/api/resume":
            self.handle_resume()
        elif self.path == "/api/cancel":
            self.handle_cancel()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_system_info(self):
        is_android = (
            "ANDROID_ROOT" in os.environ
            or "TERMUX_VERSION" in os.environ
            or Path("/sdcard").exists()
            or Path("/storage/emulated/0").exists()
        )

        if Path("/storage/emulated/0/Download").exists():
            mobile_path = "/storage/emulated/0/Download/Tamil_Medium"
        elif Path("/sdcard/Download").exists():
            mobile_path = "/sdcard/Download/Tamil_Medium"
        else:
            mobile_path = str((Path.home() / "Downloads" / "Tamil_Medium").resolve())

        project_path = str((Path(__file__).parent / "downloads" / "Tamil_Medium").resolve())
        default_dir = mobile_path if is_android else DEFAULT_DOWNLOAD_DIR

        self.send_json_response({
            "is_android": is_android,
            "default_dest": default_dir.replace("\\", "/"),
            "mobile_download_path": mobile_path.replace("\\", "/"),
            "project_download_path": project_path.replace("\\", "/"),
        })

    def handle_direct_download(self, query: Dict[str, List[str]]):
        book_url = query.get("url", [""])[0]
        book_name = query.get("name", ["Tamil_Medium_Textbook.pdf"])[0]

        if not book_url:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing 'url' parameter.")
            return

        safe_name = re.sub(r'[\\/*?:"<>|]', "", book_name)
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"

        encoded_name = urllib.parse.quote(safe_name)
        downloader = TamilTextbookDownloader(download_dir=DEFAULT_DOWNLOAD_DIR)
        direct_url = downloader.resolve_download_url(book_url)

        try:
            stream = downloader.open_download_stream(direct_url)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{encoded_name}')
            content_length = stream.headers.get("Content-Length")
            if content_length:
                self.send_header("Content-Length", content_length)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            chunk_size = 64 * 1024
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except Exception as e:
            add_log(f"[DIRECT DOWNLOAD ERROR] {e}")
            try:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Direct download error: {e}".encode("utf-8"))
            except Exception:
                pass

    def handle_download_zip(self):
        with state_lock:
            pool = list(app_state["discovered_books"])

        if not pool:
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("No verified Tamil Medium books found. Run a scan first.".encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="Tamil_Medium_School_Textbooks.zip"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        downloader = TamilTextbookDownloader(download_dir=DEFAULT_DOWNLOAD_DIR)
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for b in pool:
                try:
                    c_num = b["class_num"]
                    s_name = re.sub(r'[\\/*?:"<>|]', "", b["subject_display"]).strip()
                    term_c = b["term"].replace(" ", "_") if b["term"] else "Full_Book"
                    fname = f"Class_{c_num}/{c_num}th_Tamil_Medium_{s_name}_{term_c}.pdf"

                    disk_path = None
                    if downloader_instance:
                        candidates = list(downloader_instance.download_dir.glob(f"**/{c_num}th_Tamil_Medium_{s_name}_{term_c}.pdf"))
                        if candidates and candidates[0].exists():
                            disk_path = candidates[0]

                    if disk_path and disk_path.exists():
                        zf.write(str(disk_path), arcname=fname)
                    else:
                        direct_url = downloader.resolve_download_url(b["download_url"])
                        stream = downloader.open_download_stream(direct_url)
                        data = stream.read()
                        if data and data.startswith(b"%PDF-"):
                            zf.writestr(fname, data)
                except Exception as ex:
                    add_log(f"[ZIP WARNING] Skipped {b.get('subject_display')} in zip: {ex}")

        self.wfile.write(zip_buffer.getvalue())

    def handle_scan(self, params: Dict[str, Any]):
        classes = params.get("classes", [8])
        term = params.get("term", "All Terms")
        edition = params.get("edition", "All Editions")

        with state_lock:
            if app_state["is_scanning"] or app_state["is_downloading"]:
                self.send_json_response({"error": "An operation is already in progress"}, 400)
                return
            app_state["is_scanning"] = True
            app_state["overall_progress"] = {"current": 0, "total": 0, "pct": 0}

        def run_scan():
            add_log("[SCAN] Initiating scan for Tamil Medium school textbooks...")
            scraper = TamilTextbookScraper(log_callback=add_log)
            all_tamil = []
            all_amb = []
            for c_num in classes:
                add_log(f"Scanning Class {c_num}...")
                t_books, a_books = scraper.scrape_class(int(c_num), target_term=term, target_edition=edition)
                all_tamil.extend(t_books)
                all_amb.extend(a_books)

            with state_lock:
                app_state["discovered_books"] = [
                    {
                        "class_num": b.class_num,
                        "edition": b.edition,
                        "term": b.term,
                        "subject_raw": b.subject_raw,
                        "subject_display": b.subject_display,
                        "tamil_title": b.tamil_title or b.subject_raw,
                        "download_url": b.download_url,
                        "status": "Verified (Ready)",
                    }
                    for b in all_tamil
                ]
                app_state["ambiguous_books"] = [
                    {
                        "class_num": b.class_num,
                        "edition": b.edition,
                        "term": b.term,
                        "subject_raw": b.subject_raw,
                        "subject_display": b.subject_display,
                        "status": b.medium_status.value,
                        "notes": b.notes or "Medium uncertain",
                        "download_url": b.download_url,
                    }
                    for b in all_amb
                ]
                app_state["is_scanning"] = False
            add_log(f"[SCAN COMPLETE] Found {len(all_tamil)} verified Tamil Medium textbooks, {len(all_amb)} skipped for safety.")

        threading.Thread(target=run_scan, daemon=True).start()
        self.send_json_response({"status": "scan_started"})

    def handle_download(self, params: Dict[str, Any]):
        global downloader_instance
        raw_dest = params.get("dest", DEFAULT_DOWNLOAD_DIR).strip()
        if not raw_dest:
            raw_dest = DEFAULT_DOWNLOAD_DIR

        dest_path = Path(raw_dest)
        if not dest_path.is_absolute():
            dest_path = (Path(__file__).parent / dest_path).resolve()
        dest = str(dest_path)

        term = params.get("term", "All Terms")
        edition = params.get("edition", "All Editions")
        selected_urls = params.get("selected_urls", [])

        with state_lock:
            if app_state["is_downloading"] or app_state["is_scanning"]:
                self.send_json_response({"error": "An operation is already in progress"}, 400)
                return

            pool = app_state["discovered_books"]
            if selected_urls:
                targets = [b for b in pool if b["download_url"] in selected_urls]
            else:
                targets = list(pool)

            if not targets:
                self.send_json_response({"error": "No verified Tamil Medium books to download"}, 400)
                return

            app_state["is_downloading"] = True
            app_state["is_paused"] = False
            app_state["is_cancelled"] = False
            app_state["download_results"] = None
            app_state["overall_progress"] = {"current": 0, "total": len(targets), "pct": 0}

        def on_file_prog(res: TextbookResource, cur: int, tot: int, pct: float):
            with state_lock:
                app_state["file_progress"] = {
                    "book": res.book_display_name,
                    "current_bytes": cur,
                    "total_bytes": tot,
                    "pct": pct,
                }

        def on_overall_prog(cur: int, tot: int):
            with state_lock:
                app_state["overall_progress"] = {
                    "current": cur,
                    "total": tot,
                    "pct": (cur / tot) * 100.0 if tot > 0 else 0,
                }

        def on_file_comp(res: TextbookResource, path: str, status: str):
            with state_lock:
                for b in app_state["discovered_books"]:
                    if b["download_url"] == res.download_url:
                        b["status"] = status
                        break

        downloader_instance = TamilTextbookDownloader(
            download_dir=dest,
            on_log=add_log,
            on_file_progress=on_file_prog,
            on_overall_progress=on_overall_prog,
            on_file_complete=on_file_comp,
        )

        from models import MediumContext
        resources = []
        for t in targets:
            ctx = MediumContext(
                class_num=t["class_num"],
                edition=t["edition"],
                medium="Tamil",
                term=t["term"],
                section_heading="Tamil Medium",
            )
            res = TextbookResource(
                class_num=t["class_num"],
                edition=t["edition"],
                term=t["term"],
                subject_raw=t["subject_raw"],
                subject_display=t["subject_display"],
                tamil_title=t["tamil_title"],
                download_url=t["download_url"],
                source_page="",
                context=ctx,
                medium_status=MediumStatus.TAMIL_CONFIRMED,
            )
            resources.append(res)

        def run_dl():
            results = downloader_instance.download_queue(
                resources=resources,
                expected_term=term,
                expected_edition=edition,
            )
            with state_lock:
                app_state["is_downloading"] = False
                app_state["download_results"] = results
            add_log(f"[ALL DOWNLOADS COMPLETED] Saved {results['completed']} files to {dest}")

        threading.Thread(target=run_dl, daemon=True).start()
        self.send_json_response({"status": "download_started", "count": len(resources)})

    def handle_pause(self):
        global downloader_instance
        if downloader_instance:
            downloader_instance.pause()
            with state_lock:
                app_state["is_paused"] = True
        self.send_json_response({"status": "paused"})

    def handle_resume(self):
        global downloader_instance
        if downloader_instance:
            downloader_instance.resume()
            with state_lock:
                app_state["is_paused"] = False
        self.send_json_response({"status": "resumed"})

    def handle_cancel(self):
        global downloader_instance
        if downloader_instance:
            downloader_instance.cancel()
            with state_lock:
                app_state["is_cancelled"] = True
                app_state["is_downloading"] = False
        self.send_json_response({"status": "cancelled"})

    def serve_html(self):
        default_dir = DEFAULT_DOWNLOAD_DIR.replace("\\", "/")
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Tamil Nadu School Textbooks Auto-Downloader (Tamil Medium Only)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-main: #0b0f19;
      --bg-card: #151d30;
      --bg-card-hover: #1c263f;
      --border-color: #24304d;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent-green: #10b981;
      --accent-green-dark: #064e3b;
      --accent-blue: #3b82f6;
      --accent-blue-hover: #2563eb;
      --accent-purple: #8b5cf6;
      --accent-red: #ef4444;
      --accent-amber: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-main);
      color: var(--text-main);
      line-height: 1.5;
      padding: 16px;
      -webkit-tap-highlight-color: transparent;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    
    /* Header Card */
    .header-card {
      background: linear-gradient(135deg, #151d30 0%, #1e293b 100%);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 20px 24px;
      margin-bottom: 20px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }
    .header-title h1 {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: #ffffff;
      margin-bottom: 6px;
    }
    .header-notice {
      color: #fbbf24;
      font-size: 13px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .badge-medium {
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid var(--accent-green);
      color: #34d399;
      font-weight: 700;
      font-size: 13px;
      padding: 8px 16px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 1px;
      display: flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 0 20px rgba(16, 185, 129, 0.2);
    }
    .badge-dot {
      width: 10px;
      height: 10px;
      background: var(--accent-green);
      border-radius: 50%;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
      100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Controls Card */
    .controls-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .form-row {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: center;
      margin-bottom: 18px;
    }
    .form-row:last-child { margin-bottom: 0; }
    
    .label-heading {
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-right: 6px;
    }
    .checkbox-group {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .custom-checkbox {
      background: #1e293b;
      border: 1px solid var(--border-color);
      padding: 8px 14px;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 500;
      transition: all 0.2s;
      min-height: 40px;
    }
    .custom-checkbox:hover { background: var(--bg-card-hover); border-color: var(--accent-blue); }
    .custom-checkbox input { accent-color: var(--accent-green); cursor: pointer; width: 16px; height: 16px; }

    .select-input, .text-input {
      background: #1e293b;
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
      font-family: inherit;
      min-height: 42px;
    }
    .select-input:focus, .text-input:focus { border-color: var(--accent-blue); }
    
    /* Dedicated Path & Mobile Storage Card */
    .dest-card {
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 18px;
    }
    .dest-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .dest-title {
      font-size: 14px;
      font-weight: 700;
      color: #38bdf8;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .dest-presets {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 12px;
    }
    .btn-preset {
      background: #1e293b;
      border: 1px solid #3b82f6;
      color: #93c5fd;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      font-family: inherit;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .btn-preset:hover {
      background: #2563eb;
      color: #ffffff;
    }
    .dest-input-wrap {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .dest-input {
      flex: 1;
      min-width: 240px;
      font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: 13px;
      background: #070a12;
      border: 1px solid #334155;
    }
    .dest-help {
      margin-top: 10px;
      font-size: 12px;
      color: #94a3b8;
      line-height: 1.5;
    }
    .dest-help strong { color: #f8fafc; }

    /* Action Buttons */
    .btn {
      padding: 10px 18px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font-family: inherit;
      min-height: 42px;
    }
    .btn-primary { background: var(--accent-blue); color: white; }
    .btn-primary:hover { background: var(--accent-blue-hover); transform: translateY(-1px); }
    .btn-zip { background: var(--accent-purple); color: white; }
    .btn-zip:hover { background: #7c3aed; transform: translateY(-1px); }
    .btn-scan { background: #334155; color: #f8fafc; }
    .btn-scan:hover { background: #475569; }
    .btn-pause { background: #d97706; color: white; }
    .btn-cancel { background: var(--accent-red); color: white; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

    /* Progress section */
    .progress-box {
      margin-top: 16px;
      padding: 16px;
      background: #0d1322;
      border-radius: 12px;
      border: 1px solid var(--border-color);
    }
    .progress-bar-bg {
      height: 10px;
      background: #1e293b;
      border-radius: 999px;
      overflow: hidden;
      margin: 10px 0;
    }
    .progress-bar-fill {
      height: 100%;
      background: linear-gradient(90deg, #10b981 0%, #34d399 100%);
      width: 0%;
      transition: width 0.3s ease;
    }
    .progress-meta {
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      color: var(--text-muted);
      flex-wrap: wrap;
      gap: 6px;
    }

    /* Tabs */
    .tabs-header {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 16px;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    .tab-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 14px;
      font-weight: 600;
      padding: 12px 16px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
      font-family: inherit;
      white-space: nowrap;
    }
    .tab-btn.active {
      color: #38bdf8;
      border-bottom-color: #38bdf8;
    }

    /* Table */
    .table-wrapper {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      overflow-x: auto;
      max-height: 540px;
      -webkit-overflow-scrolling: touch;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
      min-width: 650px;
    }
    th {
      background: #1e293b;
      padding: 12px 14px;
      font-weight: 600;
      color: #cbd5e1;
      border-bottom: 1px solid var(--border-color);
      position: sticky;
      top: 0;
      z-index: 10;
      white-space: nowrap;
    }
    td {
      padding: 12px 14px;
      border-bottom: 1px solid #1e293b;
      color: #e2e8f0;
      vertical-align: middle;
    }
    tr:hover td { background: var(--bg-card-hover); }
    .badge-status {
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      display: inline-block;
      white-space: nowrap;
    }
    .status-verified { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-downloading { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
    .status-completed { background: rgba(16, 185, 129, 0.25); color: #10b981; }
    .status-failed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .status-ambiguous { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

    /* Action buttons in table */
    .btn-table-dl {
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid var(--accent-blue);
      color: #60a5fa;
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
      transition: all 0.2s;
    }
    .btn-table-dl:hover {
      background: var(--accent-blue);
      color: #ffffff;
    }

    /* Log Terminal */
    .log-box {
      background: #070a12;
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 16px;
      font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: 12px;
      color: #38bdf8;
      height: 440px;
      overflow-y: auto;
      white-space: pre-wrap;
      line-height: 1.6;
    }

    /* Responsive Design for Mobile Viewports */
    @media (max-width: 768px) {
      body { padding: 10px; }
      .header-card { padding: 16px; }
      .header-title h1 { font-size: 18px; }
      .header-notice { font-size: 12px; }
      .controls-card { padding: 14px; }
      .form-row { flex-direction: column; align-items: stretch; gap: 12px; }
      .checkbox-group { width: 100%; justify-content: flex-start; }
      .select-input, .text-input { width: 100%; }
      .dest-input-wrap { flex-direction: column; align-items: stretch; }
      .dest-input { width: 100%; }
      .btn { width: 100%; }
      .btn-scan, .btn-primary, .btn-zip { width: 100%; }
      .actions-container { display: flex; flex-direction: column; gap: 10px; width: 100%; }
      .table-wrapper { max-height: 450px; }
      .log-box { height: 350px; font-size: 11px; }
    }
  </style>
</head>
<body>
  <div class="container">
    
    <!-- Top Header -->
    <div class="header-card">
      <div class="header-title">
        <h1>Tamil Nadu School Textbooks Auto-Downloader</h1>
        <div class="header-notice">
          ⚠️ Notice: Only Tamil Medium textbooks will be downloaded. English Medium textbooks are strictly excluded.
        </div>
      </div>
      <div class="badge-medium">
        <span class="badge-dot"></span>
        Tamil Medium Only
      </div>
    </div>

    <!-- Control Center -->
    <div class="controls-card">
      <!-- Classes Row -->
      <div class="form-row">
        <span class="label-heading">Select Classes:</span>
        <div class="checkbox-group">
          <label class="custom-checkbox"><input type="checkbox" name="class" value="8" checked> Class 8</label>
          <label class="custom-checkbox"><input type="checkbox" name="class" value="9"> Class 9</label>
          <label class="custom-checkbox"><input type="checkbox" name="class" value="10"> Class 10</label>
          <label class="custom-checkbox"><input type="checkbox" name="class" value="11"> Class 11</label>
          <label class="custom-checkbox"><input type="checkbox" name="class" value="12"> Class 12</label>
          <button type="button" class="btn btn-scan" onclick="selectAllClasses(true)" style="padding: 6px 12px; font-size: 12px; min-height: 36px;">Select All</button>
          <button type="button" class="btn btn-scan" onclick="selectAllClasses(false)" style="padding: 6px 12px; font-size: 12px; min-height: 36px;">Clear</button>
        </div>
      </div>

      <!-- Filters Row -->
      <div class="form-row">
        <div style="flex: 1; min-width: 140px;">
          <span class="label-heading">Term:</span>
          <select id="termSelect" class="select-input" style="width: 100%;">
            <option value="All Terms">All Terms</option>
            <option value="Term 1">Term 1</option>
            <option value="Term 2">Term 2</option>
            <option value="Term 3">Term 3</option>
            <option value="Full Book">Full Book</option>
          </select>
        </div>

        <div style="flex: 1; min-width: 160px;">
          <span class="label-heading">Edition:</span>
          <select id="editionSelect" class="select-input" style="width: 100%;">
            <option value="All Editions">All Editions</option>
            <option value="2024-25 Edition">2024-25 Edition</option>
            <option value="2022-23 Edition">2022-23 Edition</option>
            <option value="2019 Edition">2019 Edition</option>
            <option value="Old Edition">Old Edition</option>
          </select>
        </div>
      </div>

      <!-- Dedicated Download Path & Mobile Preset Card -->
      <div class="dest-card">
        <div class="dest-header">
          <span class="dest-title">📁 Download Destination & Mobile Storage</span>
          <span id="platformBadge" style="font-size: 11px; color: #34d399; background: rgba(16, 185, 129, 0.15); padding: 3px 8px; border-radius: 6px;">Ready</span>
        </div>
        <div class="dest-presets">
          <span class="preset-label" style="font-size: 12px; color: var(--text-muted);">Quick Presets:</span>
          <button type="button" class="btn-preset" onclick="setPreset('mobile')">📱 Phone Downloads</button>
          <button type="button" class="btn-preset" onclick="setPreset('project')">📁 Project Folder</button>
          <button type="button" class="btn-preset" onclick="setPreset('custom')">📂 Custom Folder</button>
        </div>
        <div class="dest-input-wrap">
          <input type="text" id="destInput" class="text-input dest-input" value="__DEFAULT_DIR__">
        </div>
        <div class="dest-help">
          💡 <strong>Mobile Tip:</strong> On phone browsers, tap <strong>"⬇ Save to Phone"</strong> on any book row to download directly into your mobile phone's Downloads folder, or tap <strong>"📦 Download All (ZIP)"</strong> below!
        </div>
      </div>

      <!-- Action Buttons Row -->
      <div class="actions-container">
        <div class="form-row" style="margin-top: 10px;">
          <button id="btnScan" class="btn btn-scan" onclick="triggerScan()">🔍 Scan Tamil Textbooks</button>
          <button id="btnDownload" class="btn btn-primary" onclick="triggerDownload()" disabled>⬇ Download All to Storage</button>
          <button id="btnZip" class="btn btn-zip" onclick="triggerDownloadZip()" disabled>📦 Download All (ZIP to Phone)</button>
          <button id="btnPause" class="btn btn-pause" onclick="togglePause()" style="display: none;">⏸ Pause</button>
          <button id="btnCancel" class="btn btn-cancel" onclick="triggerCancel()" style="display: none;">⏹ Cancel</button>
        </div>
        <div style="margin-top: 6px;">
          <span id="lblStatus" style="font-size: 13px; color: var(--text-muted);">Ready. Click 'Scan Tamil Textbooks' to start.</span>
        </div>
      </div>

      <!-- Live Progress Bar -->
      <div id="progressBox" class="progress-box" style="display: none;">
        <div class="progress-meta">
          <span id="lblProgressBook">Downloading...</span>
          <span id="lblProgressPct">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div id="progressBarFill" class="progress-bar-fill"></div>
        </div>
        <div class="progress-meta">
          <span id="lblOverallCount">0 / 0 completed</span>
          <span id="lblBytesCount"></span>
        </div>
      </div>
    </div>

    <!-- Tabs Container -->
    <div class="tabs-header">
      <button class="tab-btn active" onclick="switchTab(event, 'tab-books')">Verified Tamil Medium Books (<span id="countBooks">0</span>)</button>
      <button class="tab-btn" onclick="switchTab(event, 'tab-logs')">Real-Time Download Log</button>
      <button class="tab-btn" onclick="switchTab(event, 'tab-amb')">Ambiguous / Skipped (<span id="countAmb">0</span>)</button>
    </div>

    <!-- TAB 1: Books Table -->
    <div id="tab-books" class="tab-content table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Class</th>
            <th>Edition</th>
            <th>Term</th>
            <th>Subject</th>
            <th>Tamil Title</th>
            <th>Status</th>
            <th>Direct Download</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody id="booksTbody">
          <tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">Click "Scan Tamil Textbooks" to discover books.</td></tr>
        </tbody>
      </table>
    </div>

    <!-- TAB 2: Logs Viewer -->
    <div id="tab-logs" class="tab-content" style="display: none;">
      <div id="logViewer" class="log-box">Waiting for logs...</div>
    </div>

    <!-- TAB 3: Ambiguous Resources -->
    <div id="tab-amb" class="tab-content table-wrapper" style="display: none;">
      <table>
        <thead>
          <tr>
            <th>Class</th>
            <th>Edition</th>
            <th>Term</th>
            <th>Subject</th>
            <th>Reason Skipped</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody id="ambTbody">
          <tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">No ambiguous resources skipped.</td></tr>
        </tbody>
      </table>
    </div>

  </div>

  <script>
    let pollInterval = null;
    let isPaused = false;
    let systemInfo = {
      is_android: false,
      default_dest: '',
      mobile_download_path: '/storage/emulated/0/Download/Tamil_Medium',
      project_download_path: 'downloads/Tamil_Medium'
    };

    async function loadSystemInfo() {
      try {
        const res = await fetch('/api/system_info');
        systemInfo = await res.json();
        if (systemInfo.is_android) {
          document.getElementById('platformBadge').innerText = "📱 Android Detected";
          document.getElementById('destInput').value = systemInfo.mobile_download_path;
        } else {
          document.getElementById('platformBadge').innerText = "💻 Desktop / Server Host";
        }
      } catch (err) {
        console.warn("Could not load system info:", err);
      }
    }

    function setPreset(type) {
      const input = document.getElementById('destInput');
      if (type === 'mobile') {
        input.value = systemInfo.mobile_download_path || '/storage/emulated/0/Download/Tamil_Medium';
      } else if (type === 'project') {
        input.value = systemInfo.project_download_path || 'downloads/Tamil_Medium';
      } else if (type === 'custom') {
        const val = prompt("Enter target directory path:", input.value);
        if (val && val.trim()) input.value = val.trim();
      }
    }

    function selectAllClasses(checked) {
      document.querySelectorAll('input[name="class"]').forEach(cb => cb.checked = checked);
    }

    function switchTab(evt, tabId) {
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
      if (evt && evt.target) {
        evt.target.classList.add('active');
      }
      document.getElementById(tabId).style.display = 'block';
    }

    async function triggerScan() {
      const selectedClasses = Array.from(document.querySelectorAll('input[name="class"]:checked')).map(cb => parseInt(cb.value));
      if (!selectedClasses.length) {
        alert("Please select at least one class.");
        return;
      }
      const term = document.getElementById('termSelect').value;
      const edition = document.getElementById('editionSelect').value;

      document.getElementById('btnScan').disabled = true;
      document.getElementById('btnDownload').disabled = true;
      document.getElementById('btnZip').disabled = true;
      document.getElementById('lblStatus').innerText = "Scanning Tamil textbooks...";

      await fetch('/api/scan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({classes: selectedClasses, term, edition})
      });

      startPolling();
    }

    async function triggerDownload() {
      const dest = document.getElementById('destInput').value;
      const term = document.getElementById('termSelect').value;
      const edition = document.getElementById('editionSelect').value;

      if (!confirm("Start downloading verified Tamil Medium textbooks to storage folder?\\nPath: " + dest)) return;

      document.getElementById('btnDownload').disabled = true;
      document.getElementById('btnZip').disabled = true;
      document.getElementById('btnScan').disabled = true;
      document.getElementById('btnPause').style.display = 'inline-flex';
      document.getElementById('btnCancel').style.display = 'inline-flex';
      document.getElementById('progressBox').style.display = 'block';

      await fetch('/api/download', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({dest, term, edition})
      });

      startPolling();
    }

    function triggerDownloadZip() {
      if (!confirm("Download all verified Tamil Medium books as a single ZIP directly to your device?")) return;
      window.location.href = '/api/download_zip';
    }

    async function togglePause() {
      const btn = document.getElementById('btnPause');
      if (!isPaused) {
        await fetch('/api/pause', {method: 'POST'});
        btn.innerText = '▶ Resume';
        isPaused = true;
      } else {
        await fetch('/api/resume', {method: 'POST'});
        btn.innerText = '⏸ Pause';
        isPaused = false;
      }
    }

    async function triggerCancel() {
      if (confirm("Cancel the download queue?")) {
        await fetch('/api/cancel', {method: 'POST'});
      }
    }

    function startPolling() {
      if (!pollInterval) {
        pollInterval = setInterval(pollStatus, 800);
      }
    }

    async function pollStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // Update counts
        document.getElementById('countBooks').innerText = data.discovered_books.length;
        document.getElementById('countAmb').innerText = data.ambiguous_books.length;

        // Render Books Table
        if (data.discovered_books.length > 0) {
          const tbody = document.getElementById('booksTbody');
          tbody.innerHTML = data.discovered_books.map(b => {
            const safeName = `${b.class_num}th_Tamil_Medium_${b.subject_display.replace(/[^a-zA-Z0-9_-]/g, '_')}_${b.term.replace(/\\s+/g, '_')}.pdf`;
            const directDlUrl = `/api/direct_download?url=${encodeURIComponent(b.download_url)}&name=${encodeURIComponent(safeName)}`;
            return `
              <tr>
                <td style="text-align: center; font-weight: 600;">${b.class_num}</td>
                <td>${b.edition}</td>
                <td style="text-align: center;">${b.term}</td>
                <td style="font-weight: 500;">${b.subject_display}</td>
                <td style="color: #6ee7b7;">${b.tamil_title}</td>
                <td><span class="badge-status ${getStatusClass(b.status)}">${b.status}</span></td>
                <td>
                  <a href="${directDlUrl}" class="btn-table-dl" download="${safeName}">
                    ⬇ Save to Phone
                  </a>
                </td>
                <td><a href="${b.download_url}" target="_blank" style="color: #38bdf8; text-decoration: none; font-size: 12px;">🔗 Drive Link</a></td>
              </tr>
            `;
          }).join('');

          if (!data.is_downloading && !data.is_scanning) {
            document.getElementById('btnDownload').disabled = false;
            document.getElementById('btnZip').disabled = false;
          }
        }

        // Render Ambiguous Table
        if (data.ambiguous_books.length > 0) {
          const ambBody = document.getElementById('ambTbody');
          ambBody.innerHTML = data.ambiguous_books.map(b => `
            <tr>
              <td style="text-align: center;">${b.class_num}</td>
              <td>${b.edition}</td>
              <td>${b.term}</td>
              <td>${b.subject_display}</td>
              <td style="color: #fbbf24;">${b.notes}</td>
              <td><a href="${b.download_url}" target="_blank" style="color: #38bdf8; text-decoration: none; font-size: 12px;">🔗 Drive Link</a></td>
            </tr>
          `).join('');
        }

        // Render Logs
        if (data.logs.length > 0) {
          const logViewer = document.getElementById('logViewer');
          logViewer.innerText = data.logs.join('\\n');
          logViewer.scrollTop = logViewer.scrollHeight;
        }

        // Render Progress
        if (data.is_downloading) {
          document.getElementById('progressBox').style.display = 'block';
          const op = data.overall_progress;
          const fp = data.file_progress;
          document.getElementById('progressBarFill').style.width = op.pct + '%';
          document.getElementById('lblProgressPct').innerText = op.pct.toFixed(1) + '%';
          document.getElementById('lblOverallCount').innerText = `${op.current} of ${op.total} completed`;
          document.getElementById('lblProgressBook').innerText = fp.book || "Downloading...";
          if (fp.total_bytes > 0) {
            document.getElementById('lblBytesCount').innerText = `${Math.round(fp.current_bytes/1024).toLocaleString()} KB / ${Math.round(fp.total_bytes/1024).toLocaleString()} KB`;
          }
        }

        // Handle Completion
        if (!data.is_downloading && !data.is_scanning) {
          document.getElementById('btnScan').disabled = false;
          document.getElementById('btnPause').style.display = 'none';
          document.getElementById('btnCancel').style.display = 'none';
          if (data.download_results) {
            document.getElementById('lblStatus').innerText = `Finished! Downloaded: ${data.download_results.completed}, Failed: ${data.download_results.failed}`;
          }
        }
      } catch (err) {
        console.error("Poll error:", err);
      }
    }

    function getStatusClass(status) {
      if (!status) return 'status-verified';
      if (status.includes('Completed')) return 'status-completed';
      if (status.includes('Downloading')) return 'status-downloading';
      if (status.includes('Failed') || status.includes('Skipped')) return 'status-failed';
      return 'status-verified';
    }

    // Auto load system info and poll on start
    loadSystemInfo();
    pollStatus();
  </script>
</body>
</html>
""".replace("__DEFAULT_DIR__", default_dir)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_content.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))


def start_web_server(port: int = None, open_browser: bool = True):
    if port is None:
        port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")

    server = ThreadingHTTPServer((host, port), TextbookWebHandler)
    local_ip = get_local_ip()
    url_local = f"http://localhost:{port}"
    url_mobile = f"http://{local_ip}:{port}"

    print(f"\n==================================================================")
    print(f"  TAMIL NADU SCHOOL TEXTBOOKS AUTO-DOWNLOADER (TAMIL MEDIUM ONLY)")
    print(f"==================================================================")
    print(f"  * Desktop / Local Browser : {url_local}")
    print(f"  * Mobile Browser on Wi-Fi : {url_mobile}")
    print(f"------------------------------------------------------------------")
    print(f"  [Mobile Access]:")
    print(f"     Open '{url_mobile}' in your mobile phone browser (Chrome/Safari)")
    print(f"     to scan and download Tamil Medium textbooks directly to your phone!")
    print(f"==================================================================\n")

    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url_local)), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web server...")
        server.server_close()


if __name__ == "__main__":
    start_web_server(port=5000, open_browser=True)
