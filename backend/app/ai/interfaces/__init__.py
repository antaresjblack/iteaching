from app.ai.interfaces.asr import ASRInterface, TranscriptionResult, TranscriptionSegment
from app.ai.interfaces.boppps import BOPPPSAnalysisInterface, BOPPPSAnalysisResult
from app.ai.interfaces.speaker import SpeakerRecognitionInterface, SpeakerSegment
from app.ai.interfaces.suggestion import SuggestionGenerationInterface

__all__ = [
    "ASRInterface",
    "BOPPPSAnalysisInterface",
    "BOPPPSAnalysisResult",
    "SpeakerRecognitionInterface",
    "SpeakerSegment",
    "SuggestionGenerationInterface",
    "TranscriptionResult",
    "TranscriptionSegment",
]
