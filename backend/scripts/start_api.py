"""Expand Cloud Run's PORT safely and replace the launcher with one API process."""

import os
import sys


def api_command(port: str) -> list[str]:
    if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("PORT must be an integer from 1 to 65535")
    return [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", str(int(port)), "--workers", "1",
    ]


def main() -> int:
    try:
        command = api_command(os.environ.get("PORT", "8080"))
    except ValueError:
        print("API configuration invalid: PORT must be an integer from 1 to 65535", file=sys.stderr)
        return 1
    os.execv(sys.executable, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
