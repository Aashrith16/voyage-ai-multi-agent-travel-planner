"""Safe request and workflow diagnostics for API failures."""

from contextvars import ContextVar
from functools import wraps
import logging
import os
import re
import traceback
from typing import Callable, TypeVar
from uuid import uuid4


logger = logging.getLogger("voyage_ai.diagnostics")
logger.setLevel(logging.INFO)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
workflow_stage_var: ContextVar[str | None] = ContextVar("workflow_stage", default=None)

F = TypeVar("F", bound=Callable)


def new_correlation_id() -> str:
    return uuid4().hex


def safe_error_payload(correlation_id: str) -> dict[str, str]:
    return {
        "code": "internal_server_error",
        "message": "An unexpected error occurred while planning this trip.",
        "correlation_id": correlation_id,
    }


def _redact(text: str) -> str:
    for key, value in os.environ.items():
        if value and len(value) >= 8 and any(
            marker in key.casefold() for marker in ("key", "secret", "token", "password", "credential")
        ):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization)(\s*[=:]\s*|\s+)[^\s,;&]+",
        r"\1\2[REDACTED]",
        text,
    )
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", text)
    return text


def log_unexpected_exception(
    error: BaseException,
    *,
    stage: str | None = None,
    method: str | None = None,
    path: str | None = None,
) -> str:
    correlation_id = correlation_id_var.get() or new_correlation_id()
    traceback_text = _redact("".join(traceback.format_exception(type(error), error, error.__traceback__)))
    logger.error(
        "Unhandled VoyageAI exception correlation_id=%s stage=%s method=%s path=%s exception_type=%s\n%s",
        correlation_id,
        stage or workflow_stage_var.get() or "unknown",
        method or "unknown",
        path or "unknown",
        type(error).__name__,
        traceback_text,
    )
    return correlation_id


def instrument_workflow_node(stage: str, function: F) -> F:
    """Expose the failing graph node to the API exception logger."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        token = workflow_stage_var.set(stage)
        correlation_id = correlation_id_var.get() or "unavailable"
        logger.info("Workflow stage entered correlation_id=%s stage=%s", correlation_id, stage)
        try:
            result = function(*args, **kwargs)
        except BaseException as error:
            # Keep the failing stage available until the API logs the error.
            workflow_stage_var.set(stage)
            if type(error).__name__ == "GraphInterrupt":
                logger.info("Workflow stage paused correlation_id=%s stage=%s checkpoint=budget_review", correlation_id, stage)
            else:
                logger.info(
                    "Workflow stage failed correlation_id=%s stage=%s exception_type=%s",
                    correlation_id,
                    stage,
                    type(error).__name__,
                )
            try:
                setattr(error, "voyageai_workflow_stage", stage)
            except Exception:
                pass
            raise
        else:
            logger.info("Workflow stage completed correlation_id=%s stage=%s", correlation_id, stage)
            workflow_stage_var.reset(token)
            return result

    return wrapped  # type: ignore[return-value]
