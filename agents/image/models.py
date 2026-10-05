from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageArtifact:
    artifact_id: str
    url: str
    width: int
    height: int
    prompt: str
    artifact_type: str = field(default="image")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "prompt": self.prompt,
            "artifact_type": self.artifact_type,
        }
