import json
import tempfile
import unittest
from pathlib import Path

from dunkin_compare.agent import automatic_missing, job_lock, schedule_command, schedule_xml
from dunkin_compare.desktop_data import read_all, update_profile, write_group
from tests.support import PARENT, COMPETITOR


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        (self.root / 'config').mkdir()
        write_group(self.root, 'parent', [PARENT])
        write_group(self.root, 'competitor', [COMPETITOR])
        self.config = self.root / 'config/profiles.json'
        self.config.write_text('{}')

    def test_untrained_and_untested_stores_block_schedule(self):
        self.assertEqual(len(automatic_missing(self.root)), 2)
        profiles = {}
        for store in (PARENT, COMPETITOR):
            key = 'trained_' + store.store_id
            profiles[key] = {'mode': 'trained', 'store_id': store.store_id,
                             'address': store.address, 'channel': store.channel,
                             'pages': [{'url': 'https://example.com/menu'}]}
            update_profile(self.root, store.store_id, key, 'https://example.com/menu')
        self.config.write_text(json.dumps(profiles))
        self.assertEqual(automatic_missing(self.root), [])
        self.assertEqual(len(automatic_missing(self.root, require_test=True)), 2)
        for profile in profiles.values():
            profile['last_validated_at'] = '2026-10-13T09:00:00-04:00'
        self.config.write_text(json.dumps(profiles))
        self.assertEqual(automatic_missing(self.root, require_test=True), [])

    def test_lock_prevents_overlapping_runs_and_releases(self):
        with job_lock(self.root):
            with self.assertRaises(RuntimeError):
                with job_lock(self.root):
                    self.fail('Second job acquired the lock')
        with job_lock(self.root):
            pass

    def test_schedule_command_quotes_paths_and_uses_logged_in_user(self):
        import xml.etree.ElementTree as ET
        root = self.root / 'A folder with spaces'
        command = schedule_command(root, '17:30')
        xml = ET.fromstring(schedule_xml(root, '17:30', 'PC\\Owner'))
        namespace = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        self.assertEqual(xml.find('.//t:LogonType', namespace).text, 'InteractiveToken')
        self.assertEqual(xml.find('.//t:RunLevel', namespace).text, 'LeastPrivilege')
        self.assertEqual(xml.find('.//t:StartBoundary', namespace).text[-8:], '17:30:00')
        self.assertEqual(xml.find('.//t:WorkingDirectory', namespace).text, str(root.resolve()))
        self.assertIn('pythonw.exe', xml.find('.//t:Command', namespace).text)
        self.assertIn('/XML', command)
        remove = schedule_command(root, '17:30', remove=True)
        self.assertEqual(command[command.index('/TN') + 1], remove[remove.index('/TN') + 1])
        for value in ('24:00', '09:60', '9am', '09:00 /F', ''):
            with self.assertRaises(ValueError):
                schedule_command(root, value)

    def test_store_update_preserves_other_group_and_csv_quotes(self):
        update_profile(self.root, PARENT.store_id, 'trained_parent', 'https://example.com/menu')
        stores = read_all(self.root)
        self.assertEqual(stores[0].address, PARENT.address)
        self.assertEqual(stores[0].profile, 'trained_parent')
        self.assertEqual(stores[1], COMPETITOR)


if __name__ == '__main__':
    unittest.main()
