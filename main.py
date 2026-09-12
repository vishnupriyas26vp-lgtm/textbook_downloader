"""
Main entry point for Tamil Nadu School Textbooks Auto-Downloader.
STRICT REQUIREMENT: TAMIL MEDIUM ONLY.

Usage:
  python main.py              # Launches the Desktop GUI
  python main.py --cli ...    # Runs via Command Line Interface
"""

import sys

# Ensure UTF-8 output handling
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    # If any CLI arguments are provided (other than script name), check if CLI or GUI
    if len(sys.argv) > 1 and ("--cli" in sys.argv or "--classes" in sys.argv or "--scan-only" in sys.argv or "-h" in sys.argv or "--help" in sys.argv):
        from cli import build_parser, run_cli
        parser = build_parser()
        # Remove --cli flag if present to avoid parser error
        cli_args = [a for a in sys.argv[1:] if a != "--cli"]
        args = parser.parse_args(cli_args)
        run_cli(args)
    elif len(sys.argv) > 1 and "--web" in sys.argv:
        from web_app import start_web_server
        start_web_server(port=5000, open_browser=True)
    else:
        # Default: Launch GUI, fallback to Web App if desktop environment is unavailable
        try:
            from gui import launch_gui
            launch_gui()
        except Exception as e:
            print(f"[INFO] Desktop GUI unavailable ({e}). Starting Web GUI instead...")
            from web_app import start_web_server
            start_web_server(port=5000, open_browser=True)


if __name__ == "__main__":
    main()
