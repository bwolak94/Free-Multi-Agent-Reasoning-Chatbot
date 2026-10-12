from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VideoArtifact:
    artifact_id: str
    url: str
    prompt: str
    duration_s: int
    artifact_type: str = field(default="video")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "url": self.url,
            "prompt": self.prompt,
            "duration_s": self.duration_s,
            "artifact_type": self.artifact_type,
        }
