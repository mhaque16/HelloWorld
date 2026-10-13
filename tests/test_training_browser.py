import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from dunkin_compare.desktop_data import read_all, write_group
from dunkin_compare.training import collect_trained, extract_page, save_training, TeachingQueue
from dunkin_compare.interactive import CaptureSession
from tests.support import PARENT


HTML = '''<!doctype html><html><body>
<div id="store-address">13801 Heathcote Blvd, Gainesville, VA</div>
<h2 id="observed-category">Coffee</h2><div id="observed-size">Small</div>
<article class="menu-card"><h3>Hot Coffee</h3><span>$2.49</span></article>
<article class="menu-card"><h3>Iced Coffee</h3><span>$3.29</span></article>
</body></html>'''


class TrainingBrowserTests(unittest.TestCase):
    def test_teaching_replay_and_changed_size_failure(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp, sync_playwright() as p:
            root = Path(temp)
            (root / 'data').mkdir()
            (root / 'config').mkdir()
            (root / 'config/profiles.json').write_text('{}')
            write_group(root, 'parent', [PARENT])
            write_group(root, 'competitor', [])
            executable = p.chromium.executable_path
            if not Path(executable).exists():
                executable = shutil.which('chromium') or shutil.which('chromium-browser')
            if not executable:
                self.skipTest('Chromium not installed')
            browser = p.chromium.launch(executable_path=executable, headless=True)
            try:
                context = browser.new_context()
                context.route('https://menu.example.test/**', lambda route: route.fulfill(body=HTML, content_type='text/html'))
                context.add_cookies([{'name': 'selectedStore', 'value': 'gainesville', 'url': 'https://menu.example.test'}])
                page = context.new_page()
                page.goto('https://menu.example.test/menu')
                recipe = {'location_selector': '#store-address', 'expected_location': '13801 Heathcote Blvd, Gainesville, VA',
                          'item_selector': '.menu-card', 'name_selector': 'h3', 'price_selector': 'span',
                          'category_global_selector': '#observed-category', 'expected_category': 'Coffee',
                          'variant_global_selector': '#observed-size', 'expected_variant': 'Small'}
                rows = [{'category': 'Coffee', 'name': name, 'variant': 'Small', 'price': price}
                        for name, price in [('Hot Coffee', '2.49'), ('Iced Coffee', '3.29')]]
                with self.assertRaisesRegex(ValueError, 'differs'):
                    save_training(page, PARENT, {'reviewed': True, 'recipe': recipe, 'reviewed_rows': rows[:1]}, root)
                result = save_training(page, PARENT, {'reviewed': True, 'recipe': recipe, 'reviewed_rows': rows}, root)
                self.assertEqual(result['item_count'], 2)
                store = read_all(root)[0]
                profile = json.loads((root / 'config/profiles.json').read_text())[store.profile]
                self.assertEqual(profile['store_id'], PARENT.store_id)
                self.assertEqual(len(profile['pages']), 1)
                self.assertTrue((root / profile['pages'][0]['state_file']).is_file())
                # A fresh real browser/context replays the saved session and selectors.
                def launch(playwright, requested, headless):
                    b = playwright.chromium.launch(executable_path=executable, headless=True)
                    original = b.new_context
                    def new_context(**kwargs):
                        ctx = original(**kwargs)
                        ctx.route('https://menu.example.test/**', lambda route: route.fulfill(body=HTML, content_type='text/html'))
                        return ctx
                    b.new_context = new_context
                    return b
                with patch('dunkin_compare.interactive.launch_visible', side_effect=launch), patch('dunkin_compare.collect.check_robots'), ThreadPoolExecutor(max_workers=1) as worker:
                    items, source = worker.submit(collect_trained, store, profile, root).result(timeout=30)
                self.assertEqual(len(items), 2)
                self.assertEqual(source, 'https://menu.example.test/menu')
                page.locator('#observed-size').evaluate("node => node.textContent = 'Large'")
                with self.assertRaisesRegex(ValueError, 'variant changed'):
                    extract_page(page, recipe)
                page.locator('#observed-size').evaluate("node => node.textContent = 'Small'")
                page.locator('#store-address').evaluate("node => node.textContent = 'Other store'")
                with self.assertRaisesRegex(ValueError, 'store changed'):
                    extract_page(page, recipe)
                # Test the real teaching buttons, not just the Python save routine.
                session = CaptureSession(PARENT, root / 'capture.jsonl', training=True)
                teaching = TeachingQueue(root)
                context.expose_binding('__dpcState', lambda source: session.state())
                def capture(source, payload):
                    if payload.get('action') == 'train':
                        return teaching.enqueue(source['page'], PARENT, payload)
                    return session.handle(payload, source['page'].url)
                context.expose_binding('__dpcCapture', capture)
                context.expose_binding('__dpcTrainingResult', lambda source, identifier: teaching.result(identifier))
                context.add_init_script(path=str(Path(__file__).resolve().parent.parent / 'dunkin_compare/picker.js'))
                ui_page = context.new_page()
                ui_page.goto('https://menu.example.test/ui')
                panel = ui_page.locator('#dpc-collector')
                from playwright.sync_api import expect
                expect(panel.locator('#teaching')).to_be_visible()
                panel.locator('#verified').check()
                panel.locator('#confirm').click()
                expect(panel.locator('#message')).to_contain_text('confirmed')
                for field, selector in [('location', '#store-address'), ('category', '#observed-category'),
                                        ('variant', '#observed-size'), ('name', '.menu-card h3'),
                                        ('price', '.menu-card span')]:
                    panel.locator(f'[data-pick="{field}"]').click()
                    ui_page.locator(selector).first.click()
                panel.locator('#similar').click()
                expect(panel.locator('#preview tr')).to_have_count(3)
                panel.locator('#reviewed').check()
                panel.locator('#train').click()
                ui_page.wait_for_timeout(100)
                teaching.process()
                expect(panel.locator('#message')).to_contain_text('Saved for autorun')
                updated = read_all(root)[0]
                settings = json.loads((root / 'config/profiles.json').read_text())[updated.profile]
                self.assertEqual(len(settings['pages']), 2)
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
