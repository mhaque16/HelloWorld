import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from dunkin_compare.ai_runner import run_store, store_signature
from dunkin_compare.agent import automatic_missing
from dunkin_compare.core import Item
from dunkin_compare.desktop_data import write_group
from tests.support import PARENT


class AiRunTests(unittest.TestCase):
    def run_plan(self,actions,limit=10,extract_error=None):
        page=Mock()
        page.url='https://example.com/menu'
        page.screenshot.return_value=b'png'
        controller=Mock()
        controller.page=page
        controller.snapshot.return_value={'elements':[]}
        if extract_error:
            controller.extract.side_effect=extract_error
        else:
            controller.extract.return_value=[Item('Coffee','Coffee','Small',Decimal('2.49'),'USD')]
        planner=Mock()
        planner.decide.side_effect=actions
        with patch('dunkin_compare.ai_runner.PageController',return_value=controller):
            return run_store(page,PARENT,planner,limit)

    def test_step_limit_retains_verified_rows_but_is_partial(self):
        items,_,status,message=self.run_plan([{'action':'extract'},{'action':'extract'}],2)
        self.assertEqual(len(items),1)
        self.assertEqual(status,'partial')
        self.assertIn('step limit',message)

    def test_access_barrier_is_failed_without_rows_and_partial_with_rows(self):
        self.assertEqual(self.run_plan([{'action':'blocked','reason':'Login needed'}])[2],'failed')
        result=self.run_plan([{'action':'extract'},{'action':'blocked','reason':'Login needed'}])
        self.assertEqual(result[2],'partial')
        self.assertEqual(len(result[0]),1)

    def test_done_without_prices_cannot_mark_store_collected(self):
        result=self.run_plan([{'action':'done'}]*3)
        self.assertEqual(result[2],'failed')

    def test_repeated_evidence_errors_stop_without_filling_prices(self):
        result=self.run_plan([{'action':'extract'}]*3,extract_error=ValueError('Price not observed'))
        self.assertEqual(result[0],[])
        self.assertEqual(result[2],'failed')

    def test_ai_mode_needs_key_and_test_but_no_taught_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for directory in ('config','data','local_state'):
                (root/directory).mkdir()
            (root/'config/profiles.json').write_text('{}')
            write_group(root,'parent',[PARENT])
            write_group(root,'competitor',[])
            file=root/'local_state/ai_settings.json'
            file.write_text(json.dumps({'enabled':True}))
            with patch('dunkin_compare.ai_credentials.get_key',return_value=''):
                self.assertIn('API key',automatic_missing(root)[0])
            with patch('dunkin_compare.ai_credentials.get_key',return_value='not-a-real-key'):
                self.assertEqual(automatic_missing(root),[])
                self.assertTrue(automatic_missing(root,require_test=True))
                file.write_text(json.dumps({'enabled':True,'last_validated_at':'test',
                                            'last_validated_stores':store_signature([PARENT])}))
                self.assertEqual(automatic_missing(root,require_test=True),[])
                file.write_text(json.dumps({'enabled':True,'last_validated_at':'test',
                                            'last_validated_stores':'old-store-list'}))
                self.assertTrue(automatic_missing(root,require_test=True))
