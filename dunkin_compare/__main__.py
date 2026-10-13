from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .collect import collect
from .core import load_stores, parse_jsonld
from .report import write_report

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect store-verified menu prices and compare them in Excel.")
    parser.add_argument("--parent", type=Path, default=ROOT / "data/parent_stores.csv")
    parser.add_argument("--competitors", type=Path, default=ROOT / "data/competitor_stores.csv")
    parser.add_argument("--profiles", type=Path, default=ROOT / "config/profiles.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--demo", action="store_true", help="Use clearly labeled synthetic fixtures, without network access")
    parser.add_argument("--interactive", action="store_true", help="Open a visible browser and pick/review menu fields")
    parser.add_argument("--browser", choices=["auto", "chromium", "edge", "chrome"], default="auto")
    args = parser.parse_args(argv)
    if args.demo and args.interactive:
        parser.error("--demo and --interactive cannot be combined")
    try:
        stores = load_stores(args.parent, "parent") + load_stores(args.competitors, "competitor")
        if not stores:
            raise ValueError("Add at least one store to an address CSV")
        ids = [s.store_id for s in stores]
        if len(set(ids)) != len(ids):
            raise ValueError("store_id must be unique across both files")
        profiles = {} if args.interactive else json.loads(args.profiles.read_text())
        if args.demo and (len(stores) != 2 or set(ids) != {"parent_gainesville", "competitor_ashburn"}):
            raise ValueError("Demo requires the two supplied example stores")
    except (ValueError, OSError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    collected, statuses = [], []
    run_stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S_%f")
    journal = ROOT / "reports" / "captures" / f"capture_{run_stamp}.jsonl"
    for index, store in enumerate(stores):
        status = {"group": store.group, "store_id": store.store_id, "address": store.address,
                  "status": "failed", "item_count": 0, "message": ""}
        try:
            if args.demo:
                fixture = ROOT / "tests/fixtures" / f"{store.group}.html"
                items = parse_jsonld(fixture.read_text(), store.address)
                source = f"synthetic-fixture:{fixture.name}"
            elif args.interactive:
                from .interactive import collect_interactive
                items, source, result_status, message = collect_interactive(store, args.browser, journal)
                status.update(status=result_status, item_count=len(items), message=message)
                if items:
                    collected.append((store, items, source))
                print(f"{store.store_id}: {result_status}, {len(items)} reviewed items")
                statuses.append(status)
                continue
            else:
                if index:
                    time.sleep(2)
                if store.profile not in profiles:
                    raise ValueError(f"Unknown profile: {store.profile}")
                items, source = collect(store, profiles[store.profile])
            collected.append((store, items, source))
            status.update(status="demo" if args.demo else "collected", item_count=len(items))
            print(f"{store.store_id}: {len(items)} items{' (synthetic demo)' if args.demo else ''}")
        except Exception as exc:
            # Continue other stores, but preserve failures in both the workbook and exit code.
            status["message"] = f"{type(exc).__name__}: {exc}"
            print(f"{store.store_id}: {status['message']}", file=sys.stderr)
        statuses.append(status)
    now = datetime.now(ZoneInfo("America/New_York"))
    prefix = "DEMO_" if args.demo else ""
    output = args.output or ROOT / "reports" / f"{prefix}menu_prices_{now:%Y%m%d_%H%M%S_%f}.xlsx"
    if output.exists():
        print(f"Refusing to overwrite existing report: {output}", file=sys.stderr)
        return 2
    method = 'user-reviewed browser capture' if args.interactive else 'automatic extraction'
    if not args.interactive and not args.demo and all(profiles.get(s.profile, {}).get('mode') == 'trained' for s in stores):
        method = 'taught-page autorun (only taught pages)'
    write_report(output, collected, statuses, now, args.demo, capture_method=method)
    print(f"Saved {output}")
    return 1 if any(s["status"] in ("failed", "partial", "skipped") for s in statuses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
