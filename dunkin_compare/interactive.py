"""Visible-browser collection with user-confirmed store and reviewed prices.

This mode needs no Dunkin CSS profile: the user picks displayed fields. It does
not assert that address selection, menu traversal, or option selection is automatic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .core import Item, Store, deduplicate, make_item


@dataclass
class CaptureSession:
    store: Store
    journal: Path
    items: list[Item] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    confirmed_url: str = ""
    done: bool = False
    skipped: bool = False
    training: bool = False

    def state(self):
        return {"address": self.store.address, "store_id": self.store.store_id,
                "group": self.store.group, "channel": self.store.channel,
                "count": len(self.items), "training": self.training}

    def handle(self, payload: dict, url: str):
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ("https", "http") or not parsed.hostname:
                raise ValueError("Open a menu web page before collecting")
            if parsed.username or parsed.password:
                raise ValueError("Do not use a URL containing credentials")
            action = payload.get("action")
            if action == "confirm":
                if not payload.get("checked"):
                    raise ValueError("Confirm the store address and pricing channel first")
                self.confirmed_url = url
                return {"ok": True, "count": len(self.items)}
            if action == "skip":
                if self.items:
                    raise ValueError("Items are already saved; use Finish store to retain them")
                self.skipped = self.done = True
                return {"ok": True}
            if action == "finish":
                if not self.items and not self.training:
                    raise ValueError("Save at least one item or use Skip store")
                self.done = True
                return {"ok": True, "count": len(self.items)}
            if action != "save":
                raise ValueError("Unknown capture action")
            if self.confirmed_url != url:
                raise ValueError("Confirm the selected store and channel on this page before saving")
            if payload.get("reviewed") is not True:
                raise ValueError("Review the captured names, sizes, categories, and prices before saving")
            rows = payload.get("rows")
            if not isinstance(rows, list) or not rows or len(rows) > 500:
                raise ValueError("Select between 1 and 500 reviewed items")
            new_items = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Invalid menu row")
                values = {key: str(row.get(key, "")).strip() for key in
                          ("category", "name", "variant", "price", "currency")}
                if any(len(v) > 300 for v in values.values()):
                    raise ValueError("A field is too long; pick the item text rather than a full page")
                if not values["variant"]:
                    raise ValueError("Enter the observed size/variant (e.g. Small or Single)")
                if values["currency"] != "USD":
                    raise ValueError("This Dunkin US workflow collects USD prices")
                new_items.append(make_item(**values))
            merged = deduplicate(self.items + new_items)
            # Write reviewed data before acknowledging it to the UI. Never save HTML,
            # cookies, login state, or browser storage in the capture journal.
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            record = {"store": self.store.__dict__, "source_url": url,
                      "items": [{**item.__dict__, "price": str(item.price)} for item in new_items]}
            from datetime import datetime
            from zoneinfo import ZoneInfo
            record["collected_at"] = datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
            with self.journal.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.items = merged
            if url not in self.sources:
                self.sources.append(url)
            return {"ok": True, "count": len(self.items)}
        except (ValueError, TypeError, OSError) as exc:
            return {"ok": False, "error": str(exc)}


def launch_visible(p, requested: str, headless: bool = False):
    channels = {"chromium": None, "edge": "msedge", "chrome": "chrome"}
    choices = ["chromium", "edge", "chrome"] if requested == "auto" else [requested]
    errors = []
    for choice in choices:
        try:
            kwargs = {"headless": headless}
            if channels[choice]:
                kwargs["channel"] = channels[choice]
            return p.chromium.launch(**kwargs)
        except Exception as exc:
            errors.append(f"{choice}: {exc}")
    raise RuntimeError("Could not start the browser. Run Setup Mac.command on Mac or setup_windows.bat "
                       "on Windows. Installed Chrome/Edge can also be tried.\n" + "\n".join(errors))


def collect_interactive(store: Store, browser_choice: str, journal: Path, training: bool = False):
    if not store.brand or not store.market or store.channel not in ("pickup", "delivery", "in_store"):
        raise ValueError("Set brand, market, and channel in the store CSV before starting")
    session = CaptureSession(store, journal, training=training)
    from playwright.sync_api import Error, sync_playwright
    script = Path(__file__).with_name("picker.js").read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = launch_visible(p, browser_choice)
        try:
            # A new context per store prevents accidental carryover of location/cart state.
            context = browser.new_context()
            from .training import TeachingQueue
            teaching = TeachingQueue()

            def state(source):
                return session.state()

            def capture(source, payload):
                if source["frame"] != source["page"].main_frame:
                    return {"ok": False, "error": "Collect from the main menu page, not an embedded frame"}
                if payload.get('action') == 'train':
                    if session.confirmed_url != source['page'].url:
                        return {'ok': False, 'error': 'Confirm this store and channel first'}
                    if not session.training:
                        return {'ok': False, 'error': 'Open Teach automatic collection from the app first'}
                    return teaching.enqueue(source['page'], store, payload)
                return session.handle(payload, source["page"].url)

            context.expose_binding("__dpcState", state)
            context.expose_binding("__dpcCapture", capture)
            context.expose_binding('__dpcTrainingResult', lambda source, identifier: teaching.result(identifier))
            context.add_init_script(script=script)
            page = context.new_page()
            target = store.menu_url or "https://www.dunkindonuts.com/en"
            parts = urlsplit(target)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                raise ValueError("menu_url must be HTTPS without embedded credentials")
            print(f"\n{store.group.upper()}: {store.address}\n"
                  f"Select the correct store and {store.channel} menu in the browser. "
                  "Use the Menu Price Collector panel to pick and review prices.", flush=True)
            try:
                page.goto(target, wait_until="domcontentloaded", timeout=45000)
            except Error as exc:
                print(f"Initial navigation: {exc}\nYou can navigate to the ordering page manually.", flush=True)
            while not session.done and context.pages:
                try:
                    context.pages[0].wait_for_timeout(250)
                    teaching.process()
                except Error:
                    if not browser.is_connected():
                        break
            incomplete = not session.done
            if not session.items:
                outcome = 'trained' if session.training and session.done and not session.skipped else ('skipped' if session.skipped else 'failed')
                return [], "", outcome, "No price rows saved during this session"
            return session.items, "\n".join(session.sources), "partial" if incomplete else "reviewed", (
                "Browser closed before Finish store; saved reviewed rows retained" if incomplete else
                "User confirmed store/channel and reviewed captured fields; coverage is user-selected")
        finally:
            browser.close()
