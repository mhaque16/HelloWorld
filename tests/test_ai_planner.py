import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from dunkin_compare.ai_planner import VisionPlanner
from tests.support import PARENT


class PlannerTests(unittest.TestCase):
    def test_image_and_observed_elements_sent_and_usage_counted(self):
        response={'choices':[{'message':{'content':json.dumps({'action':'done','reason':'fixture'})}}],
                  'usage':{'prompt_tokens':123,'completion_tokens':20}}
        data=io.BytesIO(json.dumps(response).encode())
        planner=VisionPlanner('test-key-not-a-credential')
        with patch('dunkin_compare.ai_planner.urllib.request.urlopen',return_value=data) as call:
            decision=planner.decide(PARENT,{'elements':[]},b'fake-image',[])
        payload=json.loads(call.call_args.args[0].data)
        self.assertEqual(payload['messages'][1]['content'][1]['type'],'image_url')
        self.assertEqual(decision['action'],'done')
        self.assertEqual(planner.calls,1)
        self.assertEqual(planner.input_tokens,123)

    def test_authentication_error_does_not_echo_provider_body(self):
        error=urllib.error.HTTPError('https://api.openai.com/v1/chat/completions',401,'bad',{},io.BytesIO(b'key: do-not-echo'))
        with patch('dunkin_compare.ai_planner.urllib.request.urlopen',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'API key was not accepted') as result:
                VisionPlanner('test-key-not-a-credential').decide(PARENT,{},b'',[])
        self.assertNotIn('do-not-echo',str(result.exception))
