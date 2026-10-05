"""Unit tests for the image agent — backends, job, nodes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class TestPollinationsBackend:
    @pytest.mark.asyncio
    async def test_returns_bytes_on_success(self) -> None:
        from agents.image.backends import PollinationsBackend

        image_bytes = b"\xff\xd8\xff\xe0image"
        mock_resp = MagicMock()
        mock_resp.content = image_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("agents.image.backends.httpx.AsyncClient", return_value=mock_client):
            backend = PollinationsBackend()
            result = await backend.generate("a sunset", 1280, 720)

        assert result == image_bytes

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self) -> None:
        import httpx

        from agents.image.backends import PollinationsBackend

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock())
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("agents.image.backends.httpx.AsyncClient", return_value=mock_client):
            backend = PollinationsBackend()
            with pytest.raises(httpx.HTTPStatusError):
                await backend.generate("a sunset", 1280, 720)


class TestHFInferenceBackend:
    @pytest.mark.asyncio
    async def test_returns_bytes_on_success(self) -> None:
        from agents.image.backends import HFInferenceBackend

        image_bytes = b"hf-image-data"
        mock_resp = MagicMock()
        mock_resp.content = image_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("agents.image.backends.httpx.AsyncClient", return_value=mock_client):
            backend = HFInferenceBackend(token="test-token")
            result = await backend.generate("a sunset", 512, 512)

        assert result == image_bytes

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self) -> None:
        import httpx

        from agents.image.backends import HFInferenceBackend

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock())
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("agents.image.backends.httpx.AsyncClient", return_value=mock_client):
            backend = HFInferenceBackend(token="test-token")
            with pytest.raises(httpx.HTTPStatusError):
                await backend.generate("a sunset", 512, 512)


# ---------------------------------------------------------------------------
# ImageGenerationJob
# ---------------------------------------------------------------------------


class TestImageGenerationJob:
    def _make_ctx(self) -> dict[str, Any]:
        redis_mock = AsyncMock()
        redis_mock.publish = AsyncMock()
        return {"redis": redis_mock}

    @pytest.mark.asyncio
    async def test_run_uses_first_backend_on_success(self, tmp_path: Any) -> None:
        from agents.image.backends import ImageBackend
        from agents.image.job import ImageGenerationJob

        image_bytes = b"img"

        class FakeBackend(ImageBackend):
            async def generate(self, _prompt: str, _width: int, _height: int) -> bytes:
                return image_bytes

        ctx = self._make_ctx()
        with patch("agents.image.job.settings") as mock_settings:
            mock_settings.artifacts_local_path = str(tmp_path)
            job = ImageGenerationJob(
                job_id="test-job",
                ctx=ctx,
                prompt="test prompt",
                backends=[FakeBackend()],
            )
            result = await job.run()

        assert "artifact_id" in result
        assert result["artifact_type"] == "image"
        assert result["width"] == 1280
        assert result["height"] == 720

    @pytest.mark.asyncio
    async def test_run_falls_back_to_second_backend(self, tmp_path: Any) -> None:
        from agents.image.backends import ImageBackend
        from agents.image.job import ImageGenerationJob

        image_bytes = b"img-from-fallback"

        class FailBackend(ImageBackend):
            async def generate(self, _prompt: str, _width: int, _height: int) -> bytes:
                raise RuntimeError("primary failed")

        class OkBackend(ImageBackend):
            async def generate(self, _prompt: str, _width: int, _height: int) -> bytes:
                return image_bytes

        ctx = self._make_ctx()
        with patch("agents.image.job.settings") as mock_settings:
            mock_settings.artifacts_local_path = str(tmp_path)
            job = ImageGenerationJob(
                job_id="test-job",
                ctx=ctx,
                prompt="test prompt",
                backends=[FailBackend(), OkBackend()],
            )
            result = await job.run()

        assert "artifact_id" in result

    @pytest.mark.asyncio
    async def test_run_raises_when_all_backends_fail(self) -> None:
        from agents.image.backends import ImageBackend
        from agents.image.job import ImageGenerationJob

        class FailBackend(ImageBackend):
            async def generate(self, _prompt: str, _width: int, _height: int) -> bytes:
                raise RuntimeError("failed")

        ctx = self._make_ctx()
        job = ImageGenerationJob(
            job_id="test-job",
            ctx=ctx,
            prompt="test",
            backends=[FailBackend(), FailBackend()],
        )
        with pytest.raises(RuntimeError, match="All image generation backends failed"):
            await job.run()

    @pytest.mark.asyncio
    async def test_on_progress_publishes_to_redis(self) -> None:
        import json

        from agents.image.backends import ImageBackend
        from agents.image.job import ImageGenerationJob

        class OkBackend(ImageBackend):
            async def generate(self, _prompt: str, _width: int, _height: int) -> bytes:
                return b"img"

        ctx = self._make_ctx()
        with patch("agents.image.job.settings") as mock_settings:
            mock_settings.artifacts_local_path = "/tmp"
            job = ImageGenerationJob(
                job_id="my-job",
                ctx=ctx,
                prompt="test",
                backends=[OkBackend()],
            )
            await job.on_progress(50, "halfway")

        redis_mock = ctx["redis"]
        redis_mock.publish.assert_called_once()
        channel, payload = redis_mock.publish.call_args[0]
        assert channel == "job:my-job:progress"
        data = json.loads(payload)
        assert data["percent"] == 50
        assert data["message"] == "halfway"


# ---------------------------------------------------------------------------
# ImageArtifact model
# ---------------------------------------------------------------------------


class TestImageArtifact:
    def test_to_dict_contains_required_fields(self) -> None:
        from agents.image.models import ImageArtifact

        art = ImageArtifact(
            artifact_id="abc123",
            url="/artifacts/abc123",
            width=1280,
            height=720,
            prompt="test prompt",
        )
        d = art.to_dict()
        assert d["artifact_id"] == "abc123"
        assert d["url"] == "/artifacts/abc123"
        assert d["width"] == 1280
        assert d["height"] == 720
        assert d["prompt"] == "test prompt"
        assert d["artifact_type"] == "image"


# ---------------------------------------------------------------------------
# run_image_agent node
# ---------------------------------------------------------------------------


class TestRunImageAgentNode:
    def _make_state(self, goal: str = "a beautiful sunset") -> Any:
        return {
            "current_step": 0,
            "plan": [{"goal": goal, "agent": "image", "inputs": {}, "status": "pending"}],
            "observations": [],
            "artifacts": [],
            "messages": [],
        }

    @pytest.mark.asyncio
    async def test_success_path_updates_state(self) -> None:
        from agents.image.nodes import run_image_agent

        artifact_dict = {
            "artifact_id": "xyz",
            "url": "/artifacts/xyz",
            "width": 1280,
            "height": 720,
            "prompt": "refined",
            "artifact_type": "image",
        }

        mock_job = AsyncMock()
        mock_job.result = AsyncMock(return_value=artifact_dict)

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch("agents.image.nodes.refine_image_prompt", return_value="refined prompt"),
            patch("agents.image.nodes.get_arq_pool", return_value=mock_pool),
        ):
            result = await run_image_agent(self._make_state())

        update = result.update
        assert any(
            "refined" in str(o) or "/artifacts/xyz" in str(o) for o in update["observations"]
        )
        assert update["artifacts"][0]["artifact_id"] == "xyz"
        assert update["plan"][0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_enqueue_failure_records_observation(self) -> None:
        from agents.image.nodes import run_image_agent

        with (
            patch("agents.image.nodes.refine_image_prompt", return_value="refined"),
            patch("agents.image.nodes.get_arq_pool", side_effect=RuntimeError("redis down")),
        ):
            result = await run_image_agent(self._make_state())

        observations = result.update["observations"]
        assert any("could not enqueue" in o for o in observations)

    @pytest.mark.asyncio
    async def test_prompt_refinement_fallback_uses_raw_goal(self) -> None:
        from agents.image.nodes import run_image_agent

        artifact_dict = {
            "artifact_id": "abc",
            "url": "/artifacts/abc",
            "width": 1280,
            "height": 720,
            "prompt": "a beautiful sunset",
            "artifact_type": "image",
        }

        mock_job = AsyncMock()
        mock_job.result = AsyncMock(return_value=artifact_dict)

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with (
            patch(
                "agents.image.nodes.refine_image_prompt",
                side_effect=RuntimeError("llm error"),
            ),
            patch("agents.image.nodes.get_arq_pool", return_value=mock_pool),
        ):
            await run_image_agent(self._make_state("a beautiful sunset"))

        # Job was still enqueued (with raw goal as prompt)
        mock_pool.enqueue_job.assert_called_once()
        _, kwargs = mock_pool.enqueue_job.call_args
        assert kwargs["prompt"] == "a beautiful sunset"
