"""Backend task consumer. Run from AI project: python -m iteaching_ai.worker --once."""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import ExitStack
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, ProxyHandler, build_opener

from .asr import AliyunASR, NoRedirect
from .oss_audio import OSSAudio
from .config import load_env
from .diagnostics import Journal, safe_detail
from .provider import ProviderError
from .service import AIService, validate_input, validate_evaluation


class BackendError(Exception):
    def __init__(self, status=None):
        self.status = status
        super().__init__('后端请求失败' + (f'，HTTP {status}' if status else '，网络错误或响应异常'))


class BackendClient:
    def __init__(self, base_url, token):
        self.base = base_url.rstrip('/')
        p = urlparse(self.base)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.query or p.fragment or p.path not in ('', '/'):
            raise ValueError('AI_BACKEND_URL必须是后端根地址，例如http://127.0.0.1:8000')
        if p.scheme == 'http' and p.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('非本机后端必须使用HTTPS')
        if not token:
            raise ValueError('请配置与后端一致的AI_SERVICE_TOKEN')
        self.token = token
        # Backend credentials never go through an ambient VPN proxy or redirect.
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path, body=None, claim=None, destination=None):
        if not path.startswith('/api/v1/internal/tasks/') or '://' in path or '..' in path or '?' in path:
            raise ValueError('仅允许访问后端内部任务路径')
        headers = {'X-Service-Token': self.token}
        if claim:
            headers['X-Task-Claim-Token'] = claim
        payload = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf8')
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(self.base + path, data=payload, headers=headers)
        try:
            with self.opener.open(req, timeout=30) as response:
                if destination is not None:
                    total = 0
                    with Path(destination).open('wb') as file:
                        while chunk := response.read(1024 * 1024):
                            total += len(chunk)
                            if total > 500 * 1024 * 1024:
                                raise ValueError('录音超过500MB')
                            file.write(chunk)
                    if total == 0:
                        raise ValueError('下载的录音为空')
                    return None
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise BackendError()
                result = json.loads(raw)
                if result.get('code') != 0 or 'data' not in result:
                    raise BackendError()
                return result['data']
        except HTTPError as exc:
            raise BackendError(exc.code) from None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise BackendError() from None


class Lease:
    def __init__(self, client, task):
        self.client, self.task = client, task
        self.stop = threading.Event()
        self.lost = threading.Event()
        expires = datetime.fromisoformat(task['lease_expires_at'].replace('Z', '+00:00'))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        remaining = (expires - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise BackendError(409)
        self.interval = max(1, min(30, remaining / 3))
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop.wait(self.interval):
            try:
                self.client.request(f"/api/v1/internal/tasks/{self.task['task_id']}/lease", {}, self.task['claim_token'])
            except Exception:
                self.lost.set()
                return

    def ensure(self):
        if self.lost.is_set():
            raise BackendError(409)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=31)


