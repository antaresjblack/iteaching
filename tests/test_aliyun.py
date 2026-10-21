import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from iteaching_ai.asr import AliyunASR, normalize_sentences, download_result
from iteaching_ai.config import load_env
from iteaching_ai.provider import ModelProvider, ProviderError


class AliyunTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'DASHSCOPE_API_KEY': 'test-not-real'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.asr = AliyunASR(sdk=SimpleNamespace())

    def response(self, output):
        return SimpleNamespace(status_code=200, output=output)

    def test_timestamps(self):
        result = normalize_sentences([{'text': '第二句', 'begin_time': 1500, 'end_time': 2500},
                                      {'text': '第一句', 'begin_time': 0, 'end_time': 1000}])
        self.assertEqual(result['segments'][0]['id'], 's1')
        self.assertEqual(result['segments'][1]['start_seconds'], 1.5)

    def test_invalid_timestamps_and_empty(self):
        for sentences in [[], [{'text': 'a', 'begin_time': 1, 'end_time': None}],
                          [{'text': 'a', 'begin_time': True, 'end_time': 2}]]:
            with self.assertRaises(ProviderError):
                normalize_sentences(sentences)

    def test_env_never_overwrites_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / '.env'
            p.write_text('DASHSCOPE_API_KEY=other\nITEACHING_MODEL="qwen-plus"\n', encoding='utf8')
            load_env(p)
        self.assertEqual(os.environ['DASHSCOPE_API_KEY'], 'test-not-real')
        self.assertEqual(os.environ['ITEACHING_MODEL'], 'qwen-plus')

    def test_submit_contract(self):
        with patch('dashscope.audio.asr.Transcription.async_call', return_value=self.response({'task_id': 'abc', 'task_status': 'PENDING'})) as call:
            result = self.asr.submit({'audio_url': 'https://example.com/a.mp3'})
            self.assertEqual(result['status'], 'PENDING')
            self.assertTrue(call.call_args.kwargs['timestamp_alignment_enabled'])
            self.assertEqual(call.call_args.kwargs['model'], 'paraformer-v2')

    def test_pending_and_failed(self):
        for state in ['PENDING', 'RUNNING', 'FAILED']:
            with patch('dashscope.audio.asr.Transcription.fetch', return_value=self.response({'task_status': state})):
                self.assertEqual(self.asr.fetch({'task_id': 'abc'})['status'], state)

    def test_success_result_normalized(self):
        output = {'task_status': 'SUCCEEDED', 'results': [{'subtask_status': 'SUCCEEDED', 'transcription_url': 'https://test.aliyuncs.com/result'}]}
        doc = {'transcripts': [{'sentences': [{'text': '测试', 'begin_time': 0, 'end_time': 1000}]}]}
        with patch('dashscope.audio.asr.Transcription.fetch', return_value=self.response(output)), patch('iteaching_ai.asr.download_result', return_value=doc):
            self.assertEqual(self.asr.fetch({'task_id': 'abc'})['segments'][0]['end_seconds'], 1)

    def test_failed_subtask_not_success(self):
        output = {'task_status': 'SUCCEEDED', 'results': [{'subtask_status': 'FAILED'}]}
        with patch('dashscope.audio.asr.Transcription.fetch', return_value=self.response(output)):
            with self.assertRaises(ProviderError):
                self.asr.fetch({'task_id': 'abc'})

    def test_invalid_paths_and_urls(self):
        with self.assertRaises(ValueError):
            self.asr.transcribe_file('missing.wav')
        with self.assertRaises(ValueError):
            self.asr.submit({'audio_url': 'file:///secret'})
        with self.assertRaises(ValueError):
            self.asr.fetch({'task_id': '../bad'})
        with self.assertRaises(ProviderError):
            download_result('https://example.com/result')

    def test_local_sdk_contract(self):
        import wave
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'a.wav'
            with wave.open(str(p), 'wb') as wav:
                wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x00\x00' * 160)
            response = SimpleNamespace(status_code=200, get_sentence=lambda: [{'text': '测试', 'begin_time': 0, 'end_time': 10}])
            with patch('dashscope.audio.asr.Recognition') as recognition:
                recognition.return_value.call.return_value = response
                self.assertFalse(self.asr.transcribe_file(p)['demo'])
                self.assertEqual(recognition.call_args.kwargs['sample_rate'], 16000)

    def test_qwen_json_contract(self):
        response = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"summary":"ok"}'}}]}
        with patch('iteaching_ai.provider.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as call:
            self.assertEqual(ModelProvider().generate('evaluate', {}), {'summary': 'ok'})
            body = json.loads(call.call_args.args[0].data)
            self.assertFalse(body['enable_thinking'])
            self.assertEqual(body['response_format']['type'], 'json_object')

    def test_truncation_rejected(self):
        response = {'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}
        with patch('iteaching_ai.provider.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(ProviderError):
                ModelProvider().generate('evaluate', {})


if __name__ == '__main__':
    unittest.main()
