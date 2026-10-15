"""Local web UI entrypoint (production "User Interface" requirement).

Binds to 127.0.0.1 only -- a single-operator local dashboard, not a
network-facing service. Runs independently of `run_live_loop.py`; both
read/write the same PostgreSQL database, so settings changes here take
effect on the live loop's very next cycle.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/run_web_ui.py
"""

from __future__ import annotations

import uvicorn

_HOST = "127.0.0.1"
_PORT = 8420


def main() -> None:
    """Start the local web UI."""
    uvicorn.run("src.interfaces.web.app:app", host=_HOST, port=_PORT, log_level="info")


if __name__ == "__main__":
    main()
