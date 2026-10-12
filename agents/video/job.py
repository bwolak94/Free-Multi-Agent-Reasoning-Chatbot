from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from agents.video.models import VideoArtifact
from agents.video.provider import HFSpacesProvider, VideoProvider
from api.settings import settings
from workers.jobs import BaseWorkerJob

logger = logging.getLogger(__name__)

_VIDEO_JOB_TIMEOUT = 600  # 10 minutes — HF Spaces queues can be long


def _default_provider() -> VideoProvider:
    return HFSpacesProvider(
        space=settings.hf_video_space,
        api_name=settings.hf_video_api_name,
        hf_token=settings.hf_token,
        timeout=float(_VIDEO_JOB_TIMEOUT - 30),
    )


async def _save_artifact_local(video_bytes: bytes, prompt: str, duration_s: int) -> VideoArtifact:
    artifact_id = str(uuid.uuid4())
    artifacts_dir = Path(settings.artifacts_local_path)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    video_path = artifacts_dir / f"{artifact_id}.mp4"
    video_path.write_bytes(video_bytes)
    return VideoArtifact(
        artifact_id=artifact_id,
        url=f"/artifacts/{artifact_id}",
        prompt=prompt,
        duration_s=duration_s,
    )


class VideoGenerationJob(BaseWorkerJob):
    """arq job: generate a video clip via HF Spaces VideoProvider."""

    def __init__(
        self,
        job_id: str,
        ctx: dict[str, Any],
        prompt: str,
        duration_s: int = 10,
        keyframe_url: str | None = None,
        provider: VideoProvider | None = None,
    ) -> None:
        super().__init__(job_id, ctx)
        self.prompt = prompt
        self.duration_s = min(duration_s, 10)  # enforce max 10s
        self.keyframe_url = keyframe_url
        self._provider: VideoProvider = provider or _default_provider()

    async def run(self) -> dict[str, Any]:
        await self.on_progress(5, "Submitting to HF Spaces...")

        try:
            await self.on_progress(
                10, f"Generating {self.duration_s}s clip (queue may take minutes)..."
            )
            video_bytes = await self._provider.generate(
                self.prompt,
                keyframe_url=self.keyframe_url,
                duration_s=self.duration_s,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                f"Video generation timed out after {_VIDEO_JOB_TIMEOUT // 60} minutes"
            ) from exc
        except Exception as exc:
            logger.error("Video generation failed: %s", exc)
            raise

        if not video_bytes:
            raise RuntimeError("Provider returned empty video data")

        await self.on_progress(90, "Saving artifact...")
        artifact = await _save_artifact_local(video_bytes, self.prompt, self.duration_s)

        await self.on_progress(100, "Done")
        return artifact.to_dict()


# ---------------------------------------------------------------------------
# arq job function
# ---------------------------------------------------------------------------


async def run_video_job(
    ctx: dict[str, Any],
    job_id: str,
    prompt: str,
    duration_s: int = 10,
    keyframe_url: str | None = None,
) -> dict[str, Any]:
    """arq entry point — runs VideoGenerationJob."""
    return await VideoGenerationJob(
        job_id=job_id,
        ctx=ctx,
        prompt=prompt,
        duration_s=duration_s,
        keyframe_url=keyframe_url,
    ).run()
