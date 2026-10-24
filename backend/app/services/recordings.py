from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

from fastapi import HTTPException, status

from app.models import Evaluation
from app.schemas.business import DIMENSION_KEYS

_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_CN_ID_RE = re.compile(
    r"(?<![0-9A-Za-z])[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?![0-9A-Za-z])"
)

DIMENSION_LABELS = {
    "bridge_in": "导入环节",
    "objectives": "教学目标",
    "pre_assessment": "前测环节",
    "participatory_learning": "参与式学习",
    "post_assessment": "后测环节",
    "summary": "总结环节",
}


def probe_audio(path: Path, extension: str) -> float:
    """Use ffprobe to validate the actual media container and obtain its duration."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=format_name,duration:stream=codec_type",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, check=False, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audio validation is temporarily unavailable",
        ) from exc
    if completed.returncode != 0:
        raise HTTPException(
            status_code=415, detail="Uploaded file is not a valid supported audio file"
        )
    try:
        metadata = json.loads(completed.stdout)
        format_names = set(str(metadata["format"]["format_name"]).split(","))
        duration = float(metadata["format"]["duration"])
        streams = metadata["streams"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=415, detail="Unable to read audio metadata") from exc

    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams
    ):
        raise HTTPException(
            status_code=415, detail="Uploaded media does not contain an audio stream"
        )

    accepted_formats = {
        ".wav": {"wav"},
        ".mp3": {"mp3"},
        ".m4a": {"mov", "mp4", "m4a"},
    }
    if extension not in accepted_formats or not format_names.intersection(
        accepted_formats[extension]
    ):
        raise HTTPException(
            status_code=415, detail="File extension does not match supported audio format"
        )
    if not math.isfinite(duration) or duration <= 0:
        raise HTTPException(status_code=415, detail="Audio duration must be greater than zero")
    return duration


def redact_text(text: str) -> str:
    """Basic output masking; this intentionally does not claim to find all personal data."""
    text = _EMAIL_RE.sub("[邮箱已遮蔽]", text)
    text = _PHONE_RE.sub("[手机号已遮蔽]", text)
    return _CN_ID_RE.sub("[身份证号已遮蔽]", text)


def effective_scores(evaluation: Evaluation) -> tuple[float | None, dict[str, float | None]]:
    dimensions = {item.dimension: item.score for item in evaluation.dimension_scores}
    overall = evaluation.overall_score
    explicit_overall = False
    for calibration in sorted(evaluation.calibrations, key=lambda item: item.id, reverse=True):
        if calibration.overall_score is not None:
            overall = calibration.overall_score
            explicit_overall = True
            break
        if calibration.dimension_scores:
            # 较新的维度调整取代旧人工总分；纯评语不影响评分优先级。
            break
    for dimension in DIMENSION_KEYS:
        for calibration in sorted(evaluation.calibrations, key=lambda item: item.id, reverse=True):
            if calibration.dimension_scores and dimension in calibration.dimension_scores:
                dimensions[dimension] = calibration.dimension_scores[dimension]
                break
    # 最新评分操作指定总分时优先；否则从完整的生效六维计算。
    if not explicit_overall and any(item.dimension_scores for item in evaluation.calibrations):
        scores = [dimensions.get(key) for key in DIMENSION_KEYS]
        overall = (
            round(sum(scores) / len(scores), 2)
            if all(score is not None for score in scores)
            else None
        )
    return overall, dimensions


def build_suggestions(evaluation: Evaluation) -> list[dict[str, str]]:
    if evaluation.suggestions:
        return [
            {"text": redact_text(item.text), "source": item.source}
            for item in evaluation.suggestions
        ]
    problem_texts = [
        str(item.get("description", "")) if isinstance(item, dict) else str(item)
        for item in evaluation.problems
    ]
    suggestions = [
        {
            "text": f"针对“{redact_text(problem)}”，建议在下次课堂设计中增加相应的练习与即时反馈。",
            "source": "rule",
        }
        for problem in problem_texts
    ]
    scored_dimensions = sorted(
        (
            item
            for item in evaluation.dimension_scores
            if item.score is not None and item.score < 60 and item.dimension in DIMENSION_LABELS
        ),
        key=lambda item: (item.score, item.dimension),
    )
    suggestions.extend(
        {
            "text": (
                f"建议重点改进{DIMENSION_LABELS[item.dimension]}，加入明确的课堂活动、"
                "检查点和学习反馈。"
            ),
            "source": "rule",
        }
        for item in scored_dimensions
    )
    return suggestions[:3]


def serialize_evaluation(evaluation: Evaluation) -> dict[str, object]:
    effective_overall, effective_dimensions = effective_scores(evaluation)
    observed = [
        item["score"]
        for item in evaluation.raw_result.get("indicators", [])
        if item.get("status") == "evaluated" and item.get("score") is not None
    ]
    return {
        "observed_score": round(sum(observed) / len(observed), 2) if observed else None,
        "observed_count": len(observed),
        "dimension_count": 6,
        "id": evaluation.id,
        "recording_id": evaluation.recording_id,
        "uploaded_by_role": evaluation.recording.uploaded_by_role,
        "uploaded_by_id": evaluation.recording.uploaded_by_id,
        "version": evaluation.version,
        "mode": evaluation.mode,
        "rubric_version": evaluation.raw_result.get("rubric_version") or "legacy-v1",
        "indicators": [
            {
                **item,
                "reason": redact_text(item["reason"]),
                "evidence": [{**e, "quote": redact_text(e["quote"])} for e in item["evidence"]],
            }
            for item in evaluation.raw_result.get("indicators", [])
        ],
        "model_dimension_scores": {
            item.dimension: item.score for item in evaluation.dimension_scores
        },
        "transcript": redact_text(evaluation.transcript),
        "segments": [
            {
                "start_seconds": item.start_seconds,
                "end_seconds": item.end_seconds,
                "text": redact_text(item.text),
                "speaker_id": item.speaker_id,
                "role": item.role,
            }
            for item in evaluation.segments
        ],
        "overall_score": effective_overall,
        "model_overall_score": evaluation.overall_score,
        "overall_evidence": redact_text(evaluation.overall_evidence),
        "problems": [
            (
                redact_text(str(item.get("description", "")))
                if isinstance(item, dict)
                else redact_text(str(item))
            )
            for item in evaluation.problems
        ],
        "dimension_scores": effective_dimensions,
        "suggestions": build_suggestions(evaluation),
        "reviews": [
            {"id": item.id, "comment": redact_text(item.comment), "created_at": item.created_at}
            for item in sorted(evaluation.reviews, key=lambda item: item.id)
        ],
        "calibrations": [
            {
                "id": item.id,
                "calibrated_by_role": item.calibrated_by_role,
                "calibrated_by_id": item.calibrated_by_id,
                "overall_score": item.overall_score,
                "dimension_scores": item.dimension_scores,
                "comment": redact_text(item.comment or ""),
                "created_at": item.created_at,
            }
            for item in sorted(evaluation.calibrations, key=lambda item: item.id)
        ],
    }
