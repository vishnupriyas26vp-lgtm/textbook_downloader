"""
Unit and Integration tests for Tamil Medium School Textbooks Auto-Downloader.
Ensures strict Tamil Medium enforcement, zero English leakage, and 6-point validation.
"""

import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from models import MediumContext, TextbookResource, MediumStatus
from validator import is_tamil_medium, validate_final
from scraper import TamilTextbookScraper


class TestTamilMediumValidator(unittest.TestCase):

    def test_tamil_medium_confirmed_by_context(self):
        ctx = MediumContext(
            class_num=8,
            edition="2024-25 Edition",
            medium="Tamil",
            term="Term 1",
            section_heading="8th Tamil Medium Books",
            table_header="8th Tamil Medium Books - Term I",
            column_header="Download Link",
        )
        res = TextbookResource(
            class_num=8,
            edition="2024-25 Edition",
            term="Term 1",
            subject_raw="கணிதம்",
            subject_display="Mathematics",
            tamil_title="கணிதம்",
            download_url="https://example.com/8th_maths_tm.pdf",
            source_page="https://example.com",
            context=ctx,
        )
        self.assertTrue(is_tamil_medium(res))
        self.assertEqual(res.medium_status, MediumStatus.TAMIL_CONFIRMED)

    def test_english_medium_strictly_rejected(self):
        # Scenario: Under English Medium table
        ctx = MediumContext(
            class_num=8,
            edition="2024-25 Edition",
            medium="English",
            term="Term 1",
            section_heading="8th English Medium Books",
            table_header="8th English Medium Books - Term I",
            column_header="Download Link",
        )
        res = TextbookResource(
            class_num=8,
            edition="2024-25 Edition",
            term="Term 1",
            subject_raw="Mathematics",
            subject_display="Mathematics",
            tamil_title="",
            download_url="https://example.com/8th_maths_em.pdf",
            source_page="https://example.com",
            context=ctx,
        )
        self.assertFalse(is_tamil_medium(res))
        self.assertEqual(res.medium_status, MediumStatus.ENGLISH_REJECTED)

    def test_english_url_marker_strictly_rejected(self):
        # URL has _EM_ marker
        ctx = MediumContext(
            class_num=9,
            edition="2024-25 Edition",
            medium="Tamil",  # Even if mislabeled as Tamil, URL marker rejects
            term="Full Book",
            section_heading="",
            table_header="",
            column_header="",
        )
        res = TextbookResource(
            class_num=9,
            edition="2024-25 Edition",
            term="Full Book",
            subject_raw="Science",
            subject_display="Science",
            tamil_title="",
            download_url="https://example.com/9th_Science_EM_Text.pdf",
            source_page="https://example.com",
            context=ctx,
        )
        self.assertFalse(is_tamil_medium(res))
        self.assertEqual(res.medium_status, MediumStatus.ENGLISH_REJECTED)

    def test_ambiguous_medium_skipped_and_logged(self):
        logged_messages = []

        def capture_log(msg):
            logged_messages.append(msg)

        ctx = MediumContext(
            class_num=10,
            edition="2024-25 Edition",
            medium="Unknown",
            term="Full Book",
            section_heading="General Downloads",
            table_header="Book Links",
            column_header="Link",
        )
        res = TextbookResource(
            class_num=10,
            edition="2024-25 Edition",
            term="Full Book",
            subject_raw="Social",
            subject_display="Social",
            tamil_title="",
            download_url="https://example.com/book10.pdf",
            source_page="https://example.com",
            context=ctx,
        )

        result = is_tamil_medium(res, log_callback=capture_log)
        self.assertFalse(result)
        self.assertEqual(res.medium_status, MediumStatus.AMBIGUOUS_MEDIUM)
        # Check required log text
        combined_logs = "\n".join(logged_messages)
        self.assertIn("[TAMIL MEDIUM CHECK]", combined_logs)
        self.assertIn("Unable to confidently determine medium.", combined_logs)
        self.assertIn("Resource skipped for safety.", combined_logs)

    def test_final_validation_all_6_checks(self):
        ctx = MediumContext(
            class_num=8,
            edition="2019 Edition",
            medium="Tamil",
            term="Term 1",
            table_header="8th Tamil Medium Books - Term I",
        )
        res = TextbookResource(
            class_num=8,
            edition="2019 Edition",
            term="Term 1",
            subject_raw="கணிதம்",
            subject_display="Mathematics",
            tamil_title="கணிதம்",
            download_url="https://example.com/8th_maths.pdf",
            source_page="https://example.com",
            context=ctx,
        )

        valid_header = b"%PDF-1.6\n\x00\x01\x02"
        val = validate_final(
            resource=res,
            downloaded_header=valid_header,
            expected_class=8,
            expected_edition="2019 Edition",
            expected_term="Term 1",
            expected_subject="Mathematics",
        )
        self.assertTrue(val.is_valid)
        self.assertTrue(val.step_results["class"])
        self.assertTrue(val.step_results["edition"])
        self.assertTrue(val.step_results["tamil_medium"])
        self.assertTrue(val.step_results["term"])
        self.assertTrue(val.step_results["subject"])
        self.assertTrue(val.step_results["valid_pdf"])

    def test_final_validation_rejects_non_pdf(self):
        ctx = MediumContext(
            class_num=8,
            edition="2019 Edition",
            medium="Tamil",
            term="Term 1",
            table_header="8th Tamil Medium Books - Term I",
        )
        res = TextbookResource(
            class_num=8,
            edition="2019 Edition",
            term="Term 1",
            subject_raw="கணிதம்",
            subject_display="Mathematics",
            tamil_title="கணிதம்",
            download_url="https://example.com/8th_maths.pdf",
            source_page="https://example.com",
            context=ctx,
        )

        invalid_header = b"<!DOCTYPE html><html><body>Error</body></html>"
        val = validate_final(
            resource=res,
            downloaded_header=invalid_header,
            expected_class=8,
        )
        self.assertFalse(val.is_valid)
        self.assertFalse(val.step_results["valid_pdf"])

    def test_required_log_format(self):
        ctx = MediumContext(class_num=8, edition="2019 Edition", medium="Tamil", term="Term 1")
        res = TextbookResource(
            class_num=8,
            edition="2019 Edition",
            term="Term 1",
            subject_raw="கணிதம்",
            subject_display="Mathematics",
            tamil_title="கணிதம்",
            download_url="https://example.com/sample.pdf",
            source_page="https://example.com",
            context=ctx,
        )
        log_block = res.format_log_block(status="Downloading")
        expected_lines = [
            "[INFO]",
            "Class: 8",
            "Medium: Tamil",
            "Term: 1",
            "Subject: Mathematics",
            "Book: 8th Standard Mathematics - Term 1",
            "URL: https://example.com/sample.pdf",
            "Status: Downloading",
        ]
        for line in expected_lines:
            self.assertIn(line, log_block)


