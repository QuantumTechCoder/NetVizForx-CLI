#!/usr/bin/env python3
"""
main.py — NetVizForx-CLI entry point.

Auto-installs required libraries on first run, then launches the TUI.

Usage:
    python main.py [target]

If a target is provided, it's pre-filled for all tools.
If no target is given, you'll be prompted each time you select a tool.

Examples:
    python main.py
    python main.py google.com
    python main.py 1.1.1.1
"""

import subprocess
import sys


REQUIRED_LIBS = [
    "textual==0.74.0",
    "rich==13.9.4",
    "requests==2.32.3",
    "dnspython==2.7.0",
    "python-whois==0.9.4",
    "pyfiglet==1.0.2",
]


def install_requirements() -> None:
    """Install all required libraries using pip if they aren't already available."""
    # Quick check — if textual imports fine, assume deps are installed
    try:
        import textual  # noqa: F401
        import rich  # noqa: F401
        import requests  # noqa: F401
        import dns  # noqa: F401
        import whois  # noqa: F401
        import pyfiglet  # noqa: F401
        return
    except ImportError:
        pass

    print("Installing required libraries…")
    for lib in REQUIRED_LIBS:
        print(f"  Installing {lib}…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", lib],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print("All libraries installed.\n")


def main() -> None:
    install_requirements()

    target = ""
    if len(sys.argv) >= 2:
        target = sys.argv[1].strip()
        if not target:
            print("Error: target cannot be empty.")
            sys.exit(1)

    from src.ui import NetVizForxApp

    app = NetVizForxApp(target=target)
    try:
        app.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
