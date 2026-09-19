from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.ai.interfaces.speaker import SpeakerSegment


@dataclass(frozen=True, slots=True)
class BOPPPSAnalysisResult:
    overall_score: float
    dimension_scores: Mapping[str, float]
    evidence: tuple[str, ...]
    problems: tuple[str, ...]


class BOPPPSAnalysisInterface(ABC):
    @abstractmethod
    async def analyze(
        self,
        transcript: str,
        speaker_segments: Sequence[SpeakerSegment],
    ) -> BOPPPSAnalysisResult:
        """Evaluate classroom content across the six BOPPPS dimensions."""
