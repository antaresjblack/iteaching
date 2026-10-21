import copy
import unittest

from test_service import FakeProvider, classroom
from iteaching_ai.service import AIService
from iteaching_ai.provider import ProviderError


class SequenceProvider(FakeProvider):
    def __init__(self, failures, kind='quote'):
        self.failures, self.kind, self.calls = failures, kind, []

    def generate(self, task, payload):
        self.calls.append(copy.deepcopy(payload))
        result = super().generate(task, payload)
        if len(self.calls) <= self.failures:
            item = result['indicators'][0]
            if self.kind == 'quote':
                item['evidence'][0]['quote'] = '原文没有此句'
            elif self.kind == 'problem':
                item['problems'] = [{'description': '问题', 'evidence': [
                    {'segment_id': 's1', 'quote': '不存在'}]}]
            elif self.kind == 'segment':
                item['evidence'][0]['segment_id'] = 'missing'
            else:
                item['score'] = 101
        return result


class EvaluationRetryTests(unittest.TestCase):
    def test_valid_first_attempt_does_not_retry(self):
        provider = SequenceProvider(0)
        AIService(provider=provider).evaluate(classroom())
        self.assertEqual(len(provider.calls), 1)

    def test_third_attempt_succeeds_with_feedback(self):
        for kind in ('quote', 'problem', 'segment'):
            provider = SequenceProvider(2, kind)
            result = AIService(provider=provider).evaluate(classroom())
            self.assertEqual(len(provider.calls), 3)
            self.assertIn('validation_feedback', provider.calls[1])
            self.assertEqual(provider.calls[0]['segments'], provider.calls[2]['segments'])
            self.assertEqual(result['indicators'][0]['score'], 50)

    def test_three_failures_stop(self):
        provider = SequenceProvider(10)
        with self.assertRaisesRegex(ProviderError, '连续3次'):
            AIService(provider=provider).evaluate(classroom())
        self.assertEqual(len(provider.calls), 3)

    def test_other_validation_errors_do_not_retry(self):
        provider = SequenceProvider(10, 'score')
        with self.assertRaises(ProviderError):
            AIService(provider=provider).evaluate(classroom())
        self.assertEqual(len(provider.calls), 1)


if __name__ == '__main__':
    unittest.main()
