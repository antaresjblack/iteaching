"""Durable metadata only: never persist audio, prompts or signed URLs here."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT


def safe_detail(value):
    text = str(value)
    for name in ('DASHSCOPE_API_KEY', 'ITEACHING_API_KEY', 'AI_SERVICE_TOKEN', 'AUDIO_SIGNING_KEY', 'OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET'):
        secret = os.getenv(name)
        if secret:
            text = text.replace(secret, '[redacted]')
    text = re.sub(r'https?://\S+', '[url]', text)
    text = re.sub(r'(?i)(bearer\s+|sk-)[\w.-]+', '[redacted]', text)
    return text.replace('\n', ' ')[:800]


class Journal:
    def __init__(self, task_id):
        root = Path(os.getenv('AI_WORKER_STATE_DIR', str(ROOT / 'runtime' / 'worker')))
        root.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(task_id.encode()).hexdigest()
        self.marker = root / (name + '.submitted')
        self.log = root / (name + '.jsonl')
        self.task_id = task_id

    def event(self, stage, **fields):
        record = {'time': datetime.now(timezone.utc).isoformat(),
                  'task_id': self.task_id, 'stage': stage, **fields}
        with self.log.open('a', encoding='utf-8') as file:
            file.write(json.dumps(record, ensure_ascii=False) + '\n')
            file.flush()
            os.fsync(file.fileno())
        print('Worker：' + json.dumps(record, ensure_ascii=False), flush=True)

    def before_submit(self):
        # Exclusive and durable before the paid request. An uncertain submit must
        # never be silently repeated, even if the process dies before saving its ID.
        try:
            with self.marker.open('x', encoding='utf-8') as file:
                file.write('Submission may have reached cloud; inspect journal before retry.\n')
                file.flush()
                os.fsync(file.fileno())
        except FileExistsError:
            raise ValueError('此任务已有提交记录，已阻止重复付费提交；请先核对云端任务') from None


    def save_artifact(self, name, data):
        if name not in ('transcript', 'evaluation', 'suggestions', 'backend-result'):
            raise ValueError('Invalid checkpoint name')
        directory = self.log.parent / 'artifacts' / self.log.stem
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (name + '.json')
        temporary = directory / (name + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
