"""structlog setup: JSON lines in production, readable lines locally.

Request-scoped fields (request_id, tenant_id) live in contextvars, so any
log call during a request carries them without passing a logger around.
"""

from __future__ import annotations

import logging

import structlog


def configure(*, json: bool, level: str) -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _stdlib_extra,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


_STD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def _stdlib_extra(
    logger: object, method: str, event: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Lift ``extra={...}`` fields from plain logging calls into the event."""
    record = event.get("_record")
    if record is not None:
        for k, v in vars(record).items():
            if k not in _STD_ATTRS and not k.startswith("_"):
                event.setdefault(k, v)
    return event


def bind(**fields: object) -> None:
    structlog.contextvars.bind_contextvars(**fields)


def clear() -> None:
    structlog.contextvars.clear_contextvars()
