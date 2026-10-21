"""Minimal .env loader. Environment variables take precedence; never print secrets."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path=None):
    path = Path(path) if path else ROOT / '.env'
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            raise ValueError('.env格式错误：每行必须为变量名=值')
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
        os.environ.setdefault(key, value)


def api_key():
    key = os.getenv('DASHSCOPE_API_KEY') or os.getenv('ITEACHING_API_KEY', '')
    if not key or key == 'your-api-key':
        raise ValueError('请在项目.env中填写DASHSCOPE_API_KEY')
    return key
