import io
import json
import unittest
from unittest.mock import Mock,patch

from dunkin_compare.local_planner import LocalVisionPlanner,NoRedirect,check_local,local_request
from tests.support import PARENT


class LocalPlannerTests(unittest.TestCase):
    def test_vision_payload_is_local_and_has_no_api_key(self):
        response={'message':{'content':json.dumps({'action':'done','reason':'fixture'})},
                  'prompt_eval_count':123,'eval_count':20}
        with patch('dunkin_compare.local_planner.local_request',return_value=response) as request:
            planner=LocalVisionPlanner()
            result=planner.decide(PARENT,{'elements':[]},b'image',[])
        self.assertEqual(result['action'],'done')
        self.assertEqual(request.call_args.args[0],'chat')
        payload=request.call_args.args[1]
        self.assertEqual(payload['model'],'gemma3:4b')
        self.assertEqual(payload['messages'][1]['images'],['aW1hZ2U='])
        self.assertFalse(payload['stream'])
        self.assertEqual(planner.calls,1)
        self.assertEqual(planner.input_tokens,123)
        self.assertNotIn('api_key',payload)

    def test_requests_use_loopback_without_proxy_or_authentication(self):
        opener=Mock()
        opener.open.return_value=io.BytesIO(b'{"models":[]}')
        with patch('dunkin_compare.local_planner.urllib.request.build_opener',return_value=opener) as build:
            self.assertEqual(local_request('tags'),{'models':[]})
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,'http://127.0.0.1:11434/api/tags')
        self.assertNotIn('Authorization',dict(request.header_items()))
        self.assertEqual(build.call_args.args[0].proxies,{})
        self.assertIsInstance(build.call_args.args[1],NoRedirect)

    def test_cloud_model_and_redirect_rejected(self):
        with self.assertRaisesRegex(ValueError,'cloud'):
            check_local('model:cloud')
        with self.assertRaisesRegex(RuntimeError,'redirect'):
            NoRedirect().redirect_request(None,None,302,'',{},'https://example.com')
        with patch('dunkin_compare.local_planner.local_request',side_effect=[
            {'models':[{'name':'alias:latest'}]},{'remote_host':'example.com','remote_model':'cloud-model'}]):
            with self.assertRaisesRegex(ValueError,'cloud-backed'):
                check_local('alias:latest')

    def test_missing_or_nonvision_model_stops_before_inference(self):
        with patch('dunkin_compare.local_planner.local_request',return_value={'models':[]}):
            with self.assertRaisesRegex(ValueError,'not installed'):
                check_local()
        with patch('dunkin_compare.local_planner.local_request',side_effect=[
            {'models':[{'name':'text-model:latest'}]},{'capabilities':['completion']}]):
            with self.assertRaisesRegex(ValueError,'does not support screenshots'):
                check_local('text-model:latest')

    def test_healthy_local_model_and_no_key_requirement(self):
        import tempfile
        from pathlib import Path
        from dunkin_compare.agent import automatic_missing
        from dunkin_compare.desktop_data import write_group
        with patch('dunkin_compare.local_planner.local_request',side_effect=[
            {'models':[{'name':'gemma3:4b'}]},{'capabilities':['completion','vision']}]):
            check_local()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('data','config','local_state'):(root/name).mkdir()
            write_group(root,'parent',[PARENT]);write_group(root,'competitor',[])
            (root/'config/profiles.json').write_text('{}')
            (root/'local_state/ai_settings.json').write_text(json.dumps({'enabled':True,'provider':'ollama'}))
            with patch('dunkin_compare.local_planner.check_local'),patch('dunkin_compare.ai_credentials.get_key') as key:
                self.assertEqual(automatic_missing(root),[])
                key.assert_not_called()
