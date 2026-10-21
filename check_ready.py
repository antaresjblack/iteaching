"""Local readiness check. No paid API requests and no secret output."""
import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def values(path):
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, sep, value = line.partition('=')
        if sep and not key.strip().startswith('#'):
            result[key.strip()] = value.strip().strip('\"\'')
    return result


def main():
    ai = values(ROOT / '.env')
    back = values(ROOT / 'backend' / '.env')
    checks = []
    for module in ('dashscope', 'fastapi', 'sqlalchemy', 'alembic', 'jwt'):
        checks.append((module, importlib.util.find_spec(module) is not None))
    key = ai.get('DASHSCOPE_API_KEY', '')
    checks.extend([
        ('Aliyun key configured (validity unverified)', bool(key) and key != 'your-api-key'),
        ('Worker token matches backend', bool(ai.get('AI_SERVICE_TOKEN')) and ai.get('AI_SERVICE_TOKEN') == back.get('AI_SERVICE_TOKEN')),
        ('Admin password configured', len(back.get('INITIAL_ADMIN_PASSWORD', '')) >= 12),
        ('ffmpeg', shutil.which('ffmpeg') is not None),
        ('ffprobe', shutil.which('ffprobe') is not None),
    ])
    if ai.get('AI_AUDIO_STORAGE') == 'oss':
        checks.append(('OSS SDK', importlib.util.find_spec('oss2') is not None))
        for key in ('OSS_BUCKET_NAME', 'OSS_REGION', 'OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET'):
            checks.append((key + ' configured (validity unverified)', bool(ai.get(key))))
    for name, ok in checks:
        print(('OK   ' if ok else 'TODO ') + name)
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
