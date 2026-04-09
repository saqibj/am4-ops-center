"""Small app utility CLI."""

from __future__ import annotations

import argparse

from app.state import reset_setup


def main() -> None:
    parser = argparse.ArgumentParser(description="AM4 Ops Center app utilities")
    parser.add_argument(
        "--reset-setup",
        action="store_true",
        help="Clear setup-complete flag in app_state",
    )
    args = parser.parse_args()

    if args.reset_setup:
        reset_setup()
        print("Setup flag cleared.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()

