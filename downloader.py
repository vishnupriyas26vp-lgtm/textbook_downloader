"""
Download manager for Tamil Medium School Textbooks.
Supports streaming, Google Drive links, PDF verification (%PDF-),
and strict 6-point pre-save validation.
"""

import os
import re
import time
import urllib.request
import urllib.parse
import http.cookiejar
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from models import TextbookResource, ValidationResult
from validator import validate_final
from config import DEFAULT_HEADERS, DEFAULT_DOWNLOAD_DIR

logger = logging.getLogger("TamilMediumDownloader")


class TamilTextbookDownloader:
    """
    Downloads Tamil Medium textbooks with real-time progress, cancellation,
    and 6-point pre-save verification.
    """

    def __init__(
        self,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        on_log: Optional[Callable[[str], None]] = None,
        on_file_progress: Optional[Callable[[TextbookResource, int, int, float], None]] = None,
        on_overall_progress: Optional[Callable[[int, int], None]] = None,
        on_file_complete: Optional[Callable[[TextbookResource, str, str], None]] = None,
    ):
        self.download_dir = Path(download_dir)
        self.on_log = on_log
        self.on_file_progress = on_file_progress
        self.on_overall_progress = on_overall_progress
        self.on_file_complete = on_file_complete

        self.is_paused = False
        self.is_cancelled = False

        # Cookie jar for Google Drive confirm tokens
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))

    def log(self, message: str):
        logger.info(message)
        if self.on_log:
            self.on_log(message)

    def pause(self):
        self.is_paused = True
        self.log("[CONTROL] Downloads paused.")

    def resume(self):
        self.is_paused = False
        self.log("[CONTROL] Downloads resumed.")

    def cancel(self):
        self.is_cancelled = True
        self.log("[CONTROL] Download queue cancelled.")

    def resolve_download_url(self, raw_url: str) -> str:
        """
        Converts Google Drive view/open links to direct download links.
        """
        # Google Drive pattern
        gdrive_id = None
        id_match = re.search(r"id=([a-zA-Z0-9_-]+)", raw_url)
        if id_match:
            gdrive_id = id_match.group(1)
        else:
            file_match = re.search(r"/d/([a-zA-Z0-9_-]+)", raw_url)
            if file_match:
                gdrive_id = file_match.group(1)

        if gdrive_id:
            return f"https://drive.google.com/uc?export=download&id={gdrive_id}"

        return raw_url

    def get_destination_path(self, resource: TextbookResource) -> Path:
        """
        Creates hierarchical target directory:
        downloads/Tamil_Medium/Class_<N>/<Term_or_Edition>/<Subject>.pdf
        """
        # Safe directory names
        class_folder = f"Class_{resource.class_num}"
        term_clean = resource.term.replace(" ", "_") if resource.term else "Full_Book"
        edition_clean = re.sub(r"[^\w\s-]", "", resource.edition).strip().replace(" ", "_")
        sub_folder = f"{edition_clean}_{term_clean}"

        target_dir = self.download_dir / class_folder / sub_folder
        target_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_subject = re.sub(r'[\\/*?:"<>|]', "", resource.subject_display).strip()
        filename = f"{resource.class_num}th_Tamil_Medium_{safe_subject}_{term_clean}.pdf"
        return target_dir / filename

    def download_resource(
        self,
        resource: TextbookResource,
        expected_class: Optional[int] = None,
        expected_edition: Optional[str] = None,
        expected_term: Optional[str] = None,
        expected_subject: Optional[str] = None,
    ) -> bool:
        """
        Downloads a single Tamil Medium textbook.
        Performs 6-point pre-save validation before committing to disk.
        """
        if self.is_cancelled:
            return False

        # Output required start log format
        self.log(resource.format_log_block(status="Downloading"))

        dest_file = self.get_destination_path(resource)
        temp_file = dest_file.with_suffix(".tmp")

        direct_url = self.resolve_download_url(resource.download_url)

        try:
            req = urllib.request.Request(direct_url, headers=DEFAULT_HEADERS)
            resp = self.opener.open(req, timeout=30)

            # Handle Google Drive large file confirmation page
            content_type = resp.headers.get("Content-Type", "").lower()
            resp_body = b""
            if "text/html" in content_type:
                html_text = resp.read().decode("utf-8", errors="ignore")
                # Check for confirm token
                confirm_token = None
                token_match = re.search(r"confirm=([0-9A-Za-z_]+)", html_text)
                if token_match:
                    confirm_token = token_match.group(1)
                elif "confirm=" in html_text:
                    token_match2 = re.search(r'name="confirm"\s+value="([^"]+)"', html_text)
                    if token_match2:
                        confirm_token = token_match2.group(1)

                if confirm_token:
                    confirm_url = f"{direct_url}&confirm={confirm_token}"
                    req2 = urllib.request.Request(confirm_url, headers=DEFAULT_HEADERS)
                    resp = self.opener.open(req2, timeout=30)
                else:
                    # Not a downloadable stream
                    self.log(f"[ERROR] Could not obtain direct download stream from: {direct_url}")
                    self.log(resource.format_log_block(status="Failed (HTML received instead of PDF)"))
                    if self.on_file_complete:
                        self.on_file_complete(resource, "", "Failed")
                    return False

            # Read first chunk to inspect magic bytes (%PDF-)
            first_chunk = resp.read(2048)

            # FINAL 6-POINT VALIDATION CHECK
            val_result = validate_final(
                resource=resource,
                downloaded_header=first_chunk,
                expected_class=expected_class,
                expected_edition=expected_edition,
                expected_term=expected_term,
                expected_subject=expected_subject,
            )

            if not val_result.is_valid:
                self.log(f"[VALIDATION FAILED] {val_result.summary()}")
                self.log(resource.format_log_block(status=f"Skipped ({val_result.error_message})"))
                if self.on_file_complete:
                    self.on_file_complete(resource, "", f"Skipped: {val_result.error_message}")
                return False

            # Content length if provided
            content_length = resp.headers.get("Content-Length")
            total_size = int(content_length) if content_length and content_length.isdigit() else 0
            downloaded_bytes = len(first_chunk)

            # Write stream to temporary file
            with open(temp_file, "wb") as f:
                f.write(first_chunk)

                chunk_size = 64 * 1024  # 64 KB chunks
                while True:
                    while self.is_paused and not self.is_cancelled:
                        time.sleep(0.5)

                    if self.is_cancelled:
                        f.close()
                        if temp_file.exists():
                            temp_file.unlink()
                        self.log(resource.format_log_block(status="Cancelled"))
                        return False

                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded_bytes += len(chunk)

                    if total_size > 0:
                        pct = (downloaded_bytes / total_size) * 100.0
                    else:
                        pct = -1.0

                    if self.on_file_progress:
                        self.on_file_progress(resource, downloaded_bytes, total_size, pct)

            # Replace or atomic rename
            if dest_file.exists():
                dest_file.unlink()
            temp_file.rename(dest_file)

            self.log(resource.format_log_block(status="Completed"))
            self.log(f"[SAVED] File saved successfully: {dest_file} ({downloaded_bytes:,} bytes)")

            if self.on_file_complete:
                self.on_file_complete(resource, str(dest_file), "Completed")

            return True

        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            self.log(f"[ERROR] Download error for {resource.book_display_name}: {e}")
            self.log(resource.format_log_block(status=f"Failed: {e}"))
            if self.on_file_complete:
                self.on_file_complete(resource, "", f"Failed: {e}")
            return False

    def download_queue(
        self,
        resources: list[TextbookResource],
        expected_class: Optional[int] = None,
        expected_edition: Optional[str] = None,
        expected_term: Optional[str] = None,
        expected_subject: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes download on a list of verified Tamil Medium resources.
        """
        self.is_cancelled = False
        self.is_paused = False

        total_files = len(resources)
        completed_count = 0
        failed_count = 0

        self.log(f"\n[DOWNLOAD QUEUE] Starting download of {total_files} Tamil Medium books...\n")

        for idx, res in enumerate(resources):
            if self.is_cancelled:
                self.log("[DOWNLOAD QUEUE] Process cancelled by user.")
                break

            success = self.download_resource(
                resource=res,
                expected_class=expected_class,
                expected_edition=expected_edition,
                expected_term=expected_term,
                expected_subject=expected_subject,
            )

            if success:
                completed_count += 1
            else:
                failed_count += 1

            if self.on_overall_progress:
                self.on_overall_progress(idx + 1, total_files)

        return {
            "total": total_files,
            "completed": completed_count,
            "failed": failed_count,
            "cancelled": self.is_cancelled,
        }
