import logging
import sys
from collections.abc import Mapping, MutableMapping
from datetime import datetime
from typing import Any

import structlog
from structlog.stdlib import BoundLogger, get_logger

from meeshbot.config import GROUPME_WEBHOOK_TOKEN, TIMEZONE


def _add_timezone_timestamp(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Add timestamp in configured timezone."""
    event_dict["timestamp"] = datetime.now(TIMEZONE).isoformat()
    return event_dict


def _redact_tokens(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Redact webhook token from log messages (e.g. uvicorn access logs)."""
    event = event_dict.get("event")
    if isinstance(event, str):
        event_dict["event"] = event.replace(GROUPME_WEBHOOK_TOKEN, "<redacted>")
    return event_dict


def configure_logging() -> None:
    """Configure structlog with colored output and timezone timestamps."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_timezone_timestamp,
            _redact_tokens,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(min_level=logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging (e.g. APScheduler, uvicorn) into structlog's output
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                _redact_tokens,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    logging.getLogger("apscheduler").setLevel(logging.WARNING)


log: BoundLogger = get_logger()
