from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import litellm
import yaml
from langchain_litellm import ChatLiteLLM

logger = logging.getLogger(__name__)

LLMRole = Literal["planner", "fast"]

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "litellm_config.yaml"

with _CONFIG_PATH.open() as _f:
    _litellm_config: dict[str, object] = yaml.safe_load(_f)

litellm.suppress_debug_info = True


class LLMUnavailableError(Exception):
    """Raised when all providers in a role's fallback chain are unavailable."""


def _models_for_role(role: LLMRole) -> list[str]:
    model_list: list[dict[str, object]] = _litellm_config.get("model_list", [])  # type: ignore[assignment]
    return [
        str(entry["litellm_params"]["model"])  # type: ignore[index]
        for entry in model_list
        if entry.get("model_name") == role
    ]


def get_llm(role: LLMRole) -> Any:
    """Return a LangChain-compatible chat model for the given role.

    When multiple providers are configured, chains them via .with_fallbacks()
    so each provider is tried in order on failure.

    Raises:
        ValueError: for unknown roles.
        LLMUnavailableError: when no models are configured for the role.
    """
    valid_roles: tuple[LLMRole, ...] = ("planner", "fast")
    if role not in valid_roles:
        raise ValueError(f"Unknown LLM role {role!r}. Valid roles: {valid_roles}")

    models = _models_for_role(role)
    if not models:
        raise LLMUnavailableError(
            f"No models configured for role {role!r}. Check config/litellm_config.yaml."
        )

    logger.debug("get_llm role=%s models=%s", role, models)

    primary = ChatLiteLLM(model=models[0], max_retries=3)
    if len(models) == 1:
        return primary

    fallbacks = [ChatLiteLLM(model=m, max_retries=2) for m in models[1:]]
    return primary.with_fallbacks(fallbacks)


async def check_provider_health() -> dict[str, bool]:
    """Ping one model per provider and return availability map.

    Used for observability / startup checks. Never raises.
    """
    model_list: list[dict[str, object]] = _litellm_config.get("model_list", [])  # type: ignore[assignment]
    seen: set[str] = set()
    results: dict[str, bool] = {}

    for entry in model_list:
        model = str(entry["litellm_params"]["model"])  # type: ignore[index]
        provider = model.split("/")[0]
        if provider in seen:
            continue
        seen.add(provider)
        try:
            await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            results[provider] = True
        except Exception as exc:
            logger.warning("Provider %s unavailable: %s", provider, exc)
            results[provider] = False

    return results
