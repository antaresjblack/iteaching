"""音频准入与结果契约测试。

覆盖三条防线：
1. probe_audio 调用 ffprobe 校验上传文件确实是音频——伪造音频、扩展名与
   真实封装格式不符、纯视频容器伪装成音频，一律拒绝（415）；
2. 私有存储目录/文件权限必须为仅属主可读写（0o700/0o600，仅 POSIX 有效）；
3. AI Worker 回传的 BOPPPS 评价结果必须包含六个维度的有界分数，
   维度缺失直接在 schema 层校验失败。
"""

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
    """ffprobe 无法解析的伪造音频文件被拒绝（415 Unsupported Media Type）。"""
    fake_path = tmp_path / "lesson.wav"
    fake_path.write_bytes(b"not an audio stream")
    # 模拟 ffprobe 以非零退出码失败返回
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
    """扩展名为 .mp3 但真实封装为 wav 的文件被拒绝（防止改后缀绕过校验）。"""
    audio_path = tmp_path / "lesson.mp3"
    audio_path.write_bytes(b"container mismatch")
    metadata = json.dumps({"format": {"format_name": "wav", "duration": "3.0"}}).encode()
    # 模拟 ffprobe 成功返回元数据：真实格式 wav 与声明的 .mp3 不符
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
    """纯视频容器（无音频流）改名为 .m4a 后被拒绝。"""
    video_path = tmp_path / "lesson.m4a"
    video_path.write_bytes(b"video-only container")
    metadata = json.dumps(
        {
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "3.0"},
            "streams": [{"codec_type": "video"}],  # 只有视频流，没有音频流
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
    """录音私有目录权限为 0o700、文件权限为 0o600（仅属主可访问）。"""
    directory = tmp_path / "private"
    ensure_private_directory(directory)
    stored_file = directory / "audio.upload"
    with open_private_file(stored_file) as destination:
        destination.write(b"audio")

    assert directory.stat().st_mode & 0o777 == 0o700
    assert stored_file.stat().st_mode & 0o777 == 0o600


def test_boppps_result_requires_six_bounded_scores() -> None:
    """BOPPPS 评价结果缺少任一维度分数时，schema 校验直接失败。"""
    with pytest.raises(ValidationError):
        EvaluationResultInput(
            version=1,
            mode="boppps",
            transcript="课堂转写",
            overall_score=70,
            overall_evidence="课堂目标清楚",
            # 仅给一个维度，缺少其余五个——应触发 ValidationError
            dimension_scores={"bridge_in": 70},
        )
