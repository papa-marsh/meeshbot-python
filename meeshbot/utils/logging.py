import logging
import sys
from collections.abc import Mapping, MutableMapping
from datetime import datetime
from typing import Any

import structlog
from structlog.stdlib import BoundLogger, get_logger

from meeshbot.config import GROUPME_TOKEN, GROUPME_WEBHOOK_TOKEN, TIMEZONE


def _add_timezone_timestamp(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Add timestamp in configured timezone."""
    event_dict["timestamp"] = datetime.now(TIMEZONE).isoformat()
    return event_dict


_REDACTED_STRINGS: tuple[str, ...] = (GROUPME_TOKEN, GROUPME_WEBHOOK_TOKEN)


def _redact_tokens(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Redact sensitive strings from all log message fields."""
    for key, value in event_dict.items():
        if isinstance(value, str):
            for secret in _REDACTED_STRINGS:
                if secret:
                    value = value.replace(secret, "<redacted>")
            event_dict[key] = value
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
            foreign_pre_chain=[
                structlog.processors.add_log_level,
                _add_timezone_timestamp,
                _redact_tokens,
            ],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # uvicorn.access has propagate=False and its own handler by default,
    # so it bypasses the root logger. Replace its handler with ours so
    # that access logs flow through the same redacting processor chain.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = [handler]
    access_logger.propagate = False


log: BoundLogger = get_logger()
