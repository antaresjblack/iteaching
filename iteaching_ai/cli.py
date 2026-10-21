"""Run with python -m iteaching_ai.cli --help."""
import argparse
import json
from pathlib import Path
from .config import load_env, api_key
from .asr import AliyunASR
from .service import AIService
from .provider import ProviderError


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print('已保存：' + str(path))


def main():
    parser = argparse.ArgumentParser(description='爱教学AI模块；live命令会调用云端并可能产生费用')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check', help='仅检查配置，不发送请求，不输出密钥')
    p = sub.add_parser('transcribe', help='本地单声道16位PCM WAV转写')
    p.add_argument('audio')
    p.add_argument('--output', default='outputs/transcript.json')
    p = sub.add_parser('submit', help='提交音频URL异步转写，保留task_id以免重复计费')
    p.add_argument('url')
    p.add_argument('--output', default='outputs/asr-task.json')
    p = sub.add_parser('query', help='查询任务；完成后返回segments')
    p.add_argument('task_id')
    p.add_argument('--output', default='outputs/transcript.json')
    p = sub.add_parser('analyze', help='转写JSON + 课堂信息 -> 评价及建议')
    p.add_argument('transcript')
    p.add_argument('--metadata', required=True)
    p.add_argument('--output-dir', default='outputs/lesson')
    p = sub.add_parser('compare', help='比较两个或多个评价JSON')
    p.add_argument('evaluations', nargs='+')
    p.add_argument('--output', default='outputs/comparison.json')
    args = parser.parse_args()
    load_env()
    try:
        if args.command == 'check':
            api_key()
            import dashscope
            print('API Key已配置，DashScope SDK可导入；尚未验证密钥有效性和模型权限。')
        elif args.command == 'transcribe':
            save(args.output, AliyunASR().transcribe_file(args.audio))
        elif args.command == 'submit':
            result = AliyunASR().submit({'audio_url': args.url})
            save(args.output, result)
            print('task_id: ' + result['task_id'])
        elif args.command == 'query':
            result = AliyunASR().fetch({'task_id': args.task_id})
            save(args.output, result)
            print('状态：' + result['status'])
        elif args.command == 'analyze':
            transcript, metadata = read(args.transcript), read(args.metadata)
            if 'segments' not in transcript:
                raise ValueError('转写尚未完成或缺少segments')
            metadata['segments'] = transcript['segments']
            service = AIService(mode='live')
            evaluation = service.evaluate(metadata)
            # Save evaluation before the second paid request, preserving partial success.
            save(Path(args.output_dir) / 'evaluation.json', evaluation)
            save(Path(args.output_dir) / 'suggestions.json', service.suggest({'evaluation': evaluation}))
        elif args.command == 'compare':
            result = AIService(mode='demo').compare({'evaluations': [read(p) for p in args.evaluations]})
            save(args.output, result)
    except (ProviderError, ValueError, OSError, ImportError) as exc:
        parser.exit(1, '执行失败：' + str(exc) + '\n')


if __name__ == '__main__':
    main()
