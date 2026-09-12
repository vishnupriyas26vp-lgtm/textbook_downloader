"""
Validation module enforcing strict Tamil Medium constraints and 6-point pre-save checks.
"""

import logging
from typing import Optional, Callable
from models import TextbookResource, MediumStatus, ValidationResult
from config import TAMIL_MEDIUM_LABELS, NON_TAMIL_MEDIUM_LABELS

logger = logging.getLogger("TamilMediumValidator")


def is_tamil_medium(resource: TextbookResource, log_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    Strict medium filter: Returns True ONLY when the resource can be confidently
    associated with Tamil Medium.
    
    If ambiguous or cannot be confirmed:
    Marks AMBIGUOUS_MEDIUM, logs safety warning, and returns False.
    """
    ctx = resource.context

    # Normalization helper
    def normalize(text: str) -> str:
        return (text or "").strip().lower()

    medium_normalized = normalize(ctx.medium)
    section_normalized = normalize(ctx.section_heading)
    table_normalized = normalize(ctx.table_header)
    column_normalized = normalize(ctx.column_header)
    url_normalized = normalize(resource.download_url)

    combined_context = f"{section_normalized} {table_normalized} {column_normalized}"

    # 1. HARD REJECTION: Explicit English or Other Medium Context
    if medium_normalized == "english":
        resource.medium_status = MediumStatus.ENGLISH_REJECTED
        resource.notes = "Rejected: Located under explicit English Medium context."
        return False

    for non_tamil in NON_TAMIL_MEDIUM_LABELS:
        if non_tamil in medium_normalized:
            resource.medium_status = MediumStatus.ENGLISH_REJECTED
            resource.notes = f"Rejected: Non-Tamil medium marker '{non_tamil}' in context."
            return False

    # Check for direct English Medium markers in URL (e.g., _EM_Text, English_Medium)
    # Exception: The language subject itself may be called English/Tamil within a Tamil Medium table
    if "_em_" in url_normalized or "_em.pdf" in url_normalized or "english_medium" in url_normalized or "english%20medium" in url_normalized:
        resource.medium_status = MediumStatus.ENGLISH_REJECTED
        resource.notes = "Rejected: File URL explicitly contains English Medium marker (_EM_)."
        return False

    # 2. POSITIVE IDENTIFICATION: Confirmed Tamil Medium
    is_confirmed_tamil = False

    # Check context medium string
    if medium_normalized == "tamil":
        is_confirmed_tamil = True

    # Check column header (e.g. table with columns: 'Subject', 'Tamil Medium', 'English Medium')
    if any(label in column_normalized for label in ["tamil medium", "tamil", "தமிழ் வழி", "தமிழ்"]):
        if not any(non_tamil in column_normalized for non_tamil in ["english medium", "english"]):
            is_confirmed_tamil = True

    # Check table or section headings
    if any(label in table_normalized for label in TAMIL_MEDIUM_LABELS):
        # Ensure it's not "English Medium"
        if not ("english medium" in table_normalized or "english" in table_normalized and "tamil" not in table_normalized):
            is_confirmed_tamil = True

    if any(label in section_normalized for label in TAMIL_MEDIUM_LABELS):
        if not ("english medium" in section_normalized):
            is_confirmed_tamil = True

    # Check URL markers (e.g., _TM_Text.pdf, Tamil_Medium)
    if "_tm_" in url_normalized or "_tm.pdf" in url_normalized or "tamil%20medium" in url_normalized or "tamil_medium" in url_normalized:
        is_confirmed_tamil = True

    # Check Tamil Unicode in raw subject text (e.g. கணிதம், அறிவியல், தமிழ்)
    has_tamil_unicode_subject = any(ord(char) >= 0x0B80 and ord(char) <= 0x0BFF for char in resource.subject_raw)
    if has_tamil_unicode_subject and not (medium_normalized == "english" or "english medium" in combined_context):
        is_confirmed_tamil = True

    # 3. VERDICT
    if is_confirmed_tamil:
        # Double check no English Medium overrides
        if "english medium" in combined_context and not any(tm in column_normalized for tm in ["tamil medium", "தமிழ்"]):
            # Ambiguous conflict
            resource.medium_status = MediumStatus.AMBIGUOUS_MEDIUM
            resource.notes = "Skipped: Conflicting English and Tamil markers in context."
            log_msg = (
                "[TAMIL MEDIUM CHECK]\n"
                "Unable to confidently determine medium.\n"
                "Resource skipped for safety.\n"
            )
            logger.warning(log_msg)
            if log_callback:
                log_callback(log_msg)
            return False

        resource.medium_status = MediumStatus.TAMIL_CONFIRMED
        return True

    # 4. AMBIGUOUS / UNCERTAIN
    resource.medium_status = MediumStatus.AMBIGUOUS_MEDIUM
    resource.notes = "Skipped: Unable to confidently associate with Tamil Medium."
    log_msg = (
        "[TAMIL MEDIUM CHECK]\n"
        "Unable to confidently determine medium.\n"
        "Resource skipped for safety.\n"
    )
    logger.warning(log_msg)
    if log_callback:
        log_callback(log_msg)
    return False


def validate_final(
    resource: TextbookResource,
    downloaded_header: bytes,
    expected_class: Optional[int] = None,
    expected_edition: Optional[str] = None,
    expected_term: Optional[str] = None,
    expected_subject: Optional[str] = None,
) -> ValidationResult:
    """
    Perform final validation before saving a PDF to disk:
    1. Correct class?
    2. Correct edition?
    3. Tamil Medium?
    4. Correct term?
    5. Correct subject?
    6. Valid PDF?
    """
    checks = {
        "class": False,
        "edition": False,
        "tamil_medium": False,
        "term": False,
        "subject": False,
        "valid_pdf": False,
    }

    # 1. Correct class check
    if expected_class is not None:
        checks["class"] = resource.class_num == expected_class
    else:
        checks["class"] = resource.class_num in [8, 9, 10, 11, 12]

    # 2. Correct edition check
    if expected_edition is not None and expected_edition != "All Editions":
        checks["edition"] = expected_edition.lower() in resource.edition.lower()
    else:
        checks["edition"] = bool(resource.edition and resource.edition.strip())

    # 3. Tamil Medium check (Strict!)
    checks["tamil_medium"] = is_tamil_medium(resource)

    # 4. Correct term check
    if expected_term is not None and expected_term != "All Terms":
        clean_exp = expected_term.replace("Term ", "").strip().lower()
        clean_res = resource.term.replace("Term ", "").strip().lower()
        checks["term"] = (clean_exp in clean_res) or (resource.term == "Full Book")
    else:
        checks["term"] = bool(resource.term and resource.term.strip())

    # 5. Correct subject check
    if expected_subject is not None and expected_subject.strip():
        checks["subject"] = (
            expected_subject.lower() in resource.subject_display.lower()
            or expected_subject in resource.subject_raw
        )
    else:
        checks["subject"] = bool(resource.subject_display and resource.subject_display.strip())

    # 6. Valid PDF magic bytes check (%PDF-)
    checks["valid_pdf"] = bool(downloaded_header and downloaded_header.startswith(b"%PDF-"))

    all_passed = all(checks.values())
    error_msg = ""
    if not all_passed:
        failed_steps = [name for name, passed in checks.items() if not passed]
        error_msg = f"Failed validation steps: {', '.join(failed_steps)}"

    return ValidationResult(
        is_valid=all_passed,
        step_results=checks,
        error_message=error_msg,
        details={
            "resource": resource.book_display_name,
            "medium_status": resource.medium_status.value,
            "header_bytes": downloaded_header[:16] if downloaded_header else b"",
        },
    )
