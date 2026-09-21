"""Production WSGI runner.

Used on Windows hosts and in the production Docker image. The choice is
waitress because gunicorn does not support Windows; waitress supports
both and is the documented production server in the README and docs.
"""
from __future__ import annotations

import logging
import os
import signal

from app import create_app


def main() -> None:
    app = create_app("production")
    host = os.environ.get("BIND_ADDRESS", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    threads = int(os.environ.get("WEB_CONCURRENCY", "4"))
    logging.getLogger(__name__).info(
        "production server starting on %s:%d (threads=%d)", host, port, threads
    )

    try:
        from waitress import serve
    except ImportError as exc:
        raise RuntimeError(
            "waitress is not installed. Install backend/requirements.txt first."
        ) from exc

    def _shutdown(signum, frame):
        logging.getLogger(__name__).info("shutdown requested by signal %s", signum)
        raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _shutdown)
        except (OSError, ValueError):
            # windows main-thread signal semantics
            pass

    serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
