import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dunkin_compare.mac_schedule import configure, label_for, launch_agent


class MacScheduleTests(unittest.TestCase):
    def test_plist_preserves_paths_with_spaces_and_daily_time(self):
        root = Path('/Users/example/Dunkin Agent')
        config = plistlib.loads(plistlib.dumps(launch_agent(root, '09:15')))
        self.assertEqual(config['StartCalendarInterval'], {'Hour': 9, 'Minute': 15})
        self.assertEqual(config['ProgramArguments'][0], '/Users/example/Dunkin Agent/.venv/bin/python')
        self.assertEqual(config['WorkingDirectory'], str(root))
        self.assertFalse(config['RunAtLoad'])
        for time in ('24:00', '09:60', '9AM', ''):
            with self.assertRaises(ValueError):
                launch_agent(root, time)

    def test_enable_and_disable_only_this_users_own_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            root = home / 'Dunkin Agent'
            (root / '.venv/bin').mkdir(parents=True)
            (root / '.venv/bin/python').touch()
            calls = []
            def run(arguments, **kwargs):
                calls.append(arguments)
                return subprocess.CompletedProcess(arguments, 113 if arguments[1] == 'print' else 0, '', '')
            with patch('dunkin_compare.mac_schedule.Path.home', return_value=home), patch('dunkin_compare.mac_schedule.os.getuid', return_value=501, create=True), patch('dunkin_compare.mac_schedule.subprocess.run', side_effect=run):
                configure(root, '17:30')
                file = home / 'Library/LaunchAgents' / (label_for(root)+'.plist')
                self.assertTrue(file.is_file())
                self.assertEqual(plistlib.loads(file.read_bytes())['StartCalendarInterval']['Hour'], 17)
                self.assertEqual(calls[-1][1], 'bootstrap')
                self.assertTrue(calls[-1][2].startswith('gui/'))
                self.assertEqual(Path(calls[-1][3]), file)
                configure(root, '17:30', remove=True)
                self.assertFalse(file.exists())

    def test_failed_bootstrap_is_not_recorded_as_enabled(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            root = home / 'app'
            (root / '.venv/bin').mkdir(parents=True)
            (root / '.venv/bin/python').touch()
            def run(arguments, **kwargs):
                return subprocess.CompletedProcess(arguments, 113 if arguments[1] == 'print' else 1, '', 'Not permitted')
            with patch('dunkin_compare.mac_schedule.Path.home', return_value=home), patch('dunkin_compare.mac_schedule.os.getuid', return_value=501, create=True), patch('dunkin_compare.mac_schedule.subprocess.run', side_effect=run):
                with self.assertRaisesRegex(RuntimeError, 'Not permitted'):
                    configure(root, '09:00')
            self.assertFalse(json.loads((root / 'local_state/schedule.json').read_text())['enabled'])
