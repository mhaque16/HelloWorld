import csv
import os
from pathlib import Path

from .core import load_stores

FIELDS = ['store_id', 'brand', 'address', 'market', 'channel', 'menu_url', 'profile']


def read_all(root: Path):
    return load_stores(root / 'data/parent_stores.csv', 'parent') + load_stores(root / 'data/competitor_stores.csv', 'competitor')


def write_group(root, group, stores):
    path = root / 'data' / ('parent_stores.csv' if group == 'parent' else 'competitor_stores.csv')
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for store in stores:
            writer.writerow({field: getattr(store, field) for field in FIELDS})
    os.replace(temporary, path)


def update_profile(root, store_id, profile, url):
    from dataclasses import replace
    stores = read_all(root)
    matches = [s for s in stores if s.store_id == store_id]
    if len(matches) != 1:
        raise ValueError('Store ID missing or duplicated in address files')
    group = matches[0].group
    write_group(root, group, [replace(s, profile=profile, menu_url=url) if s.store_id == store_id else s
                            for s in stores if s.group == group])
