"""Actual Chromium test of field picking, reviewed capture, and navigation."""
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dunkin_compare.core import load_stores
from dunkin_compare.interactive import CaptureSession
from tests.support import PARENT

ROOT = Path(__file__).resolve().parent.parent


class PickerBrowserTests(unittest.TestCase):
    def test_user_capture_flow(self):
        from playwright.sync_api import sync_playwright, expect

        fixture = (ROOT / 'tests/fixtures/picker_menu.html').read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(fixture)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as temp, sync_playwright() as p:
            binary = Path(p.chromium.executable_path)
            system_browser = shutil.which('chromium') or shutil.which('chromium-browser')
            if not binary.exists() and not system_browser:
                self.skipTest('Chromium not installed; run python -m playwright install chromium')
            browser = p.chromium.launch(headless=True, executable_path=str(binary) if binary.exists() else system_browser)
            try:
                store = PARENT
                session = CaptureSession(store, Path(temp) / 'capture.jsonl')
                context = browser.new_context(viewport={'width': 1280, 'height': 1000})
                context.expose_binding('__dpcState', lambda source: session.state())
                context.expose_binding('__dpcCapture', lambda source, payload: session.handle(payload, source['page'].url))
                context.add_init_script(path=str(ROOT / 'dunkin_compare/picker.js'))
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/menu')
                panel = page.locator('#dpc-collector')
                expect(panel.locator('#address')).to_have_text(store.address)
                panel.locator('#category').fill('Coffee')
                panel.locator('#variant').fill('Small')
                panel.locator('[data-pick="name"]').click()
                page.locator('.card h3').first.click()
                expect(panel.locator('#name')).to_have_value('Hot Coffee')
                panel.locator('[data-pick="price"]').click()
                page.locator('.card .price').first.click()
                expect(panel.locator('#price')).to_have_value('$2.49')
                panel.locator('#similar').click()
                expect(panel.locator('#preview tr')).to_have_count(3)  # Header + two exact visible prices.
                panel.locator('#selectall').click()
                panel.locator('#save').click()
                expect(panel.locator('#message')).to_contain_text('Confirm the store')
                self.assertEqual(session.items, [])
                panel.locator('#verified').check()
                panel.locator('#confirm').click()
                expect(panel.locator('#message')).to_contain_text('Store and channel confirmed')
                panel.locator('#save').click()
                expect(panel.locator('#message')).to_contain_text('Review the captured')
                self.assertEqual(session.items, [])
                panel.locator('#reviewed').check()
                panel.locator('#save').click()
                expect(panel.locator('#count')).to_have_text('2')
                self.assertEqual([i.name for i in session.items], ['Hot Coffee', 'Iced Coffee'])
                self.assertTrue(session.journal.exists())
                panel.locator('#minimize').click()
                expect(panel.locator('#body')).to_be_hidden()
                page.get_by_role('link', name='Next menu page').click()
                expect(panel.locator('#count')).to_have_text('2')
                expect(panel.locator('#verified')).not_to_be_checked()
                panel.locator('#finish').click()
                expect(panel.locator('#message')).to_contain_text('Store finished')
                self.assertTrue(session.done)
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
