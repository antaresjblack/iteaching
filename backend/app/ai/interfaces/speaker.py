from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SpeakerRole = Literal["teacher", "student", "unknown"]


@dataclass(frozen=True, slots=True)
class SpeakerSegment:
    speaker_id: str
    role: SpeakerRole
    start_seconds: float
    end_seconds: float
    text: str | None = None


class SpeakerRecognitionInterface(ABC):
    @abstractmethod
    async def diarize(self, audio_path: Path) -> tuple[SpeakerSegment, ...]:
        """Split audio into speaker-attributed segments."""
