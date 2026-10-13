"""Save and replay explicitly taught menu-page layouts on the user's PC."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .core import deduplicate, make_item, normalized

ROOT = Path(__file__).resolve().parent.parent


class TeachingQueue:
    """Bindings enqueue work; the outer browser loop performs sync API calls.

    Calling Playwright's sync methods inside an exposed-binding callback hangs
    its dispatcher, so callbacks must only read/write ordinary Python state.
    """
    def __init__(self, root=ROOT):
        self.root, self.jobs, self.results = root, [], {}

    def enqueue(self, page, store, payload):
        if self.jobs:
            return {'ok': False, 'error': 'A teaching save is already pending'}
        identifier = uuid.uuid4().hex
        self.jobs.append((identifier, page, store, payload))
        return {'ok': True, 'pending': True, 'request_id': identifier}

    def result(self, identifier):
        return self.results.get(identifier, {'ok': True, 'pending': True, 'request_id': identifier})

    def process(self):
        if not self.jobs:
            return
        identifier, page, store, payload = self.jobs.pop(0)
        try:
            self.results[identifier] = save_training(page, store, payload, self.root)
        except Exception as exc:
            self.results[identifier] = {'ok': False, 'error': str(exc)}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def extract_page(page, recipe):
    location = page.locator(recipe['location_selector'])
    location.wait_for(timeout=30000)
    if location.count() != 1 or normalized(location.inner_text()) != normalized(recipe['expected_location']):
        raise ValueError('Selected store changed or could not be verified. Teach this page again.')
    shared = {}
    for field in ('category', 'variant'):
        if recipe.get(f'{field}_global_selector'):
            node = page.locator(recipe[f'{field}_global_selector'])
            node.wait_for(timeout=30000)
            if node.count() != 1 or normalized(node.inner_text()) != normalized(recipe[f'expected_{field}']):
                raise ValueError(f'The selected {field} changed. Automatic collection stopped for this page.')
            shared[field] = node.inner_text().strip()
    cards = page.locator(recipe['item_selector'])
    cards.first.wait_for(timeout=30000)
    rows = []
    for card in cards.all():
        if not card.is_visible():
            continue
        fields = dict(shared)
        for field in ('name', 'price', 'category', 'variant'):
            if field in fields:
                continue
            nodes = card.locator(recipe[f'{field}_selector'])
            if nodes.count() != 1 or not nodes.is_visible():
                raise ValueError(f'Taught menu layout changed: missing/ambiguous {field}')
            fields[field] = nodes.inner_text().strip()
        rows.append(make_item(**fields, currency='USD'))
    if not rows:
        raise ValueError('No visible priced items found on the taught page')
    for field in ('category', 'variant'):
        expected = recipe.get(f'expected_{field}_values')
        if expected is not None and {normalized(getattr(item, field)) for item in rows} != set(expected):
            raise ValueError(f'The taught {field} selection changed. Teach this page again.')
    return deduplicate(rows)


def save_training(page, store, payload, root=ROOT):
    if payload.get('reviewed') is not True:
        raise ValueError('Review the preview rows before teaching automatic collection')
    recipe = payload.get('recipe', {})
    required = ['location_selector', 'expected_location', 'item_selector', 'name_selector', 'price_selector']
    required += [f'{field}_selector' if recipe.get(f'{field}_selector') else f'{field}_global_selector'
                 for field in ('category', 'variant')]
    if any(not isinstance(recipe.get(k), str) or not recipe[k] or len(recipe[k]) > 1000 for k in required):
        raise ValueError('Pick address, name, price, category, and size from the page before teaching')
    parsed = urlsplit(page.url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Teach a public HTTPS menu URL')
    allowed = set(required) | {'expected_category', 'expected_variant'}
    recipe = {key: value for key, value in recipe.items() if key in allowed}
    items = extract_page(page, recipe)  # Validate selectors against the current actual browser page.
    reviewed = payload.get('reviewed_rows', [])
    try:
        preview_items = deduplicate([make_item(category=row['category'], name=row['name'],
                                              variant=row['variant'], price=row['price'], currency='USD')
                                     for row in reviewed])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('Preview all similar cards and review their fields before teaching') from exc
    if set(items) != set(preview_items):
        raise ValueError('The taught layout differs from the reviewed rows. Use Preview similar cards, review all rows, and try again. Typed corrections cannot be replayed automatically.')
    config_path = root / 'config/profiles.json'
    profiles = json.loads(config_path.read_text(encoding='utf-8'))
    from .desktop_data import read_all
    current = [s for s in read_all(root) if s.store_id == store.store_id]
    if len(current) != 1 or current[0].address != store.address or current[0].channel != store.channel:
        raise ValueError('Store settings changed during teaching. Close this browser and teach the store again.')
    key = current[0].profile
    existing = profiles.get(key, {})
    if existing.get('mode') != 'trained' or existing.get('store_id') != store.store_id:
        key = 'trained_' + uuid.uuid4().hex
        existing = {'mode': 'trained', 'store_id': store.store_id, 'pages': []}
    existing['address'] = store.address
    existing['channel'] = store.channel
    recipe['url'] = page.url
    for field in ('category', 'variant'):
        recipe[f'expected_{field}_values'] = sorted({normalized(getattr(item, field)) for item in items})
    recipe['state_file'] = f'local_state/{uuid.uuid4().hex}.json'
    # Browser session is kept only on this PC, outside the distributable package.
    state_path = root / recipe['state_file']
    state_path.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(state_path))
    signature = (recipe['url'], recipe.get('expected_category'), recipe.get('expected_variant'), recipe['item_selector'])
    pages = [r for r in existing['pages'] if
             (r['url'], r.get('expected_category'), r.get('expected_variant'), r['item_selector']) != signature]
    existing['pages'] = pages + [recipe]
    existing.pop('last_validated_at', None)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    existing['last_taught_at'] = datetime.now(ZoneInfo('America/New_York')).isoformat()
    profiles[key] = existing
    atomic_json(config_path, profiles)
    from .desktop_data import update_profile
    update_profile(root, store.store_id, key, page.url)
    return {'ok': True, 'page_count': len(existing['pages']), 'item_count': len(items)}


def collect_trained(store, profile, root=ROOT):
    if profile.get('store_id') != store.store_id or not profile.get('pages'):
        raise ValueError('This store needs its own taught menu pages')
    if profile.get('address') != store.address or profile.get('channel') != store.channel:
        raise ValueError('Store address or pricing channel changed. Teach this store again.')
    from playwright.sync_api import sync_playwright
    from .interactive import launch_visible
    items, sources = [], []
    with sync_playwright() as p:
        # Reuse installed Chromium/Edge/Chrome, but keep automatic runs headless.
        browser = launch_visible(p, 'auto', headless=True)
        try:
            for recipe in profile['pages']:
                from .collect import check_robots
                check_robots(recipe['url'])
                state = (root / recipe['state_file']).resolve()
                if not state.is_relative_to((root / 'local_state').resolve()) or not state.is_file():
                    raise ValueError('Saved local session missing. Teach this page again.')
                context = browser.new_context(storage_state=str(state))
                try:
                    page = context.new_page()
                    response = page.goto(recipe['url'], wait_until='domcontentloaded', timeout=45000)
                    if response is None or response.status >= 400:
                        raise ValueError('The ordering page is unavailable; no prices collected')
                    page.locator(recipe['item_selector']).first.wait_for(timeout=30000)
                    page.wait_for_timeout(1500)
                    items.extend(extract_page(page, recipe))
                    sources.append(page.url)
                finally:
                    context.close()
            return deduplicate(items), '\n'.join(dict.fromkeys(sources))
        finally:
            browser.close()