def convert_audio(source, destination):
    executable = shutil.which('ffmpeg')
    if not executable:
        raise ValueError('缺少FFmpeg，请安装并加入PATH')
    try:
        result = subprocess.run([executable, '-nostdin', '-v', 'error', '-y', '-i', str(source),
                                 '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(destination)],
                                capture_output=True, timeout=180, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError('音频格式转换超时') from None
    if result.returncode != 0:
        raise ValueError('音频格式转换失败')


def backend_result(transcript, evaluation, suggestions):
    validate_evaluation(evaluation)
    if evaluation['demo'] or suggestions.get('demo'):
        raise ValueError('不能将演示结果写入业务后端')
    dimensions = {i['id']: i['score'] for i in evaluation['indicators']}
    scores = list(dimensions.values())
    overall = round(sum(scores) / 6, 2) if all(s is not None for s in scores) else None
    # Normalize IDs because the v2 API identifies segments by their 1-based order.
    id_map = {s['id']: f's{n}' for n, s in enumerate(transcript['segments'], 1)}
    indicators = [
        {**{k: v for k, v in item.items() if k != 'problems'}, 'evidence': [{**e, 'segment_id': id_map[e['segment_id']]} for e in item['evidence']]}
        for item in evaluation['indicators']
    ]
    return {
        'version': 2, 'mode': 'boppps', 'rubric_version': evaluation['rubric_version'],
        'indicators': indicators, 'transcript': '\n'.join(s['text'] for s in transcript['segments']),
        'segments': [{k: s[k] for k in ('start_seconds', 'end_seconds', 'text')} | {'role': 'unknown'}
                     for s in transcript['segments']],
        'overall_score': overall, 'overall_evidence': evaluation['summary'] + (('\n建议状态：' + '；'.join(suggestions.get('warnings', []))) if suggestions.get('warnings') else ''),
        'dimension_scores': dimensions,
        'problems': list(dict.fromkeys('【' + {'bridge_in': '导入', 'objectives': '教学目标', 'pre_assessment': '前测', 'participatory_learning': '参与式学习', 'post_assessment': '后测', 'summary': '总结'}.get(item['id'], '教学评价') + '】' + problem['description']
                        for item in evaluation['indicators'] for problem in item.get('problems', []))),
        'suggestions': [{'text': f"【{dict(high='高优先级', medium='中优先级', low='低优先级').get(s['priority'], '改进建议')}】{s['action']}；验证方式：{s['verification']}"}
                        for s in suggestions['suggestions']],
    }


def run_once(client, asr, ai, worker_id, converter=convert_audio):
    storage_mode = os.getenv('AI_AUDIO_STORAGE', 'signed_backend')
    if storage_mode not in ('oss', 'signed_backend'):
        raise ValueError('AI_AUDIO_STORAGE 必须为 oss 或 signed_backend')
    storage = OSSAudio() if storage_mode == 'oss' else None
    if storage is None:
        client.request('/api/v1/internal/tasks/audio-config')
    task = client.request('/api/v1/internal/tasks/claim', {'worker_id': worker_id})
    if task is None:
        return 'idle'
    print(f"Worker：已领取任务 {task['task_id']}", flush=True)
    prefix = f"/api/v1/internal/tasks/{task['task_id']}"
    claim = task['claim_token']
    journal = Journal(task['task_id'])
    stage = '准备音频链接'
    cloud_id = None
    with Lease(client, task) as lease, ExitStack() as cleanup:
        try:
            journal.event(stage)
            # Metadata comes from the backend, never invented by the worker.
            if not all(k in task for k in ('course_id', 'recorded_at', 'duration_seconds')):
                raise ValueError('后端缺少课程/录制日期/时长，请更新到v2契约')
            if journal.marker.exists():
                raise ValueError('此任务已有提交记录，已阻止重复付费提交；请先核对云端任务')
            if storage is not None:
                stage = '上传录音到OSS'
                journal.event(stage)
                key = storage.new_key(task['original_filename'])
                journal.event('OSS临时对象', object_key=key)
                cleanup.callback(storage.cleanup, key, journal)
                with tempfile.TemporaryDirectory(prefix='iteaching-oss-') as directory:
                    source = Path(directory) / 'audio'
                    client.request(task['audio_url'], claim=claim, destination=source)
                    lease.ensure()
                    signed = storage.upload(key, source)
            else:
                signed = client.request(prefix + '/audio-url', {}, claim)
            lease.ensure()
            print('Worker：正在提交异步转写', flush=True)
            stage = '提交转写'
            journal.before_submit()
            journal.event(stage)
            submitted = asr.submit({'audio_url': signed['audio_url']})
            cloud_id = submitted['task_id']
            journal.event('转写已提交', cloud_task_id=cloud_id)
            stage = '查询转写或下载转写结果'
            deadline = time.monotonic() + min(3600, signed['expires'] - time.time() - 60)
            print(f"Worker：云端转写任务 {submitted['task_id']} 已提交", flush=True)
            query_errors = 0
            last_report = -60
            while True:
                lease.ensure()
                if time.monotonic() >= deadline:
                    raise ValueError('异步转写等待超时')
                try:
                    transcript = asr.fetch({'task_id': submitted['task_id']})
                    query_errors = 0
                except ProviderError:
                    query_errors += 1
                    if query_errors >= 3:
                        raise
                    time.sleep(5)
                    continue
                if time.monotonic() - last_report >= 30:
                    journal.event(stage, cloud_task_id=cloud_id, status=transcript['status'])
                    last_report = time.monotonic()
                if transcript['status'] == 'SUCCEEDED':
                    break
                if transcript['status'] not in ('PENDING', 'RUNNING'):
                    raise ProviderError(transcript.get('error', '异步转写任务失败'))
                time.sleep(5)
            lease.ensure()
            stage = '校验转写'
            journal.event(stage, cloud_task_id=cloud_id)
            for s in transcript['segments']:
                if s['end_seconds'] > task['duration_seconds'] + 0.1:
                    raise ValueError('转写时间戳超出原录音时长')
                s['end_seconds'] = min(s['end_seconds'], task['duration_seconds'])
            data = {'course_id': str(task['course_id']), 'lesson_id': task['recording_id'],
                    'taught_at': datetime.fromisoformat(task['recorded_at'].replace('Z', '+00:00')).date().isoformat(),
                    'segments': transcript['segments']}
            validate_input(data)
            journal.save_artifact('transcript', data)
            print('Worker：转写完成，正在生成教学评价', flush=True)
            stage = '生成教学评价'
            journal.event(stage, cloud_task_id=cloud_id)
            evaluation = ai.evaluate(data)
            journal.save_artifact('evaluation', evaluation)
            lease.ensure()
            print('Worker：正在生成改进建议', flush=True)
            stage = '生成改进建议'
            journal.event(stage, cloud_task_id=cloud_id)
            try:
                suggestions = ai.suggest({'evaluation': evaluation})
            except ProviderError as exc:
                journal.event('建议不可用，保留已完成评价', detail=safe_detail(exc))
                suggestions = {'demo': False, 'suggestions': [], 'status': 'unavailable',
                               'warnings': ['改进建议暂不可用，转写与教学评价已保留，请人工复核。']}
            journal.save_artifact('suggestions', suggestions)
            result = backend_result(transcript, evaluation, suggestions)
            journal.save_artifact('backend-result', result)
        except Exception as exc:
            if lease.lost.is_set() or isinstance(exc, BackendError) and exc.status == 409:
                return 'lease_lost'
            # No raw model output, signed URL or credentials in the failure message.
            detail = safe_detail(exc) if isinstance(exc, (ProviderError, ValueError, BackendError)) else type(exc).__name__
            reason = f'{stage}失败：{detail}'
            journal.event('失败', failed_stage=stage, detail=detail, cloud_task_id=cloud_id)
            try:
                client.request(prefix + '/failure', {'reason': reason, 'retryable': False}, claim)
            except BackendError:
                return 'failure_unconfirmed'
            return 'failed'
        # Retry the exact same result on uncertain delivery; do not rescore or mark failure.
        for attempt in range(3):
            try:
                lease.ensure()
                journal.event('保存结果', cloud_task_id=cloud_id)
                client.request(prefix + '/result', result, claim)
                journal.event('完成', cloud_task_id=cloud_id)
                return 'succeeded'
            except BackendError as exc:
                if exc.status == 409 or lease.lost.is_set():
                    return 'lease_lost'
                if exc.status is not None and exc.status < 500:
                    # Validation errors are definitive; allow the backend retry policy.
                    if exc.status == 422:
                        client.request(prefix + '/failure', {'reason': 'AI结果不符合后端v2契约', 'retryable': False}, claim)
                    return 'result_rejected'
                if attempt < 2:
                    time.sleep(1)
        return 'delivery_unconfirmed'


def main():
    parser = argparse.ArgumentParser(description='AI Worker：真实转写、评价及建议会调用阿里云付费API')
    parser.add_argument('--once', action='store_true', help='最多领取一个任务后退出')
    args = parser.parse_args()
    load_env()
    try:
        client = BackendClient(os.getenv('AI_BACKEND_URL', 'http://127.0.0.1:8000'), os.getenv('AI_SERVICE_TOKEN', ''))
        asr, ai = AliyunASR(), AIService(mode='live')
        worker_id = os.getenv('AI_WORKER_ID', 'aliyun-worker-01')
        print('Worker：已启动，检查待处理任务', flush=True)
        last_status = None
        while True:
            result = run_once(client, asr, ai, worker_id)
            if result != last_status or result != 'idle':
                print('Worker状态：' + result, flush=True)
            last_status = result
            if args.once or result not in ('idle', 'succeeded'):
                return
            time.sleep(5)
    except KeyboardInterrupt:
        return
    except (ValueError, BackendError, ProviderError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
