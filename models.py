"""
Data models for the Tamil Medium School Textbooks Auto-Downloader.
Ensures context tracking and strict medium categorization.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class MediumStatus(Enum):
    TAMIL_CONFIRMED = "TAMIL_CONFIRMED"
    ENGLISH_REJECTED = "ENGLISH_REJECTED"
    AMBIGUOUS_MEDIUM = "AMBIGUOUS_MEDIUM"


@dataclass
class MediumContext:
    """
    Context tracked during DOM traversal.
    Every discovered resource inherits this context.
    """
    class_num: int
    edition: str
    medium: str  # "Tamil", "English", or "Ambiguous"
    term: str    # "Term 1", "Term 2", "Term 3", or "Full Book"
    section_heading: str = ""
    table_header: str = ""
    column_header: str = ""

    def is_explicitly_tamil(self) -> bool:
        return self.medium.strip().lower() == "tamil"

    def is_explicitly_english(self) -> bool:
        return self.medium.strip().lower() == "english"


@dataclass
class TextbookResource:
    """
    Represents an extracted textbook candidate from the website.
    """
    class_num: int
    edition: str
    term: str
    subject_raw: str
    subject_display: str
    tamil_title: str
    download_url: str
    source_page: str
    context: MediumContext
    medium_status: MediumStatus = MediumStatus.AMBIGUOUS_MEDIUM
    notes: str = ""

    @property
    def book_display_name(self) -> str:
        """Standard human-readable book name for UI and logs."""
        term_str = f" - {self.term}" if self.term and self.term != "Full Book" else ""
        return f"{self.class_num}th Standard {self.subject_display}{term_str}"

    def format_log_block(self, status: str = "Discovered") -> str:
        """Format as requested by the user:
        [INFO]
        Class: 8
        Medium: Tamil
        Term: 1
        Subject: Mathematics
        Book: 8th Standard Mathematics
        Status: Downloading
        """
        # Clean term format (e.g., 'Term 1' -> '1', 'Full Book' -> 'Full Book')
        term_clean = self.term.replace("Term ", "").strip() if "Term" in self.term else self.term
        return (
            f"[INFO]\n"
            f"Class: {self.class_num}\n"
            f"Medium: Tamil\n"
            f"Term: {term_clean}\n"
            f"Subject: {self.subject_display}\n"
            f"Book: {self.book_display_name}\n"
            f"URL: {self.download_url}\n"
            f"Status: {status}\n"
        )


@dataclass
class ValidationResult:
    """
    Result of the 6-point pre-save validation:
    1. Correct class?
    2. Correct edition?
    3. Tamil Medium?
    4. Correct term?
    5. Correct subject?
    6. Valid PDF?
    """
    is_valid: bool
    step_results: Dict[str, bool] = field(default_factory=dict)
    error_message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        if self.is_valid:
            return "All 6 validation checks passed successfully."
        failed = [k for k, v in self.step_results.items() if not v]
        return f"Validation failed on: {', '.join(failed)}. Error: {self.error_message}"
