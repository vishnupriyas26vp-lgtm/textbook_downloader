"""
Command Line Interface for Tamil Medium School Textbooks Auto-Downloader.
STRICT REQUIREMENT: TAMIL MEDIUM ONLY.
"""

import sys
import argparse
from pathlib import Path
from typing import List

from scraper import TamilTextbookScraper
from downloader import TamilTextbookDownloader
from config import SUPPORTED_CLASSES, DEFAULT_DOWNLOAD_DIR


def run_cli(args: argparse.Namespace):
    # Ensure stdout handles Unicode Tamil correctly
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print(" TAMIL NADU SCHOOL TEXTBOOKS AUTO-DOWNLOADER")
    print(" REQUIREMENT: TAMIL MEDIUM ONLY")
    print("=" * 60)
    print("Notice: Only Tamil Medium textbooks will be downloaded.")
    print("=" * 60 + "\n")

    # Determine classes to scrape
    if args.classes.lower() == "all":
        target_classes = SUPPORTED_CLASSES
    else:
        try:
            target_classes = [int(c.strip()) for c in args.classes.split(",") if c.strip()]
        except ValueError:
            print(f"[ERROR] Invalid classes argument: {args.classes}. Use e.g. '8' or '8,9,10' or 'all'")
            sys.exit(1)

    scraper = TamilTextbookScraper(log_callback=print)

    all_tamil_books = []
    all_ambiguous_books = []

    for c_num in target_classes:
        print(f"\nScanning Class {c_num} (Tamil Medium)...")
        tamil_books, amb_books = scraper.scrape_class(
            class_num=c_num,
            target_term=args.term,
            target_edition=args.edition,
        )

        # Subject filter if specified
        if args.subject:
            s_filter = args.subject.lower()
            tamil_books = [
                b for b in tamil_books
                if s_filter in b.subject_display.lower() or s_filter in b.subject_raw.lower()
            ]

        all_tamil_books.extend(tamil_books)
        all_ambiguous_books.extend(amb_books)

    print(f"\n[SCAN COMPLETE]")
    print(f"Verified Tamil Medium Books Found: {len(all_tamil_books)}")
    print(f"Ambiguous / Skipped Resources: {len(all_ambiguous_books)}")

    if not all_tamil_books:
        print("\nNo Tamil Medium books found matching the selected criteria.")
        return

    print("\n--- Discovered Tamil Medium Books ---")
    for idx, book in enumerate(all_tamil_books):
        print(f"{idx + 1:3d}. Class {book.class_num:2d} | {book.edition} | {book.term:9s} | {book.subject_display} ({book.subject_raw})")

    if args.scan_only:
        print("\n[INFO] Scan-only mode active. Skipping download.")
        return

    # Start download
    dest_path = args.dest or DEFAULT_DOWNLOAD_DIR
    print(f"\nDestination Directory: {dest_path}")
    confirm = input(f"\nProceed with downloading {len(all_tamil_books)} Tamil Medium books? [y/N]: ") if not args.yes else "y"

    if confirm.lower() != "y":
        print("Download cancelled by user.")
        return

    downloader = TamilTextbookDownloader(
        download_dir=dest_path,
        on_log=print,
    )

    results = downloader.download_queue(
        resources=all_tamil_books,
        expected_term=args.term,
        expected_edition=args.edition,
        expected_subject=args.subject,
    )

    print("\n" + "=" * 60)
    print(" DOWNLOAD SUMMARY")
    print("=" * 60)
    print(f"Total Tamil Medium Books: {results['total']}")
    print(f"Successfully Downloaded:   {results['completed']}")
    print(f"Failed / Skipped:         {results['failed']}")
    print("=" * 60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tamil Nadu School Textbooks Downloader (TAMIL MEDIUM ONLY)"
    )
    parser.add_argument(
        "--classes",
        default="8",
        help="Class number(s) to download: '8', '8,9,10', or 'all' (default: '8')",
    )
    parser.add_argument(
        "--term",
        default="All Terms",
        help="Term filter: 'Term 1', 'Term 2', 'Term 3', 'Full Book', or 'All Terms' (default: 'All Terms')",
    )
    parser.add_argument(
        "--edition",
        default="All Editions",
        help="Edition filter: e.g. '2024-25 Edition', '2019 Edition', or 'All Editions' (default: 'All Editions')",
    )
    parser.add_argument(
        "--subject",
        default="",
        help="Subject name filter (e.g. 'Mathematics', 'Science', 'கணிதம்')",
    )
    parser.add_argument(
        "--dest",
        default="",
        help=f"Destination directory (default: {DEFAULT_DOWNLOAD_DIR})",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Only scan and list verified Tamil Medium books without downloading",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically confirm and start downloads without prompt",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    run_cli(args)
