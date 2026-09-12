"""
DOM Scraper for Tamil Nadu School Textbooks with strict Medium Context Tracking.
Hierarchy: CLASS -> EDITION -> TAMIL MEDIUM -> TERM -> SUBJECT -> PDF
"""

import re
import html
import urllib.request
import logging
from typing import List, Dict, Tuple, Optional, Callable
from models import TextbookResource, MediumContext, MediumStatus
from validator import is_tamil_medium
from config import (
    CLASS_URLS,
    DEFAULT_HEADERS,
    TAMIL_SUBJECT_TRANSLATIONS,
    TAMIL_MEDIUM_LABELS,
    NON_TAMIL_MEDIUM_LABELS,
)

logger = logging.getLogger("TamilMediumScraper")


class TamilTextbookScraper:
    """
    Scrapes textbooks while strictly enforcing Tamil Medium selection.
    Tracks state context and ensures resources inherit the verified context.
    """

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log_callback = log_callback

    def log(self, message: str):
        logger.info(message)
        if self.log_callback:
            self.log_callback(message)

    def fetch_page_html(self, url: str) -> str:
        """Fetch page content with standard browser headers."""
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_data = response.read()
            return raw_data.decode("utf-8", errors="ignore")

    def scrape_class(
        self,
        class_num: int,
        target_term: Optional[str] = None,
        target_edition: Optional[str] = None,
    ) -> Tuple[List[TextbookResource], List[TextbookResource]]:
        """
        Scrape books for a specific class (8, 9, 10, 11, 12).
        Returns:
            (tamil_confirmed_resources, ambiguous_or_skipped_resources)
        """
        if class_num not in CLASS_URLS:
            self.log(f"[ERROR] Class {class_num} is not supported.")
            return [], []

        url = CLASS_URLS[class_num]
        self.log(f"Fetching Class {class_num} page from {url}...")
        try:
            page_html = self.fetch_page_html(url)
        except Exception as e:
            self.log(f"[ERROR] Failed to fetch page for Class {class_num}: {e}")
            return [], []

        return self.parse_class_page(class_num, page_html, url, target_term, target_edition)

    def parse_class_page(
        self,
        class_num: int,
        page_html: str,
        source_url: str,
        target_term: Optional[str] = None,
        target_edition: Optional[str] = None,
    ) -> Tuple[List[TextbookResource], List[TextbookResource]]:
        """
        Parses the class HTML page by inspecting DOM tables, section headings,
        table headers, and rows with context tracking.
        """
        tamil_resources: List[TextbookResource] = []
        ambiguous_resources: List[TextbookResource] = []

        # Split HTML by <table> tags while tracking preceding content for heading context
        table_splits = re.split(r"<table[^>]*>", page_html, flags=re.I)
        if len(table_splits) <= 1:
            self.log(f"[WARNING] No tables found on Class {class_num} page.")
            return [], []

        # Track rolling section headings
        current_section_heading = ""
        current_edition = "Latest Edition (2024-25)"

        for idx in range(1, len(table_splits)):
            preceding_content = table_splits[idx - 1]
            table_body = table_splits[idx].split("</table>")[0]

            # 1. Update Context from Preceding Headings (h1 - h6, strong, b)
            heading_matches = re.findall(r"<(h[1-6]|strong|b)[^>]*>(.*?)</\1>", preceding_content, re.I | re.S)
            if heading_matches:
                # Find the most meaningful recent heading
                for tag, text in reversed(heading_matches[-5:]):
                    clean_h = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
                    if clean_h and len(clean_h) > 2:
                        current_section_heading = clean_h
                        # Detect edition info if present in heading
                        if "2026" in clean_h or "2027" in clean_h:
                            current_edition = "2026-27 Edition"
                        elif "2024" in clean_h or "2025" in clean_h:
                            current_edition = "2024-25 Edition"
                        elif "2022" in clean_h or "2023" in clean_h:
                            current_edition = "2022-23 Edition"
                        elif "2019" in clean_h:
                            current_edition = "2019 Edition"
                        elif "old" in clean_h.lower():
                            current_edition = "Old Edition"
                        break

            # 2. Extract Table Headers (th tags)
            raw_ths = re.findall(r"<th[^>]*>(.*?)</th>", table_body, re.I | re.S)
            table_headers = [html.unescape(re.sub(r"<[^>]+>", "", th)).strip() for th in raw_ths]
            table_header_str = " | ".join(table_headers)

            # Detect edition from table headers if present
            if "2024" in table_header_str or "2025" in table_header_str:
                current_edition = "2024-25 Edition"
            elif "2022" in table_header_str or "2023" in table_header_str:
                current_edition = "2022-23 Edition"
            elif "2019" in table_header_str:
                current_edition = "2019 Edition"
            elif "old" in table_header_str.lower():
                current_edition = "Old Edition"

            # 3. Detect Term Context (Prioritize specific table header over broad section heading)
            term = "Full Book"
            # Check table header first
            th_lower = f" {table_header_str.lower()} "
            if any(k in th_lower for k in ["term 3", "term-3", "term iii", "term-iii"]):
                term = "Term 3"
            elif any(k in th_lower for k in ["term 2", "term-2", "term ii", "term-ii"]):
                term = "Term 2"
            elif any(k in th_lower for k in ["term 1", "term-1", "term i ", "term i|", "term-i"]):
                term = "Term 1"
            else:
                # Fallback to section heading
                sec_lower = f" {current_section_heading.lower()} "
                if any(k in sec_lower for k in ["term 3", "term-3", "term iii", "term-iii"]):
                    term = "Term 3"
                elif any(k in sec_lower for k in ["term 2", "term-2", "term ii", "term-ii"]):
                    term = "Term 2"
                elif any(k in sec_lower for k in ["term 1", "term-1", "term i ", "term-i"]):
                    term = "Term 1"

            # 4. Detect Table-level Medium Context
            table_medium = "Ambiguous"
            section_lower = current_section_heading.lower()
            table_h_lower = table_header_str.lower()

            # Check for English Medium rejection at table level
            is_english_table = (
                "english medium" in table_h_lower
                or (section_lower == "english medium")
                or ("english medium" in section_lower and "tamil medium" not in section_lower)
            )

            is_tamil_table = (
                "tamil medium" in table_h_lower
                or (section_lower == "tamil medium")
                or ("tamil medium" in section_lower and "english medium" not in section_lower)
                or any(t in table_h_lower for t in ["தமிழ் வழி", "தமிழ் வழிக்கல்வி"])
            )

            # Multi-column check: tables where column headers are ['Subjects', 'Tamil Medium', 'English Medium']
            is_multi_medium_columns = (
                any("tamil" in h.lower() for h in table_headers)
                and any("english" in h.lower() for h in table_headers)
            )

            if is_english_table and not is_tamil_table and not is_multi_medium_columns:
                table_medium = "English"
            elif is_tamil_table and not is_english_table and not is_multi_medium_columns:
                table_medium = "Tamil"

            # 5. Extract Table Rows (tr tags)
            raw_trs = re.findall(r"<tr[^>]*>(.*?)</tr>", table_body, re.I | re.S)
            for tr in raw_trs:
                # Extract td elements
                raw_tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.I | re.S)
                if not raw_tds:
                    continue

                clean_tds = [html.unescape(re.sub(r"<[^>]+>", "", td)).strip() for td in raw_tds]

                # Case A: Multi-column table (e.g. Col 0: Subject, Col 1: Tamil Medium, Col 2: English Medium)
                if is_multi_medium_columns:
                    subject_name = clean_tds[0]
                    # Find which column index is Tamil Medium
                    tamil_col_idx = None
                    for c_idx, th_title in enumerate(table_headers):
                        th_l = th_title.lower()
                        if ("tamil medium" in th_l or th_l == "tamil" or "தமிழ்" in th_l) and "english" not in th_l:
                            tamil_col_idx = c_idx
                            break

                    if tamil_col_idx is not None and tamil_col_idx < len(raw_tds):
                        links = re.findall(r'href=["\']([^"\']+)["\']', raw_tds[tamil_col_idx], re.I)
                        if links:
                            link = links[0]
                            # Only PDF links (avoid EPUB or unrelated anchor links)
                            ctx = MediumContext(
                                class_num=class_num,
                                edition=current_edition,
                                medium="Tamil",
                                term=term,
                                section_heading=current_section_heading,
                                table_header=table_header_str,
                                column_header=table_headers[tamil_col_idx] if tamil_col_idx < len(table_headers) else "Tamil Medium",
                            )
                            res = self._create_resource(class_num, current_edition, term, subject_name, link, source_url, ctx)
                            self._categorize_resource(res, tamil_resources, ambiguous_resources, target_term, target_edition)
                    continue

                # Case B: Standard table (Col 0: Subject Name, Col 1: PDF Download Link, Col 2: EPUB Download Link)
                subject_name = clean_tds[0]
                if not subject_name or subject_name.lower() in ["subject name", "subjects", "language subjects", "general subjects", "vocational subjects", "practical manual"]:
                    continue

                # Look for download link in Col 1 (PDF)
                pdf_td = raw_tds[1] if len(raw_tds) > 1 else tr
                # Extract href
                links = re.findall(r'href=["\']([^"\']+)["\']', pdf_td, re.I)
                if not links and len(raw_tds) > 1:
                    # check all tds for link
                    links = re.findall(r'href=["\']([^"\']+)["\']', tr, re.I)

                if not links:
                    continue

                # If there are multiple links, prefer the first link (PDF) rather than EPUB (second column)
                download_link = links[0]

                # If the table is explicitly English Medium, DO NOT ADD TO TAMIL QUEUE
                if table_medium == "English":
                    # Strictly skip and never allow into queue
                    continue

                # Build context
                ctx = MediumContext(
                    class_num=class_num,
                    edition=current_edition,
                    medium=table_medium,
                    term=term,
                    section_heading=current_section_heading,
                    table_header=table_header_str,
                    column_header=table_headers[1] if len(table_headers) > 1 else "",
                )

                res = self._create_resource(class_num, current_edition, term, subject_name, download_link, source_url, ctx)
                self._categorize_resource(res, tamil_resources, ambiguous_resources, target_term, target_edition)

        return tamil_resources, ambiguous_resources

    def _create_resource(
        self,
        class_num: int,
        edition: str,
        term: str,
        subject_raw: str,
        download_url: str,
        source_url: str,
        ctx: MediumContext,
    ) -> TextbookResource:
        """Normalizes and translates subject names while preserving Tamil Unicode."""
        clean_raw = subject_raw.strip()
        # Clean trailing asterisks or annotations
        clean_name = re.sub(r"[\*\(\)\d\.\-]+$", "", clean_raw).strip()

        # Find English display name
        display_name = TAMIL_SUBJECT_TRANSLATIONS.get(clean_name, clean_name)
        tamil_title = clean_name if any(ord(c) >= 0x0B80 and ord(c) <= 0x0BFF for c in clean_name) else ""

        return TextbookResource(
            class_num=class_num,
            edition=edition,
            term=term,
            subject_raw=clean_raw,
            subject_display=display_name,
            tamil_title=tamil_title,
            download_url=download_url,
            source_page=source_url,
            context=ctx,
        )

    def _categorize_resource(
        self,
        resource: TextbookResource,
        tamil_queue: List[TextbookResource],
        ambiguous_queue: List[TextbookResource],
        target_term: Optional[str] = None,
        target_edition: Optional[str] = None,
    ):
        """Validates medium strictly and places resource in appropriate queue."""
        # Check target term filter
        if target_term and target_term != "All Terms":
            clean_tgt = target_term.replace("Term ", "").strip().lower()
            clean_res = resource.term.replace("Term ", "").strip().lower()
            if clean_tgt not in clean_res and resource.term != "Full Book":
                return

        # Check target edition filter
        if target_edition and target_edition != "All Editions":
            if target_edition.lower() not in resource.edition.lower():
                return

        # STRICT MEDIUM VALIDATION
        if is_tamil_medium(resource, log_callback=self.log):
            # Avoid duplicate URLs in the queue
            if not any(r.download_url == resource.download_url for r in tamil_queue):
                tamil_queue.append(resource)
        else:
            if resource.medium_status == MediumStatus.AMBIGUOUS_MEDIUM:
                if not any(r.download_url == resource.download_url for r in ambiguous_queue):
                    ambiguous_queue.append(resource)
            # If ENGLISH_REJECTED: do not add to either queue
