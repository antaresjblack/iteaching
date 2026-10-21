"""Private, temporary OSS copies for cloud transcription."""
import os
import re
import time
import uuid
from pathlib import Path

from .provider import ProviderError


class OSSAudio:
    def __init__(self, bucket=None):
        region = os.getenv('OSS_REGION', '').strip()
        name = os.getenv('OSS_BUCKET_NAME', '').strip()
        self.prefix = os.getenv('OSS_AUDIO_PREFIX', 'iteaching-temp/').strip()
        if not re.fullmatch(r'[a-z0-9-]+', region):
            raise ValueError('请配置 OSS_REGION，例如 cn-beijing')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', name):
            raise ValueError('请配置 OSS_BUCKET_NAME')
        if not re.fullmatch(r'[A-Za-z0-9_-]+/', self.prefix):
            raise ValueError('OSS_AUDIO_PREFIX 必须是单层目录，例如 iteaching-temp/')
        self.ttl = 7200
        if bucket is None:
            key = os.getenv('OSS_ACCESS_KEY_ID', '')
            secret = os.getenv('OSS_ACCESS_KEY_SECRET', '')
            if not key or not secret:
                raise ValueError('请在项目 .env 配置 OSS_ACCESS_KEY_ID 和 OSS_ACCESS_KEY_SECRET')
            try:
                import oss2
            except ImportError:
                raise ValueError('缺少 OSS SDK，请安装 requirements.txt 中的依赖') from None
            auth = oss2.AuthV4(key, secret)
            self.bucket = oss2.Bucket(auth, f'https://oss-{region}.aliyuncs.com',
                                      name, region=region, connect_timeout=30)
        else:
            self.bucket = bucket

    def new_key(self, filename):
        extension = Path(filename).suffix.lower()
        if extension not in ('.wav', '.mp3', '.m4a'):
            raise ValueError('OSS 上传音频格式不支持')
        return self.prefix + uuid.uuid4().hex + extension

    def upload(self, key, source):
        try:
            self.bucket.put_object_from_file(key, str(source), headers={
                'x-oss-object-acl': 'private',
                'x-oss-forbid-overwrite': 'true',
                'Content-Type': 'application/octet-stream',
            })
            url = self.bucket.sign_url('GET', key, self.ttl)
            return {'audio_url': url, 'expires': int(time.time()) + self.ttl}
        except Exception as exc:
            code = getattr(exc, 'code', '')
            code = code if isinstance(code, str) and re.fullmatch(r'[\w.-]{1,80}', code) else type(exc).__name__
            raise ProviderError('OSS 上传或签名失败：' + code) from None

    def cleanup(self, key, journal):
        try:
            self.bucket.delete_object(key)
            journal.event('OSS临时文件已清理', object_key=key)
        except Exception:
            # Do not discard a valid assessment because remote cleanup failed.
            journal.event('OSS清理失败，请按对象路径手动清理', object_key=key)
