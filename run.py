#!/usr/bin/env python3
"""Kashe Royale launcher.

    python run.py

Starts the authoritative game server and prints the local + LAN addresses.
Only the Python standard library is required (Python 3.10+).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pokerstack.server import main  # noqa: E402


DEFAULT_PORT = 8000


def default_port() -> int:
    """Hosting platforms (Render, Railway, Fly, Koyeb) inject $PORT and expect it to be used."""
    raw = os.environ.get("PORT", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_PORT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kashe Royale — Royal Texas Hold'em")
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default 0.0.0.0)")
    parser.add_argument(
        "--port",
        type=int,
        default=default_port(),
        help=f"first port to try (default: $PORT if set, else {DEFAULT_PORT})",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(host=args.host, port=args.port, open_browser=not args.no_browser)
