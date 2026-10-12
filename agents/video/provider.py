from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class VideoProvider(ABC):
    """Abstract interface for video generation backends.

    Implementations must be stateless and thread-safe.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        keyframe_url: str | None = None,
        duration_s: int = 10,
    ) -> bytes:
        """Generate a video clip and return raw bytes (mp4).

        Parameters
        ----------
        prompt:
            Text description of the video.
        keyframe_url:
            Optional URL to a reference image used as the first frame.
        duration_s:
            Desired clip length in seconds. Capped at 10s by the agent.
        """


class HFSpacesProvider(VideoProvider):
    """Video generation via Hugging Face Spaces using gradio_client.

    Uses ``asyncio.to_thread`` to run the synchronous gradio_client in a
    thread pool so it does not block the event loop.

    The generated video file is downloaded as raw bytes. Supports any
    Gradio Space that exposes a text-to-video API endpoint.

    Parameters
    ----------
    space:
        HF Spaces repo id, e.g. ``"Wan-AI/Wan2.1-T2V-14B"``.
    api_name:
        Gradio API endpoint name within the space.
    hf_token:
        Optional HF token for private or gated spaces.
    timeout:
        Per-generation timeout in seconds (default: 600 — queues can be long).
    """

    def __init__(
        self,
        space: str,
        *,
        api_name: str = "/generate",
        hf_token: str = "",
        timeout: float = 600.0,
    ) -> None:
        self._space = space
        self._api_name = api_name
        self._hf_token = hf_token
        self._timeout = timeout

    async def generate(
        self,
        prompt: str,
        *,
        keyframe_url: str | None = None,
        duration_s: int = 10,
    ) -> bytes:
        """Submit job to HF Spaces and return video bytes."""
        video_url = await asyncio.wait_for(
            asyncio.to_thread(self._run_gradio, prompt, keyframe_url, duration_s),
            timeout=self._timeout,
        )
        return await self._download(video_url)

    def _run_gradio(
        self,
        prompt: str,
        keyframe_url: str | None,
        duration_s: int,
    ) -> str:
        """Synchronous gradio_client call — runs in a thread pool."""
        from gradio_client import Client, handle_file  # type: ignore[import-untyped]

        kwargs: dict = {"src": self._space}
        if self._hf_token:
            kwargs["hf_token"] = self._hf_token

        client = Client(**kwargs)

        predict_kwargs: dict = {
            "prompt": prompt,
            "num_frames": min(duration_s * 8, 81),  # ~8 fps, cap at 81 frames
        }
        if keyframe_url:
            predict_kwargs["image"] = handle_file(keyframe_url)

        result = client.predict(api_name=self._api_name, **predict_kwargs)

        # result may be a file path string or a dict with a "video" key
        if isinstance(result, dict):
            return str(result.get("video") or result.get("url") or result)
        return str(result)

    @staticmethod
    async def _download(url: str) -> bytes:
        """Download video from URL or read from local path."""
        if Path(url).exists():
            return Path(url).read_bytes()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
