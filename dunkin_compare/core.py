from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path


def normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


@dataclass(frozen=True)
class Store:
    group: str
    store_id: str
    brand: str
    address: str
    market: str
    channel: str
    menu_url: str
    profile: str


@dataclass(frozen=True)
class Item:
    category: str
    name: str
    variant: str
    price: Decimal
    currency: str


def load_stores(path: Path, group: str) -> list[Store]:
    required = ["store_id", "brand", "address", "market", "channel", "menu_url", "profile"]
    stores = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != required:
            raise ValueError(f"{path}: expected columns {','.join(required)}")
        for line, row in enumerate(reader, 2):
            if not any(row.values()):
                continue
            if None in row or any(row.get(k) is None for k in required):
                raise ValueError(f"{path}:{line}: malformed CSV row; quote addresses containing commas")
            values = {k: row[k].strip() for k in required}
            if not values["store_id"] or not values["address"]:
                raise ValueError(f"{path}:{line}: store_id and address are required")
            stores.append(Store(group=group, **values))
    return stores


def price_amount(value: object) -> Decimal:
    # Reject ranges, 'from' prices, and ambiguous thousands/decimal formats.
    text = str(value).strip()
    if not re.fullmatch(r"\$?\s*\d+(?:\.\d{1,2})?", text):
        raise ValueError(f"Not an exact price: {text!r}")
    try:
        amount = Decimal(text.replace("$", "").strip())
    except InvalidOperation as exc:
        raise ValueError("Invalid price") from exc
    if amount < 0 or not amount.is_finite():
        raise ValueError("Invalid price")
    return amount


def make_item(category: str, name: str, variant: str, price: object, currency: str) -> Item:
    if not category.strip() or not name.strip():
        raise ValueError("Menu item is missing its name or category")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Menu item requires an explicit three-letter currency")
    return Item(category.strip(), name.strip(), variant.strip(), price_amount(price), currency)


def deduplicate(items: list[Item]) -> list[Item]:
    seen = {}
    for item in items:
        key = (normalized(item.category), normalized(item.name), normalized(item.variant), item.currency)
        if key in seen and seen[key].price != item.price:
            raise ValueError(f"Conflicting prices for {item.name} / {item.variant}; refine the profile")
        seen[key] = item
    return list(seen.values())


class JsonScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.active = True
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.active = False
            self.documents.append(json.loads("".join(self.parts)))


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def has_type(node, expected):
    types = node.get("@type", [])
    return expected in (types if isinstance(types, list) else [types])


def address_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(value.get(k, "")) for k in
                        ["streetAddress", "addressLocality", "addressRegion", "postalCode"])
    return ""


def parse_jsonld(html: str, expected_address: str) -> list[Item]:
    parser = JsonScripts()
    parser.feed(html)
    restaurants = [node for doc in parser.documents for node in objects(doc)
                   if has_type(node, "Restaurant") or has_type(node, "FoodEstablishment")]
    matched = [r for r in restaurants if normalized(address_text(r.get("address")))
               == normalized(expected_address)]
    if len(matched) != 1:
        raise ValueError("Cannot verify a unique selected store address in menu data")
    menu = matched[0].get("hasMenu")
    if not isinstance(menu, (dict, list)):
        raise ValueError("Selected store does not embed a structured menu; a browser profile is needed")
    items = []

    def visit(value, category=""):
        if isinstance(value, list):
            for child in value:
                visit(child, category)
        elif isinstance(value, dict):
            if has_type(value, "MenuSection"):
                category = str(value.get("name", ""))
            if has_type(value, "MenuItem"):
                offers = value.get("offers", [])
                offers = offers if isinstance(offers, list) else [offers]
                if not offers:
                    raise ValueError(f"Missing price for {value.get('name', 'menu item')}")
                for offer in offers:
                    if offer.get("availability", "").endswith(("OutOfStock", "Discontinued")):
                        continue
                    items.append(make_item(category or str(value.get("category", "")),
                                           str(value.get("name", "")),
                                           str(offer.get("name", value.get("size", ""))),
                                           offer.get("price", ""), str(offer.get("priceCurrency", ""))))
            for key in ("hasMenuSection", "hasMenuItem"):
                if key in value:
                    visit(value[key], category)

    visit(menu)
    if not items:
        raise ValueError("No priced menu items found for the selected store")
    return deduplicate(items)
