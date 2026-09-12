"""
Desktop GUI for Tamil Nadu School Textbooks Auto-Downloader.
STRICT REQUIREMENT: TAMIL MEDIUM ONLY.
English medium is NEVER provided as an active option.
"""

import sys
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Optional

from scraper import TamilTextbookScraper
from downloader import TamilTextbookDownloader
from models import TextbookResource, MediumStatus
from config import SUPPORTED_CLASSES, SUPPORTED_TERMS, DEFAULT_DOWNLOAD_DIR


class TamilMediumApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Tamil Nadu School Textbooks Auto-Downloader (Tamil Medium Only)")
        self.root.geometry("1080x750")
        self.root.minsize(900, 650)

        # Threading and Queue
        self.msg_queue = queue.Queue()
        self.downloader: Optional[TamilTextbookDownloader] = None
        self.download_thread: Optional[threading.Thread] = None

        # Data stores
        self.discovered_books: List[TextbookResource] = []
        self.ambiguous_books: List[TextbookResource] = []

        # Setup styling
        self._setup_styles()

        # Build UI layout
        self._build_ui()

        # Start periodic queue polling
        self.root.after(100, self._process_queue)

    def _setup_styles(self):
        self.style = ttk.Style()
        # Use clam or default theme for clean custom colors
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Color Palette
        self.BG_MAIN = "#0f172a"        # Dark slate
        self.BG_CARD = "#1e293b"        # Card slate
        self.BG_ACCENT = "#334155"      # Lighter slate
        self.TEXT_PRIMARY = "#f8fafc"   # White text
        self.TEXT_MUTED = "#94a3b8"     # Gray text
        self.COLOR_GREEN = "#10b981"    # Emerald green for Tamil Medium badge
        self.COLOR_BLUE = "#3b82f6"     # Vibrant blue for primary buttons
        self.COLOR_RED = "#ef4444"      # Red for cancel

        self.root.configure(bg=self.BG_MAIN)

        # Style configuration
        self.style.configure(".", background=self.BG_MAIN, foreground=self.TEXT_PRIMARY)
        self.style.configure("TFrame", background=self.BG_MAIN)
        self.style.configure("Card.TFrame", background=self.BG_CARD, relief="flat")
        self.style.configure("TLabel", background=self.BG_MAIN, foreground=self.TEXT_PRIMARY, font=("Segoe UI", 10))
        self.style.configure("Card.TLabel", background=self.BG_CARD, foreground=self.TEXT_PRIMARY, font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", background=self.BG_CARD, foreground=self.TEXT_PRIMARY, font=("Segoe UI", 15, "bold"))
        self.style.configure("Muted.TLabel", background=self.BG_CARD, foreground=self.TEXT_MUTED, font=("Segoe UI", 9))
        self.style.configure("Warning.TLabel", background=self.BG_CARD, foreground="#fbbf24", font=("Segoe UI", 9, "bold"))

        # Badge Style
        self.style.configure("Badge.TLabel", background="#064e3b", foreground="#34d399", font=("Segoe UI", 11, "bold"), padding=6)

        # Button Styles
        self.style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=6, background=self.COLOR_BLUE, foreground="#ffffff")
        self.style.configure("Cancel.TButton", font=("Segoe UI", 10, "bold"), padding=6, background=self.COLOR_RED, foreground="#ffffff")

        # Treeview styling
        self.style.configure(
            "Treeview",
            background="#1e293b",
            foreground="#f8fafc",
            fieldbackground="#1e293b",
            rowheight=26,
            font=("Segoe UI", 9),
        )
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#334155", foreground="#ffffff")
        self.style.map("Treeview", background=[("selected", "#2563eb")])

        # Progressbar
        self.style.configure("TProgressbar", thickness=10, background=self.COLOR_GREEN)

    def _build_ui(self):
        # 1. TOP BANNER: STRICT MEDIUM HEADER
        top_card = ttk.Frame(self.root, style="Card.TFrame", padding=15)
        top_card.pack(fill="x", padx=15, pady=(15, 10))

        # Title & Strict Medium Requirement Display
        header_row = ttk.Frame(top_card, style="Card.TFrame")
        header_row.pack(fill="x")

        title_label = ttk.Label(
            header_row,
            text="Tamil Nadu School Textbooks Auto-Downloader",
            style="Header.TLabel",
        )
        title_label.pack(side="left")

        # Mandatory Medium Display as requested:
        # MEDIUM
        # ● TAMIL MEDIUM ONLY
        medium_frame = ttk.Frame(header_row, style="Card.TFrame")
        medium_frame.pack(side="right")

        med_title = ttk.Label(medium_frame, text="MEDIUM", style="Muted.TLabel", font=("Segoe UI", 8, "bold"))
        med_title.pack(anchor="e")

        badge = ttk.Label(
            medium_frame,
            text="● TAMIL MEDIUM ONLY",
            style="Badge.TLabel",
        )
        badge.pack(anchor="e")

        # Notice row
        notice_label = ttk.Label(
            top_card,
            text="Notice: Only Tamil Medium textbooks will be downloaded. English Medium textbooks are strictly excluded.",
            style="Warning.TLabel",
        )
        notice_label.pack(anchor="w", pady=(8, 0))

        # 2. CONTROLS CARD
        ctrl_card = ttk.Frame(self.root, style="Card.TFrame", padding=15)
        ctrl_card.pack(fill="x", padx=15, pady=5)

        # Classes Row
        class_row = ttk.Frame(ctrl_card, style="Card.TFrame")
        class_row.pack(fill="x", pady=(0, 10))

        ttk.Label(class_row, text="Select Classes:", style="Card.TLabel", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 10))

        self.class_vars = {}
        for c in SUPPORTED_CLASSES:
            var = tk.BooleanVar(value=(c == 8))  # Default 8 checked
            self.class_vars[c] = var
            cb = tk.Checkbutton(
                class_row,
                text=f"Class {c}",
                variable=var,
                bg=self.BG_CARD,
                fg=self.TEXT_PRIMARY,
                selectcolor=self.BG_ACCENT,
                activebackground=self.BG_CARD,
                activeforeground=self.TEXT_PRIMARY,
                font=("Segoe UI", 9),
            )
            cb.pack(side="left", padx=5)

        # Select All / Clear buttons
        btn_all = ttk.Button(class_row, text="Select All", style="Action.TButton", command=self._select_all_classes)
        btn_all.pack(side="left", padx=(15, 5))
        btn_clear = ttk.Button(class_row, text="Clear", style="Action.TButton", command=self._clear_all_classes)
        btn_clear.pack(side="left", padx=5)

        # Filters Row (Term, Edition, Subject)
        filter_row = ttk.Frame(ctrl_card, style="Card.TFrame")
        filter_row.pack(fill="x", pady=(0, 10))

        # Term filter
        ttk.Label(filter_row, text="Term:", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.term_var = tk.StringVar(value="All Terms")
        term_combo = ttk.Combobox(
            filter_row,
            textvariable=self.term_var,
            values=["All Terms", "Term 1", "Term 2", "Term 3", "Full Book"],
            state="readonly",
            width=12,
        )
        term_combo.pack(side="left", padx=(0, 20))

        # Edition filter
        ttk.Label(filter_row, text="Edition:", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.edition_var = tk.StringVar(value="All Editions")
        edition_combo = ttk.Combobox(
            filter_row,
            textvariable=self.edition_var,
            values=["All Editions", "2024-25 Edition", "2022-23 Edition", "2019 Edition", "Old Edition"],
            state="readonly",
            width=16,
        )
        edition_combo.pack(side="left", padx=(0, 20))

        # Subject Search Filter
        ttk.Label(filter_row, text="Subject Search:", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.subject_search_var = tk.StringVar()
        subj_entry = ttk.Entry(filter_row, textvariable=self.subject_search_var, width=20)
        subj_entry.pack(side="left", padx=(0, 10))
        subj_entry.bind("<KeyRelease>", lambda e: self._filter_tree())

        # Destination Folder Row
        dest_row = ttk.Frame(ctrl_card, style="Card.TFrame")
        dest_row.pack(fill="x", pady=(0, 10))

        ttk.Label(dest_row, text="Save To:", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.dest_var = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        dest_entry = ttk.Entry(dest_row, textvariable=self.dest_var)
        dest_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn_browse = ttk.Button(dest_row, text="Browse...", style="Action.TButton", command=self._browse_dest)
        btn_browse.pack(side="left")

        # Action Buttons Row
        action_row = ttk.Frame(ctrl_card, style="Card.TFrame")
        action_row.pack(fill="x")

        self.btn_scan = ttk.Button(
            action_row,
            text="🔍 Scan Tamil Textbooks",
            style="Action.TButton",
            command=self._start_scan,
        )
        self.btn_scan.pack(side="left", padx=(0, 10))

        self.btn_download = ttk.Button(
            action_row,
            text="⬇ Download All Verified Books",
            style="Primary.TButton",
            command=self._start_download,
            state="disabled",
        )
        self.btn_download.pack(side="left", padx=(0, 10))

        self.btn_pause = ttk.Button(
            action_row,
            text="⏸ Pause",
            style="Action.TButton",
            command=self._toggle_pause,
            state="disabled",
        )
        self.btn_pause.pack(side="left", padx=(0, 10))

        self.btn_cancel = ttk.Button(
            action_row,
            text="⏹ Cancel",
            style="Cancel.TButton",
            command=self._cancel_download,
            state="disabled",
        )
        self.btn_cancel.pack(side="left")

        # Status counts label
        self.lbl_stats = ttk.Label(action_row, text="Ready. Click 'Scan Tamil Textbooks' to discover books.", style="Muted.TLabel")
        self.lbl_stats.pack(side="right")

        # 3. TABS CONTAINER
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=5)

        # TAB 1: Verified Tamil Medium Books
        tab_books = ttk.Frame(self.notebook)
        self.notebook.add(tab_books, text=" Verified Tamil Medium Books (0) ")

        cols = ("Class", "Edition", "Term", "Subject", "Tamil Title", "Status", "Download URL")
        self.tree_books = ttk.Treeview(tab_books, columns=cols, show="headings", selectmode="extended")
        self.tree_books.heading("Class", text="Class")
        self.tree_books.heading("Edition", text="Edition")
        self.tree_books.heading("Term", text="Term")
        self.tree_books.heading("Subject", text="Subject (English)")
        self.tree_books.heading("Tamil Title", text="Tamil Title")
        self.tree_books.heading("Status", text="Status")
        self.tree_books.heading("Download URL", text="Source URL")

        self.tree_books.column("Class", width=60, anchor="center")
        self.tree_books.column("Edition", width=130, anchor="w")
        self.tree_books.column("Term", width=80, anchor="center")
        self.tree_books.column("Subject", width=180, anchor="w")
        self.tree_books.column("Tamil Title", width=160, anchor="w")
        self.tree_books.column("Status", width=120, anchor="center")
        self.tree_books.column("Download URL", width=250, anchor="w")

        scroll_b_y = ttk.Scrollbar(tab_books, orient="vertical", command=self.tree_books.yview)
        scroll_b_x = ttk.Scrollbar(tab_books, orient="horizontal", command=self.tree_books.xview)
        self.tree_books.configure(yscrollcommand=scroll_b_y.set, xscrollcommand=scroll_b_x.set)

        self.tree_books.pack(side="left", fill="both", expand=True)
        scroll_b_y.pack(side="right", fill="y")
        scroll_b_x.pack(side="bottom", fill="x")

        # TAB 2: Real-time Download Log (Formatted)
        tab_logs = ttk.Frame(self.notebook)
        self.notebook.add(tab_logs, text=" Real-Time Download Log ")

        self.log_text = tk.Text(
            tab_logs,
            wrap="word",
            bg="#0f172a",
            fg="#38bdf8",
            insertbackground="white",
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        scroll_log = ttk.Scrollbar(tab_logs, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll_log.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll_log.pack(side="right", fill="y")

        # TAB 3: Ambiguous / Skipped Resources Review
        tab_amb = ttk.Frame(self.notebook)
        self.notebook.add(tab_amb, text=" Ambiguous / Skipped Resources (0) ")

        amb_cols = ("Class", "Edition", "Term", "Subject", "Status", "Reason / Notes", "URL")
        self.tree_amb = ttk.Treeview(tab_amb, columns=amb_cols, show="headings")
        self.tree_amb.heading("Class", text="Class")
        self.tree_amb.heading("Edition", text="Edition")
        self.tree_amb.heading("Term", text="Term")
        self.tree_amb.heading("Subject", text="Subject")
        self.tree_amb.heading("Status", text="Status")
        self.tree_amb.heading("Reason / Notes", text="Reason Skipped")
        self.tree_amb.heading("URL", text="URL")

        self.tree_amb.column("Class", width=60, anchor="center")
        self.tree_amb.column("Edition", width=120, anchor="w")
        self.tree_amb.column("Term", width=80, anchor="center")
        self.tree_amb.column("Subject", width=150, anchor="w")
        self.tree_amb.column("Status", width=140, anchor="center")
        self.tree_amb.column("Reason / Notes", width=260, anchor="w")
        self.tree_amb.column("URL", width=250, anchor="w")

        scroll_amb_y = ttk.Scrollbar(tab_amb, orient="vertical", command=self.tree_amb.yview)
        self.tree_amb.configure(yscrollcommand=scroll_amb_y.set)
        self.tree_amb.pack(side="left", fill="both", expand=True)
        scroll_amb_y.pack(side="right", fill="y")

        # 4. BOTTOM PROGRESS BAR & STATUS
        bottom_frame = ttk.Frame(self.root, style="Card.TFrame", padding=10)
        bottom_frame.pack(fill="x", padx=15, pady=(5, 15))

        # Overall progress
        self.progress_overall = ttk.Progressbar(bottom_frame, mode="determinate")
        self.progress_overall.pack(fill="x", pady=(0, 5))

        self.lbl_progress = ttk.Label(bottom_frame, text="Ready", style="Muted.TLabel")
        self.lbl_progress.pack(side="left")

    def _select_all_classes(self):
        for v in self.class_vars.values():
            v.set(True)

    def _clear_all_classes(self):
        for v in self.class_vars.values():
            v.set(False)

    def _browse_dest(self):
        chosen = filedialog.askdirectory(initialdir=self.dest_var.get())
        if chosen:
            self.dest_var.set(chosen)

    def log_message(self, msg: str):
        self.msg_queue.put(("log", msg))

    def _process_queue(self):
        """Processes async updates from worker threads in the main Tk thread."""
        try:
            while not self.msg_queue.empty():
                kind, data = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log_text.insert("end", data + "\n")
                    self.log_text.see("end")
                elif kind == "scan_done":
                    tamil_books, amb_books = data
                    self.discovered_books = tamil_books
                    self.ambiguous_books = amb_books
                    self._populate_trees()
                    self.btn_scan.config(state="normal")
                    if tamil_books:
                        self.btn_download.config(state="normal")
                    self.lbl_stats.config(text=f"Scan complete. {len(tamil_books)} Tamil Medium books ready.")
                elif kind == "file_progress":
                    res, cur_bytes, tot_bytes, pct = data
                    if pct >= 0:
                        self.lbl_progress.config(
                            text=f"Downloading {res.book_display_name}: {pct:.1f}% ({cur_bytes // 1024:,} KB / {tot_bytes // 1024:,} KB)"
                        )
                    else:
                        self.lbl_progress.config(
                            text=f"Downloading {res.book_display_name}: {cur_bytes // 1024:,} KB"
                        )
                elif kind == "file_complete":
                    res, path, status = data
                    self._update_book_status(res, status)
                elif kind == "overall_progress":
                    cur_idx, total_count = data
                    pct = (cur_idx / total_count) * 100.0 if total_count > 0 else 0
                    self.progress_overall["value"] = pct
                    self.lbl_progress.config(text=f"Progress: {cur_idx} of {total_count} files completed ({pct:.1f}%)")
                elif kind == "download_done":
                    results = data
                    self.btn_download.config(state="normal")
                    self.btn_scan.config(state="normal")
                    self.btn_pause.config(state="disabled", text="⏸ Pause")
                    self.btn_cancel.config(state="disabled")
                    self.lbl_stats.config(
                        text=f"Download Finished! Completed: {results['completed']}, Skipped/Failed: {results['failed']}"
                    )
                    messagebox.showinfo(
                        "Download Complete",
                        f"Tamil Medium Textbook Download Completed!\n\n"
                        f"Total: {results['total']}\n"
                        f"Completed: {results['completed']}\n"
                        f"Failed / Skipped: {results['failed']}\n\n"
                        f"Files saved in:\n{self.dest_var.get()}",
                    )
        except Exception as e:
            print("Queue processing error:", e)
        finally:
            self.root.after(100, self._process_queue)

    def _start_scan(self):
        selected_classes = [c for c, v in self.class_vars.items() if v.get()]
        if not selected_classes:
            messagebox.showwarning("No Class Selected", "Please select at least one class to scan.")
            return

        self.btn_scan.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.lbl_stats.config(text="Scanning Tamil Nadu textbooks website...")
        self.progress_overall["value"] = 0

        target_term = self.term_var.get()
        target_edition = self.edition_var.get()

        def scan_worker():
            scraper = TamilTextbookScraper(log_callback=self.log_message)
            all_tamil = []
            all_amb = []
            for c_num in selected_classes:
                self.log_message(f"Scanning Class {c_num}...")
                t_books, a_books = scraper.scrape_class(c_num, target_term=target_term, target_edition=target_edition)
                all_tamil.extend(t_books)
                all_amb.extend(a_books)

            self.msg_queue.put(("scan_done", (all_tamil, all_amb)))

        threading.Thread(target=scan_worker, daemon=True).start()

    def _populate_trees(self):
        # Clear existing
        for item in self.tree_books.get_children():
            self.tree_books.delete(item)
        for item in self.tree_amb.get_children():
            self.tree_amb.delete(item)

        # Update tab titles
        self.notebook.tab(0, text=f" Verified Tamil Medium Books ({len(self.discovered_books)}) ")
        self.notebook.tab(2, text=f" Ambiguous / Skipped Resources ({len(self.ambiguous_books)}) ")

        # Populate Tamil Books
        s_filter = self.subject_search_var.get().strip().lower()
        for b in self.discovered_books:
            if s_filter and (s_filter not in b.subject_display.lower() and s_filter not in b.subject_raw.lower()):
                continue
            self.tree_books.insert(
                "",
                "end",
                iid=b.download_url,
                values=(
                    b.class_num,
                    b.edition,
                    b.term,
                    b.subject_display,
                    b.tamil_title or b.subject_raw,
                    "Verified (Ready)",
                    b.download_url,
                ),
            )

        # Populate Ambiguous / Skipped Books
        for b in self.ambiguous_books:
            self.tree_amb.insert(
                "",
                "end",
                values=(
                    b.class_num,
                    b.edition,
                    b.term,
                    b.subject_display,
                    b.medium_status.value,
                    b.notes or "Medium uncertain",
                    b.download_url,
                ),
            )

    def _filter_tree(self):
        self._populate_trees()

    def _update_book_status(self, resource: TextbookResource, status: str):
        if self.tree_books.exists(resource.download_url):
            vals = list(self.tree_books.item(resource.download_url, "values"))
            vals[5] = status
            self.tree_books.item(resource.download_url, values=vals)

    def _start_download(self):
        if not self.discovered_books:
            messagebox.showinfo("No Books", "No verified Tamil Medium books to download.")
            return

        dest_dir = self.dest_var.get().strip()
        if not dest_dir:
            messagebox.showwarning("Destination Required", "Please specify a destination folder.")
            return

        # Prepare selected or all books
        selected_iids = self.tree_books.selection()
        if selected_iids:
            queue_books = [b for b in self.discovered_books if b.download_url in selected_iids]
            msg = f"Download {len(queue_books)} selected Tamil Medium books?"
        else:
            queue_books = list(self.discovered_books)
            msg = f"Download all {len(queue_books)} verified Tamil Medium books?"

        if not messagebox.askyesno("Confirm Tamil Medium Download", msg):
            return

        self.btn_download.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸ Pause")
        self.btn_cancel.config(state="normal")
        self.progress_overall["value"] = 0

        self.downloader = TamilTextbookDownloader(
            download_dir=dest_dir,
            on_log=self.log_message,
            on_file_progress=lambda r, c, t, p: self.msg_queue.put(("file_progress", (r, c, t, p))),
            on_overall_progress=lambda c, t: self.msg_queue.put(("overall_progress", (c, t))),
            on_file_complete=lambda r, p, s: self.msg_queue.put(("file_complete", (r, p, s))),
        )

        target_term = self.term_var.get()
        target_edition = self.edition_var.get()

        def download_worker():
            results = self.downloader.download_queue(
                resources=queue_books,
                expected_term=target_term,
                expected_edition=target_edition,
            )
            self.msg_queue.put(("download_done", results))

        self.download_thread = threading.Thread(target=download_worker, daemon=True)
        self.download_thread.start()

    def _toggle_pause(self):
        if not self.downloader:
            return
        if self.downloader.is_paused:
            self.downloader.resume()
            self.btn_pause.config(text="⏸ Pause")
        else:
            self.downloader.pause()
            self.btn_pause.config(text="▶ Resume")

    def _cancel_download(self):
        if self.downloader:
            if messagebox.askyesno("Cancel Download", "Are you sure you want to stop the download queue?"):
                self.downloader.cancel()
                self.btn_cancel.config(state="disabled")
                self.btn_pause.config(state="disabled")


def launch_gui():
    root = tk.Tk()
    app = TamilMediumApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
