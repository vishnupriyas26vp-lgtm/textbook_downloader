"""
Local Web Application for Tamil Nadu School Textbooks Auto-Downloader.
STRICT REQUIREMENT: TAMIL MEDIUM ONLY.
Runs a local server and opens directly in the browser (Google Chrome, Edge, etc.).
"""

import sys
import os
import json
import time
import threading
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import List, Dict, Any, Optional

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
        if self.path == "/" or self.path == "/index.html":
            self.serve_html()
        elif self.path == "/api/status":
            with state_lock:
                self.send_json_response(app_state)
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
        raw_dest = params.get("dest", DEFAULT_DOWNLOAD_DIR)
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

            # Match discovered books to models
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

        # Convert back to TextbookResource objects
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
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
      --accent-red: #ef4444;
      --accent-amber: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-main);
      color: var(--text-main);
      line-height: 1.5;
      padding: 24px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    
    /* Header Card */
    .header-card {
      background: linear-gradient(135deg, #151d30 0%, #1e293b 100%);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 24px 30px;
      margin-bottom: 20px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }
    .header-title h1 {
      font-size: 24px;
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
      font-size: 14px;
      padding: 10px 18px;
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
      padding: 24px;
      margin-bottom: 24px;
    }
    .form-row {
      display: flex;
      flex-wrap: wrap;
      gap: 20px;
      align-items: center;
      margin-bottom: 20px;
    }
    .form-row:last-child { margin-bottom: 0; }
    
    .label-heading {
      font-size: 13px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-right: 8px;
    }
    .checkbox-group {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }
    .custom-checkbox {
      background: #1e293b;
      border: 1px solid var(--border-color);
      padding: 8px 16px;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 500;
      transition: all 0.2s;
    }
    .custom-checkbox:hover { background: var(--bg-card-hover); border-color: var(--accent-blue); }
    .custom-checkbox input { accent-color: var(--accent-green); cursor: pointer; }

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
    }
    .select-input:focus, .text-input:focus { border-color: var(--accent-blue); }
    
    .btn {
      padding: 10px 20px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-family: inherit;
    }
    .btn-primary { background: var(--accent-blue); color: white; }
    .btn-primary:hover { background: var(--accent-blue-hover); transform: translateY(-1px); }
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
    }

    /* Tabs */
    .tabs-header {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 16px;
    }
    .tab-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 15px;
      font-weight: 600;
      padding: 12px 20px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
      font-family: inherit;
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
      max-height: 520px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      text-align: left;
    }
    th {
      background: #1e293b;
      padding: 14px 18px;
      font-weight: 600;
      color: #cbd5e1;
      border-bottom: 1px solid var(--border-color);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    td {
      padding: 12px 18px;
      border-bottom: 1px solid #1e293b;
      color: #e2e8f0;
    }
    tr:hover td { background: var(--bg-card-hover); }
    .badge-status {
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }
    .status-verified { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-downloading { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
    .status-completed { background: rgba(16, 185, 129, 0.25); color: #10b981; }
    .status-failed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .status-ambiguous { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

    /* Log Terminal */
    .log-box {
      background: #070a12;
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 16px;
      font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: 13px;
      color: #38bdf8;
      height: 480px;
      overflow-y: auto;
      white-space: pre-wrap;
      line-height: 1.6;
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
          <button type="button" class="btn btn-scan" onclick="selectAllClasses(true)" style="padding: 6px 12px; font-size: 12px;">Select All</button>
          <button type="button" class="btn btn-scan" onclick="selectAllClasses(false)" style="padding: 6px 12px; font-size: 12px;">Clear</button>
        </div>
      </div>

      <!-- Filters Row -->
      <div class="form-row">
        <div>
          <span class="label-heading">Term:</span>
          <select id="termSelect" class="select-input">
            <option value="All Terms">All Terms</option>
            <option value="Term 1">Term 1</option>
            <option value="Term 2">Term 2</option>
            <option value="Term 3">Term 3</option>
            <option value="Full Book">Full Book</option>
          </select>
        </div>

        <div>
          <span class="label-heading">Edition:</span>
          <select id="editionSelect" class="select-input">
            <option value="All Editions">All Editions</option>
            <option value="2024-25 Edition">2024-25 Edition</option>
            <option value="2022-23 Edition">2022-23 Edition</option>
            <option value="2019 Edition">2019 Edition</option>
            <option value="Old Edition">Old Edition</option>
          </select>
        </div>

        <div style="flex-grow: 1;">
          <span class="label-heading">Save Folder:</span>
          <input type="text" id="destInput" class="text-input" style="width: 100%;" value="""" + DEFAULT_DOWNLOAD_DIR.replace("\\", "/") + """">
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="form-row" style="margin-top: 10px;">
        <button id="btnScan" class="btn btn-scan" onclick="triggerScan()">🔍 Scan Tamil Textbooks</button>
        <button id="btnDownload" class="btn btn-primary" onclick="triggerDownload()" disabled>⬇ Download All Verified Books</button>
        <button id="btnPause" class="btn btn-pause" onclick="togglePause()" style="display: none;">⏸ Pause</button>
        <button id="btnCancel" class="btn btn-cancel" onclick="triggerCancel()" style="display: none;">⏹ Cancel</button>
        <span id="lblStatus" style="font-size: 14px; color: var(--text-muted); margin-left: auto;">Ready. Click 'Scan Tamil Textbooks'.</span>
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
      <button class="tab-btn active" onclick="switchTab('tab-books')">Verified Tamil Medium Books (<span id="countBooks">0</span>)</button>
      <button class="tab-btn" onclick="switchTab('tab-logs')">Real-Time Download Log</button>
      <button class="tab-btn" onclick="switchTab('tab-amb')">Ambiguous / Skipped (<span id="countAmb">0</span>)</button>
    </div>

    <!-- TAB 1: Books Table -->
    <div id="tab-books" class="tab-content table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Class</th>
            <th>Edition</th>
            <th>Term</th>
            <th>Subject (English)</th>
            <th>Tamil Title</th>
            <th>Status</th>
            <th>Link</th>
          </tr>
        </thead>
        <tbody id="booksTbody">
          <tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">Click "Scan Tamil Textbooks" to discover books.</td></tr>
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
            <th>Link</th>
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

    function selectAllClasses(checked) {
      document.querySelectorAll('input[name="class"]').forEach(cb => cb.checked = checked);
    }

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
      event.target.classList.add('active');
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

      if (!confirm("Start downloading verified Tamil Medium textbooks?")) return;

      document.getElementById('btnDownload').disabled = true;
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
          tbody.innerHTML = data.discovered_books.map(b => `
            <tr>
              <td style="text-align: center; font-weight: 600;">${b.class_num}</td>
              <td>${b.edition}</td>
              <td style="text-align: center;">${b.term}</td>
              <td style="font-weight: 500;">${b.subject_display}</td>
              <td style="color: #6ee7b7;">${b.tamil_title}</td>
              <td><span class="badge-status ${getStatusClass(b.status)}">${b.status}</span></td>
              <td><a href="${b.download_url}" target="_blank" style="color: #38bdf8; text-decoration: none; font-size: 12px;">Link</a></td>
            </tr>
          `).join('');
          if (!data.is_downloading && !data.is_scanning) {
            document.getElementById('btnDownload').disabled = false;
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
              <td><a href="${b.download_url}" target="_blank" style="color: #38bdf8; text-decoration: none; font-size: 12px;">Link</a></td>
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

    // Auto poll once on load
    pollStatus();
  </script>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_content.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))


def start_web_server(port: int = 5000, open_browser: bool = True):
    server = ThreadingHTTPServer(("127.0.0.1", port), TextbookWebHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"\n=======================================================")
    print(f" TAMIL MEDIUM TEXTBOOKS AUTO-DOWNLOADER (WEB GUI)")
    print(f" Web Application running at: {url}")
    print(f" Notice: Only Tamil Medium textbooks will be downloaded.")
    print(f"=======================================================\n")

    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url)), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web server...")
        server.server_close()


if __name__ == "__main__":
    start_web_server(port=5000, open_browser=True)
