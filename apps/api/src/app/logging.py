import logging
import sys

import structlog


def setup_logging(env: str) -> None:
    """structlog, JSON in deployed envs, pretty console in dev/test."""
    renderer = (
        structlog.dev.ConsoleRenderer()
        if env in ("dev", "test")
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
