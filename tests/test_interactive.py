import json
import tempfile
import unittest
from pathlib import Path

from dunkin_compare.core import load_stores
from dunkin_compare.interactive import CaptureSession
from tests.support import PARENT

ROOT = Path(__file__).resolve().parent.parent


class CaptureSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = PARENT
        self.session = CaptureSession(self.store, Path(self.temp.name) / 'captures.jsonl')
        self.url = 'https://example.com/store/menu'
        self.row = {'category': 'Coffee', 'name': 'Hot Coffee', 'variant': 'Small',
                    'price': '$2.49', 'currency': 'USD'}

    def confirm(self):
        self.assertTrue(self.session.handle({'action': 'confirm', 'checked': True}, self.url)['ok'])

    def save(self, row=None, **kwargs):
        return self.session.handle({'action': 'save', 'rows': [row or self.row],
                                    'reviewed': True, **kwargs}, self.url)

    def test_confirmation_and_review_required(self):
        self.assertFalse(self.save()['ok'])
        self.assertFalse(self.session.handle({'action': 'confirm', 'checked': False}, self.url)['ok'])
        self.confirm()
        self.assertFalse(self.save(reviewed=False)['ok'])
        self.assertTrue(self.save()['ok'])
        self.assertEqual(len(self.session.items), 1)

    def test_page_navigation_requires_confirmation_again(self):
        self.confirm()
        payload = {'action': 'save', 'rows': [self.row], 'reviewed': True}
        self.assertFalse(self.session.handle(payload, 'https://example.com/other-store')['ok'])

    def test_batch_validated_before_any_write(self):
        self.confirm()
        bad = {**self.row, 'name': 'Other coffee', 'price': 'From $1.99'}
        result = self.session.handle({'action': 'save', 'reviewed': True, 'rows': [self.row, bad]}, self.url)
        self.assertFalse(result['ok'])
        self.assertEqual(self.session.items, [])
        self.assertFalse(self.session.journal.exists())

    def test_duplicates_conflicts_and_journal(self):
        self.confirm()
        self.assertTrue(self.save()['ok'])
        self.assertTrue(self.save()['ok'])
        self.assertEqual(len(self.session.items), 1)
        self.assertFalse(self.save({**self.row, 'price': '$8.99'})['ok'])
        records = [json.loads(line) for line in self.session.journal.read_text().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['items'][0]['price'], '2.49')
        self.assertEqual(records[0]['source_url'], self.url)
        self.assertIn('collected_at', records[0])
        self.assertTrue(self.session.handle({'action': 'finish'}, self.url)['ok'])
        self.assertTrue(self.session.done)

    def test_unknown_size_and_other_currency_rejected(self):
        self.confirm()
        for overrides in ({'variant': ''}, {'currency': 'CAD'}):
            self.assertFalse(self.save({**self.row, **overrides})['ok'])

    def test_cannot_skip_saved_items_or_finish_empty(self):
        self.assertFalse(self.session.handle({'action': 'finish'}, self.url)['ok'])
        self.confirm()
        self.save()
        self.assertFalse(self.session.handle({'action': 'skip'}, self.url)['ok'])

    def test_journal_failure_does_not_acknowledge_save(self):
        self.confirm()
        self.session.journal = Path(self.temp.name)  # A directory cannot be opened as a journal file.
        self.assertFalse(self.save()['ok'])
        self.assertEqual(self.session.items, [])


if __name__ == '__main__':
    unittest.main()
