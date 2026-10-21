"""Aliyun ASR: local WAV via SDK and URL-based asynchronous transcription."""
import json
import math
import os
import re
import wave
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .config import api_key, load_env
from .provider import ProviderError


def normalize_sentences(sentences):
    if not isinstance(sentences, list):
        raise ProviderError('转写结果缺少句子列表')
    segments = []
    for sentence in sentences:
        if not isinstance(sentence, dict):
            raise ProviderError('转写句子格式错误')
        text = sentence.get('text')
        if not isinstance(text, str) or not text.strip():
            continue
        start, end = sentence.get('begin_time'), sentence.get('end_time')
        if not all(type(n) in (int, float) and math.isfinite(n) for n in (start, end)) or not 0 <= start < end:
            raise ProviderError('转写时间戳不完整，不能生成可靠的课堂证据')
        segments.append({'start_seconds': start / 1000, 'end_seconds': end / 1000, 'text': text})
    if not segments:
        raise ProviderError('未识别到有效语音，请检查录音')
    segments.sort(key=lambda s: s['start_seconds'])
    for i, segment in enumerate(segments, 1):
        segment['id'] = 's' + str(i)
    return {'segments': segments, 'text': '\n'.join(s['text'] for s in segments), 'demo': False}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ProviderError('转写结果下载不允许重定向')


def download_result(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.aliyuncs.com') or parsed.username or parsed.port not in (None, 443):
        raise ProviderError('转写结果下载地址不是允许的阿里云HTTPS地址')
    try:
        # Deliberately no Authorization header on the signed result URL.
        with build_opener(NoRedirect()).open(Request(url), timeout=60) as response:
            raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ProviderError('转写结果过大')
        return json.loads(raw)
    except ProviderError:
        raise
    except Exception:
        raise ProviderError('转写结果下载或解析失败，请重试查询') from None


def error_code(value):
    code = value.get('code', '') if isinstance(value, dict) else getattr(value, 'code', '')
    return code if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', code) else 'unavailable'


class AliyunASR:
    def __init__(self, sdk=None):
        load_env()
        key = api_key()
        if sdk is None:
            try:
                import dashscope as sdk
            except ImportError:
                raise ProviderError('请先运行 python -m pip install -r requirements.txt') from None
        self.sdk = sdk
        self.key = key
        sdk.base_http_api_url = os.getenv('DASHSCOPE_HTTP_BASE_URL', 'https://dashscope.aliyuncs.com/api/v1')
        sdk.base_websocket_api_url = os.getenv('DASHSCOPE_WEBSOCKET_BASE_URL', 'wss://dashscope.aliyuncs.com/api-ws/v1/inference')
        if not sdk.base_http_api_url.startswith('https://') or not sdk.base_websocket_api_url.startswith('wss://'):
            raise ValueError('语音服务地址必须使用HTTPS/WSS')

    @staticmethod
    def check(response):
        if response.status_code != 200:
            raise ProviderError('阿里云语音请求失败，HTTP ' + str(response.status_code) + '；code=' + error_code(response))

    def transcribe_file(self, filename):
        """Trusted Python/CLI only; never accept arbitrary local paths via HTTP."""
        path = Path(filename)
        if path.suffix.lower() != '.wav' or not path.is_file():
            raise ValueError('本地转写请提供存在的单声道16位PCM WAV文件')
        if path.stat().st_size > 200_000_000:
            raise ValueError('本地录音超过200MB，请使用URL异步转写')
        try:
            with wave.open(str(path), 'rb') as audio:
                rate = audio.getframerate()
                if rate <= 0 or audio.getnframes() <= 0:
                    raise ValueError('录音为空或采样率无效')
                if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
                    raise ValueError('本地WAV需为单声道16位PCM格式')
        except (wave.Error, EOFError):
            raise ValueError('无法读取PCM WAV文件') from None
        try:
            from dashscope.audio.asr import Recognition
            recognition = Recognition(model=os.getenv('ITEACHING_LOCAL_ASR_MODEL', 'paraformer-realtime-v2'),
                                      format='wav', sample_rate=rate, language_hints=['zh', 'en'],
                                      callback=None, api_key=self.key)
            response = recognition.call(str(path))
            self.check(response)
            return normalize_sentences(response.get_sentence())
        except (ProviderError, ValueError):
            raise
        except Exception:
            raise ProviderError('本地音频转写调用失败，请检查网络、SDK及模型权限') from None

    def submit(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('audio_url'), str):
            raise ValueError('请提供audio_url')
        url = data['audio_url']
        p = urlparse(url)
        if p.scheme not in ('https', 'http') or not p.hostname or p.username:
            raise ValueError('audio_url必须是云端可访问的HTTP(S)音频链接')
        try:
            from dashscope.audio.asr import Transcription
            r = Transcription.async_call(model=os.getenv('ITEACHING_ASR_MODEL', 'paraformer-v2'),
                                         file_urls=[url], language_hints=['zh', 'en'],
                                         timestamp_alignment_enabled=True, api_key=self.key, request_timeout=30)
            self.check(r)
            return {'task_id': r.output['task_id'], 'status': r.output['task_status']}
        except (ProviderError, ValueError):
            raise
        except Exception:
            raise ProviderError('转写任务提交失败；请勿在未确认状态时反复提交') from None

    def fetch(self, data):
        task = data.get('task_id') if isinstance(data, dict) else None
        if not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', task):
            raise ValueError('task_id格式无效')
        try:
            from dashscope.audio.asr import Transcription
            r = Transcription.fetch(task=task, api_key=self.key, request_timeout=30)
            self.check(r)
            status = r.output['task_status']
            result = {'task_id': task, 'status': status}
            if status == 'SUCCEEDED':
                records = r.output.get('results', [])
                if len(records) != 1 or records[0].get('subtask_status') != 'SUCCEEDED':
                    raise ProviderError('音频子任务失败或结果缺失；code=' + (error_code(records[0]) if records else 'missing_result'))
                document = download_result(records[0]['transcription_url'])
                sentences = [s for t in document['transcripts'] for s in t['sentences']]
                result.update(normalize_sentences(sentences))
            elif status in ('FAILED', 'CANCELED', 'UNKNOWN'):
                result['error'] = '转写任务状态=' + status + '；code=' + error_code(r.output)
            elif status not in ('PENDING', 'RUNNING'):
                raise ProviderError('未知转写任务状态')
            return result
        except (ProviderError, ValueError):
            raise
        except Exception:
            raise ProviderError('转写查询失败或响应不完整') from None
