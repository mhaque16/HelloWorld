from __future__ import annotations

import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urlsplit

from .core import Store, deduplicate, make_item, normalized, parse_jsonld

USER_AGENT = "MenuPriceResearch/0.1"


def read_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(10_000_001)
        if len(data) > 10_000_000:
            raise ValueError("Menu response exceeds 10 MB")
        return data.decode(response.headers.get_content_charset() or "utf-8")


def check_robots(url: str):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("menu_url must be a public HTTPS URL without embedded credentials")
    robots_url = f"https://{parsed.netloc}/robots.txt"
    try:
        content = read_url(robots_url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        raise ValueError(f"Cannot check robots.txt (HTTP {exc.code})") from exc
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(content.splitlines())
    if not parser.can_fetch(USER_AGENT, url):
        raise ValueError("The site's robots.txt disallows this menu URL")
    delay = parser.crawl_delay(USER_AGENT)
    if delay:
        time.sleep(delay)


def collect(store: Store, profile: dict):
    if profile.get('mode') == 'trained':
        from .training import collect_trained
        return collect_trained(store, profile)
    if not store.menu_url:
        raise ValueError("Address saved; store-specific menu_url is needed. Address lookup is not implemented.")
    if not store.brand or not store.market or store.channel not in ("pickup", "delivery", "in_store"):
        raise ValueError("Set brand, market, and channel (pickup, delivery, or in_store)")
    check_robots(store.menu_url)
    mode = profile.get("mode")
    if mode == "jsonld":
        return parse_jsonld(read_url(store.menu_url), store.address), store.menu_url
    if mode != "browser":
        raise ValueError("Unknown profile mode; use jsonld or browser")
    # Selectors must be verified against the real selected-store ordering page.
    for key in ("location_selector", "item_selector", "name_selector", "category_selector",
                "price_selector", "variant_selector", "currency"):
        if not profile.get(key):
            raise ValueError(f"Browser profile requires {key}")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            response = page.goto(store.menu_url, wait_until="domcontentloaded", timeout=45000)
            if response is None or response.status >= 400:
                raise ValueError(f"Menu failed to load (HTTP {response.status if response else 'unknown'})")
            location = page.locator(profile["location_selector"])
            location.wait_for(timeout=30000)
            if location.count() != 1 or normalized(location.inner_text()) != normalized(store.address):
                raise ValueError("Page's selected-store address does not match the input address")
            cards = page.locator(profile["item_selector"])
            cards.first.wait_for(timeout=30000)
            # A profile can specify an explicit marker signaling the full menu has loaded.
            if profile.get("ready_selector"):
                page.locator(profile["ready_selector"]).wait_for(timeout=30000)
            items = []
            for card in cards.all():
                fields = {}
                for field in ("name", "category", "price", "variant"):
                    node = card.locator(profile[f"{field}_selector"])
                    if node.count() != 1:
                        raise ValueError(f"Expected exactly one {field} in each menu item")
                    fields[field] = node.inner_text().strip()
                items.append(make_item(fields["category"], fields["name"], fields["variant"],
                                       fields["price"], profile["currency"]))
            if not items:
                raise ValueError("No priced menu items found")
            return deduplicate(items), page.url
        finally:
            browser.close()
