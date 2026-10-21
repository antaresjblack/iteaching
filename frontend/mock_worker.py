"""模拟 AI Worker：驱动「处理/转写 → 基础评价」环节，供前端联调使用。

仅使用 Python 标准库（无需 pip 安装依赖）。协议见
backend/docs/ai-worker-integration.md。

用法（环境变量 AI_SERVICE_TOKEN 需与后端 .env 一致）：

    $env:AI_SERVICE_TOKEN = "你的服务令牌"   # PowerShell
    python mock_worker.py

默认轮询 http://127.0.0.1:8000/api/v1，可用环境变量 API_BASE_URL 覆盖。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1")
SERVICE_TOKEN = os.environ.get("AI_SERVICE_TOKEN", "")
POLL_INTERVAL_SECONDS = 5
SIMULATED_PROCESS_SECONDS = 10


def request(method: str, path: str, body: object = None, headers: dict[str, str] | None = None) -> object:
    url = API_BASE_URL + path
    data = None
    merged = {"Accept": "application/json", **({"X-Service-Token": SERVICE_TOKEN} if SERVICE_TOKEN else {}), **(headers or {})}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        merged["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=merged, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        print(f"  [!] HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
        raise


def download_audio(task_id: str, claim_token: str) -> int:
    """凭领取令牌下载原始音频，验证双头协议后丢弃（返回字节数）。"""
    url = f"{API_BASE_URL}/internal/tasks/{task_id}/audio"
    req = urllib.request.Request(
        url,
        headers={"X-Service-Token": SERVICE_TOKEN, "X-Task-Claim-Token": claim_token},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        content = response.read()
        print(f"  -> 已下载音频 {len(content)} 字节")
        return len(content)


def build_fake_result() -> dict:
    """mode=basic 的基础评价；不携带 segments，避免模拟时长超过真实录音时长。"""
    return {
        "version": 1,
        "mode": "basic",
        "transcript": "教师：同学们好，今天我们继续学习第三章的内容。"
        "先回顾上次课的重点，再通过一组练习检查掌握情况。"
        "（模拟转写文本，真实内容由 AI 处理进程生成）",
        "segments": [],
        "overall_score": 78,
        "overall_evidence": "教学目标明确，讲解清晰，课堂互动较好；后测环节覆盖略不足。",
        "problems": ["后测环节覆盖不够充分"],
        "dimension_scores": {},
        "suggestions": [{"text": "建议增加覆盖不同难度层次的后测题目。"}],
    }


def process_task(task: dict) -> None:
    task_id = task["task_id"]
    claim_token = task["claim_token"]
    print(f"[worker] 领到任务 {task_id}（第 {task['attempt']} 次尝试），模拟处理中…")
    try:
        download_audio(task_id, claim_token)
    except Exception as exc:  # 音频下载失败不阻塞流程，仅提示
        print(f"  [!] 音频下载失败（忽略）：{exc}")
    time.sleep(SIMULATED_PROCESS_SECONDS)
    headers = {"X-Task-Claim-Token": claim_token}
    result = request("POST", f"/internal/tasks/{task_id}/result", build_fake_result(), headers)
    print(f"  -> 已回传结果：{json.dumps(result, ensure_ascii=False)}")


def main() -> None:
    if not SERVICE_TOKEN:
        print("请先设置环境变量 AI_SERVICE_TOKEN（与后端 .env 保持一致）")
        raise SystemExit(1)
    print(f"[worker] 启动，轮询 {API_BASE_URL}/internal/tasks/claim（每 {POLL_INTERVAL_SECONDS}s）")
    while True:
        try:
            claim = request("POST", "/internal/tasks/claim", {"worker_id": "mock-worker-01"})
            task = (claim or {}).get("data")
            if task:
                process_task(task)
        except Exception as exc:  # 网络/协议错误不影响继续轮询
            print(f"[worker] 本轮失败（继续轮询）：{exc}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
