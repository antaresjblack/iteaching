from abc import ABC, abstractmethod

from app.ai.interfaces.boppps import BOPPPSAnalysisResult


class SuggestionGenerationInterface(ABC):
    @abstractmethod
    async def generate(self, analysis: BOPPPSAnalysisResult) -> tuple[str, ...]:
        """Generate teaching-improvement suggestions from an evaluation."""
