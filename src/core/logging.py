"""
Structured logging setup using structlog.
All agents call get_logger(__name__) and log structured key=value events.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

from src.core.config import settings


def configure_logging(quiet: bool = False) -> None:
    """
    Configure structured JSON logging.

    quiet=True  — logs go to file only (no stdout). Use for CLI scan/run so
                  Rich output is not mixed with JSON log lines.
    quiet=False — logs go to both stdout and file (default, used by the server).
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handlers: list[logging.Handler] = []
    if not quiet:
        handlers.append(logging.StreamHandler(sys.stdout))
    try:
        file_handler = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError:
        pass

    for h in handlers:
        h.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    for h in handlers:
        root_logger.addHandler(h)
    root_logger.setLevel(log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
