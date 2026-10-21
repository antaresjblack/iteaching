import os
import unittest
from unittest.mock import Mock, patch

from iteaching_ai.oss_audio import OSSAudio
from iteaching_ai.provider import ProviderError


class OSSAudioTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {
            'OSS_REGION': 'cn-beijing', 'OSS_BUCKET_NAME': 'test-bucket',
            'OSS_AUDIO_PREFIX': 'iteaching-temp/',
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_private_upload_sign_and_cleanup(self):
        bucket = Mock()
        bucket.sign_url.return_value = 'https://example.com/signed'
        storage = OSSAudio(bucket)
        key = storage.new_key('课堂.wav')
        self.assertTrue(key.startswith('iteaching-temp/'))
        self.assertNotIn('课堂', key)
        result = storage.upload(key, 'file.wav')
        headers = bucket.put_object_from_file.call_args.kwargs['headers']
        self.assertEqual(headers['x-oss-object-acl'], 'private')
        self.assertEqual(headers['x-oss-forbid-overwrite'], 'true')
        bucket.sign_url.assert_called_once_with('GET', key, 7200)
        self.assertIn('expires', result)
        storage.cleanup(key, Mock())
        bucket.delete_object.assert_called_once_with(key)

    def test_sdk_errors_do_not_expose_url(self):
        bucket = Mock()
        bucket.put_object_from_file.side_effect = RuntimeError('https://secret/signature')
        with self.assertRaises(ProviderError) as context:
            OSSAudio(bucket).upload('key', 'file')
        self.assertNotIn('secret', str(context.exception))

    def test_cleanup_failure_is_reported_without_losing_result(self):
        bucket, journal = Mock(), Mock()
        bucket.delete_object.side_effect = RuntimeError('secret')
        OSSAudio(bucket).cleanup('iteaching-temp/test.wav', journal)
        self.assertIn('清理失败', journal.event.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
