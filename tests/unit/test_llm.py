from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.llm import LLMUnavailableError, _models_for_role, get_llm


@pytest.mark.unit
def test_get_llm_planner_returns_model() -> None:
    llm = get_llm("planner")
    assert llm is not None


@pytest.mark.unit
def test_get_llm_fast_returns_model() -> None:
    llm = get_llm("fast")
    assert llm is not None


@pytest.mark.unit
def test_get_llm_unknown_role_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM role"):
        get_llm("unknown")  # type: ignore[arg-type]


@pytest.mark.unit
def test_get_llm_no_models_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.llm._litellm_config", {"model_list": []})
    with pytest.raises(LLMUnavailableError, match="No models configured"):
        get_llm("planner")


@pytest.mark.unit
def test_planner_has_fallbacks() -> None:
    models = _models_for_role("planner")
    assert len(models) >= 2, "planner must have at least 2 providers for fallback"


@pytest.mark.unit
def test_fast_has_fallbacks() -> None:
    models = _models_for_role("fast")
    assert len(models) >= 2, "fast must have at least 2 providers for fallback"


@pytest.mark.unit
def test_planner_primary_is_gemini() -> None:
    models = _models_for_role("planner")
    assert models[0].startswith("gemini/"), f"Expected Gemini as primary planner, got {models[0]}"


@pytest.mark.unit
def test_fast_primary_is_groq() -> None:
    models = _models_for_role("fast")
    assert models[0].startswith("groq/"), f"Expected Groq as primary fast, got {models[0]}"


@pytest.mark.unit
async def test_check_provider_health_returns_dict() -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]

    with patch("api.llm.litellm.acompletion", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = mock_response
        from api.llm import check_provider_health

        results = await check_provider_health()

    assert isinstance(results, dict)
    assert len(results) > 0
    assert all(isinstance(v, bool) for v in results.values())


@pytest.mark.unit
async def test_check_provider_health_handles_failure() -> None:
    with patch("api.llm.litellm.acompletion", new_callable=AsyncMock) as mock_complete:
        mock_complete.side_effect = Exception("connection refused")
        from api.llm import check_provider_health

        results = await check_provider_health()

    assert all(v is False for v in results.values())
