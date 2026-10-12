from __future__ import annotations

import functools
import logging
import time
from typing import TYPE_CHECKING, Any

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Module-level tracer — set up by configure_tracing()
_tracer: trace.Tracer | None = None

# In-memory exporter used in tests
_test_exporter: InMemorySpanExporter | None = None


# ---------------------------------------------------------------------------
# Structlog configuration
# ---------------------------------------------------------------------------


def configure_structlog() -> None:
    """Configure structlog with JSON output and OTel trace context injection."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _inject_otel_context(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add OTel trace_id and span_id to every log record."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


# ---------------------------------------------------------------------------
# OpenTelemetry setup
# ---------------------------------------------------------------------------


def configure_tracing(*, test_mode: bool = False) -> None:
    """Set up OTel TracerProvider and export spans to Langfuse OTLP endpoint.

    When ``test_mode=True`` an in-memory exporter is used instead so tests
    can assert on emitted spans without a real Langfuse instance.

    When Langfuse keys are empty the provider is still set up but spans are
    exported to a no-op sink (so local dev works without credentials).
    """
    global _tracer, _test_exporter

    from api.settings import settings

    resource = Resource.create({SERVICE_NAME: "chatbot"})
    provider = TracerProvider(resource=resource)

    if test_mode:
        _test_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(_test_exporter))
    elif settings.langfuse_public_key and settings.langfuse_secret_key:
        import base64

        creds = base64.b64encode(
            f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
        ).decode()
        otlp_endpoint = settings.langfuse_host.rstrip("/") + "/api/public/otel/v1/traces"
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers={"Authorization": f"Basic {creds}"},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTel tracing configured → %s", otlp_endpoint)
    else:
        logger.info("Langfuse keys not set — tracing disabled (spans discarded)")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("chatbot")


def get_tracer() -> trace.Tracer:
    """Return the module-level tracer (lazy-init fallback if not configured)."""
    if _tracer is None:
        return trace.get_tracer("chatbot")
    return _tracer


def get_test_spans() -> list[Any]:
    """Return all in-memory spans (test helper)."""
    if _test_exporter is None:
        return []
    return list(_test_exporter.get_finished_spans())


# ---------------------------------------------------------------------------
# @traced_node decorator
# ---------------------------------------------------------------------------


def traced_node(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap an async LangGraph node function with an OTel span.

    Span attributes:
        node_name   — function name
        thread_id   — from state["hitl_config"]["thread_id"] if present
        step_index  — state["current_step"]
    """

    @functools.wraps(fn)
    async def wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        node_name = fn.__name__
        thread_id = ""
        if isinstance(state, dict):
            cfg = state.get("hitl_config") or {}
            thread_id = str(cfg.get("thread_id", ""))
            step_index = state.get("current_step", 0)
        else:
            step_index = 0

        with tracer.start_as_current_span(node_name) as span:
            span.set_attribute("node_name", node_name)
            span.set_attribute("step_index", step_index)
            if thread_id:
                span.set_attribute("thread_id", thread_id)
            return await fn(state, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# ToolRegistry instrumentation
# ---------------------------------------------------------------------------


def instrument_tool_registry() -> None:
    """Patch _RegisteredTool.__call__ to emit an OTel span per tool invocation."""
    from tools.base import _RegisteredTool

    original_call = _RegisteredTool.__call__

    @functools.wraps(original_call)
    async def _traced_call(self: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        tool_name: str = self.descriptor.name
        risk: str = self.descriptor.risk

        with tracer.start_as_current_span(f"tool.{tool_name}") as span:
            span.set_attribute("tool_name", tool_name)
            span.set_attribute("tool_risk", risk)
            t0 = time.monotonic()
            try:
                result = await original_call(self, **kwargs)
                span.set_attribute("tool_duration_ms", round((time.monotonic() - t0) * 1000))
                return result
            except Exception as exc:
                span.set_attribute("tool_error", str(exc))
                span.record_exception(exc)
                raise

    _RegisteredTool.__call__ = _traced_call  # type: ignore[method-assign]
    logger.debug("ToolRegistry instrumented with OTel spans")


# ---------------------------------------------------------------------------
# LiteLLM instrumentation
# ---------------------------------------------------------------------------


def configure_litellm_tracing() -> None:
    """Register a LiteLLM callback that emits an OTel span per LLM call."""
    import litellm

    from api.settings import settings

    # Enable Langfuse native integration when keys are present
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        import os

        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        if "langfuse" not in (litellm.success_callback or []):
            litellm.success_callback = [*(litellm.success_callback or []), "langfuse"]
        logger.info("LiteLLM → Langfuse callback enabled")

    # Always attach OTel span callback
    litellm.callbacks = [*(litellm.callbacks or []), _LLMSpanCallback()]  # type: ignore[list-item]
    logger.debug("LiteLLM OTel span callback registered")


class _LLMSpanCallback:
    """LiteLLM callback that creates an OTel span for each LLM call."""

    def log_success_event(self, kwargs: Any, response_obj: Any, **_: Any) -> None:
        tracer = get_tracer()
        model = kwargs.get("model", "unknown")
        with tracer.start_as_current_span(f"llm.{model}") as span:
            span.set_attribute("llm.model", model)
            usage = getattr(response_obj, "usage", None)
            if usage:
                span.set_attribute("llm.prompt_tokens", getattr(usage, "prompt_tokens", 0))
                span.set_attribute("llm.completion_tokens", getattr(usage, "completion_tokens", 0))
            duration = kwargs.get("end_time", 0) - kwargs.get("start_time", 0)
            if duration:
                span.set_attribute("llm.latency_ms", round(duration * 1000))

    def log_failure_event(self, kwargs: Any, response_obj: Any, **_: Any) -> None:  # noqa: ARG002
        tracer = get_tracer()
        model = kwargs.get("model", "unknown")
        with tracer.start_as_current_span(f"llm.{model}") as span:
            span.set_attribute("llm.model", model)
            span.set_attribute("llm.error", str(kwargs.get("exception", "")))


# ---------------------------------------------------------------------------
# Langfuse health check
# ---------------------------------------------------------------------------


async def check_langfuse_health() -> bool:
    """Return True if Langfuse is reachable (HTTP GET /api/public/health)."""
    import httpx

    from api.settings import settings

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(settings.langfuse_host.rstrip("/") + "/api/public/health")
            return resp.status_code < 500
    except Exception:
        return False
