from __future__ import annotations

import logging
import urllib.parse
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

_POLLINATIONS_BASE = "https://image.pollinations.ai"
_HF_INFERENCE_URL = "https://api-inference.huggingface.co/models/{model}"
_HF_DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"


class ImageBackend(ABC):
    """Abstract base for image-generation backends."""

    @abstractmethod
    async def generate(self, prompt: str, width: int, height: int) -> bytes:
        """Generate an image and return raw bytes."""


class PollinationsBackend(ImageBackend):
    """Free image generation via Pollinations.AI — no API key required.

    URL pattern: ``{base}/prompt/{encoded_prompt}?width=W&height=H&model=flux``
    """

    def __init__(self, base_url: str = _POLLINATIONS_BASE, timeout: float = 60.0) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def generate(self, prompt: str, width: int, height: int) -> bytes:
        encoded = urllib.parse.quote(prompt, safe="")
        url = (
            f"{self._base_url}/prompt/{encoded}"
            f"?width={width}&height={height}&model=flux&nologo=true"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=self._timeout, follow_redirects=True)
            resp.raise_for_status()
            return resp.content


class HFInferenceBackend(ImageBackend):
    """HuggingFace Inference API — requires ``HF_TOKEN`` (free tier).

    Model: ``black-forest-labs/FLUX.1-schnell`` (free, no GPU required).
    """

    def __init__(
        self,
        token: str = "",
        model: str = _HF_DEFAULT_MODEL,
        timeout: float = 120.0,
    ) -> None:
        self._token = token
        self._model = model
        self._timeout = timeout

    async def generate(self, prompt: str, width: int, height: int) -> bytes:
        url = _HF_INFERENCE_URL.format(model=self._model)
        headers = {"Authorization": f"Bearer {self._token}"}
        payload = {"inputs": prompt, "parameters": {"width": width, "height": height}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=self._timeout)
            resp.raise_for_status()
            return resp.content