class TestScraperZeroEnglishLeakage(unittest.TestCase):

    def test_parser_filters_english_medium_completely(self):
        # Sample HTML containing both Tamil and English Medium tables
        sample_html = """
        <html>
        <body>
            <h2>8th Standard Textbooks</h2>
            
            <!-- Tamil Medium Table -->
            <table>
                <tr>
                    <th width="60%">8th Tamil Medium Books - Term I</th>
                    <th>Download Link</th>
                </tr>
                <tr>
                    <td>கணிதம்</td>
                    <td><a href="https://example.com/tm_maths.pdf">Download</a></td>
                </tr>
                <tr>
                    <td>அறிவியல்</td>
                    <td><a href="https://example.com/tm_science.pdf">Download</a></td>
                </tr>
            </table>

            <!-- English Medium Table -->
            <table>
                <tr>
                    <th width="60%">8th English Medium Books - Term I</th>
                    <th>Download Link</th>
                </tr>
                <tr>
                    <td>Mathematics</td>
                    <td><a href="https://example.com/em_maths.pdf">Download</a></td>
                </tr>
                <tr>
                    <td>Science</td>
                    <td><a href="https://example.com/em_science.pdf">Download</a></td>
                </tr>
            </table>
        </body>
        </html>
        """
        scraper = TamilTextbookScraper()
        tamil_books, amb_books = scraper.parse_class_page(
            class_num=8,
            page_html=sample_html,
            source_url="https://example.com/8th",
        )

        # Confirm ONLY Tamil Medium books were extracted
        self.assertEqual(len(tamil_books), 2)
        urls = [b.download_url for b in tamil_books]
        self.assertIn("https://example.com/tm_maths.pdf", urls)
        self.assertIn("https://example.com/tm_science.pdf", urls)

        # STRICT ASSERTION: ZERO English Medium books in Tamil queue
        self.assertNotIn("https://example.com/em_maths.pdf", urls)
        self.assertNotIn("https://example.com/em_science.pdf", urls)

        # Check inherited context
        for b in tamil_books:
            self.assertEqual(b.context.medium, "Tamil")
            self.assertEqual(b.term, "Term 1")


if __name__ == "__main__":
    unittest.main()
