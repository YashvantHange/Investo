"""Application logging setup.

All logs go to **stderr** — never stdout, which the MCP stdio transport reserves for the
JSON-RPC protocol. The library logger ``investo`` carries a ``NullHandler`` by default (see
``investo/__init__.py``) so importing the package is silent; ``configure_logging()`` attaches a
real stderr handler and is called by the server and CLI entry points. Level is controlled by
``INVESTO_LOG_LEVEL`` (default ``WARNING``).
"""

from __future__ import annotations

import logging
import sys

from .config import CONFIG

_HANDLER_FLAG = "_investo_handler"


def configure_logging(level: str | None = None) -> logging.Logger:
    """Attach a stderr handler to the ``investo`` logger at the configured level (idempotent)."""
    logger = logging.getLogger("investo")
    resolved = (level or CONFIG.log_level or "WARNING").upper()
    logger.setLevel(getattr(logging, resolved, logging.WARNING))

    if not any(getattr(h, _HANDLER_FLAG, False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)  # stderr only
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        setattr(handler, _HANDLER_FLAG, True)
        logger.addHandler(handler)
    logger.propagate = False
    return logger
