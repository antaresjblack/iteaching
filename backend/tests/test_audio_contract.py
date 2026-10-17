import json
import os
import subprocess

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.business import EvaluationResultInput
from app.services.recordings import probe_audio
from app.services.storage import ensure_private_directory, open_private_file


def test_probe_rejects_a_fake_audio_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_path = tmp_path / "lesson.wav"
    fake_path.write_bytes(b"not an audio stream")
    monkeypatch.setattr(
        "app.services.recordings.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, b"", b"invalid"),
    )

    with pytest.raises(HTTPException) as error:
        probe_audio(fake_path, ".wav")

    assert error.value.status_code == 415


def test_probe_rejects_extension_that_does_not_match_media(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio_path = tmp_path / "lesson.mp3"
    audio_path.write_bytes(b"container mismatch")
    metadata = json.dumps({"format": {"format_name": "wav", "duration": "3.0"}}).encode()
    monkeypatch.setattr(
        "app.services.recordings.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, metadata, b""),
    )

    with pytest.raises(HTTPException) as error:
        probe_audio(audio_path, ".mp3")

    assert error.value.status_code == 415


def test_probe_rejects_video_only_container_named_as_audio(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "lesson.m4a"
    video_path.write_bytes(b"video-only container")
    metadata = json.dumps(
        {
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "3.0"},
            "streams": [{"codec_type": "video"}],
        }
    ).encode()
    monkeypatch.setattr(
        "app.services.recordings.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, metadata, b""),
    )

    with pytest.raises(HTTPException) as error:
        probe_audio(video_path, ".m4a")

    assert error.value.status_code == 415


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are not available on Windows")
def test_private_storage_uses_owner_only_permissions(tmp_path) -> None:
    directory = tmp_path / "private"
    ensure_private_directory(directory)
    stored_file = directory / "audio.upload"
    with open_private_file(stored_file) as destination:
        destination.write(b"audio")

    assert directory.stat().st_mode & 0o777 == 0o700
    assert stored_file.stat().st_mode & 0o777 == 0o600


def test_boppps_result_requires_six_bounded_scores() -> None:
    with pytest.raises(ValidationError):
        EvaluationResultInput(
            version=1,
            mode="boppps",
            transcript="课堂转写",
            overall_score=70,
            overall_evidence="课堂目标清楚",
            dimension_scores={"bridge_in": 70},
        )
