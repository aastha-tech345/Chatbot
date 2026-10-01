"""Preserve domain records and describe them without coupling to operation names."""
import re
from typing import Any


def records_from(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"name": item} for item in value if isinstance(item, (dict, str))]
    if not isinstance(value, dict):
        return []
    for key in ("items", "cart_items", "results", "products", "addresses", "orders", "categories", "brands", "data"):
        if isinstance(value.get(key), list):
            return records_from(value[key])
        if key == "data" and isinstance(value.get(key), dict):
            return records_from(value[key])
    return [value] if value else []


def resolve_entity_type(route, records: list[dict], intent: str = "") -> str:
    # Route metadata wins over overlapping fields (e.g. product_id in a cart line).
    hints = " ".join(str(getattr(route, key, "") or "") for key in ("path", "name", "description"))
    for pattern, entity in ((r"address", "address"), (r"cart", "cart_item"), (r"order", "order"),
                            (r"categor", "category"), (r"brand", "brand"), (r"manufacturer", "manufacturer"),
                            (r"profile|/auth/me\b|customer profile", "profile"), (r"product", "product")):
        if re.search(pattern, hints, re.I):
            return entity
    keys = set().union(*(r.keys() for r in records)) if records else set()
    if keys & {"line1", "address_line1", "addressLine1", "postal_code", "postalCode"}:
        return "address"
    if keys & {"order_number", "order_status", "order_id"}:
        return "order"
    if "quantity" in keys and keys & {"line_total", "product", "unit_price"}:
        return "cart_item"
    if keys & {"sku", "variants", "brand_name", "product_name"}:
        return "product"
    if "email" in keys and keys & {"name", "full_name", "first_name"}:
        return "profile"
    return "unknown"


def entity_response(route, payload: Any, intent: str = "") -> dict:
    records = records_from(payload)
    entity = resolve_entity_type(route, records, intent)
    if entity == "cart_item":
        records = [{**(r.get("product") if isinstance(r.get("product"), dict) else {}), **r} for r in records]
    titles = {"address": "Your Addresses", "cart_item": "Your Cart", "product": "Products", "order": "Your Orders",
              "category": "Categories", "brand": "Brands", "manufacturer": "Manufacturers", "profile": "Your Profile"}
    result = {"type": "entity_list", "entity_type": entity, "title": titles.get(entity, "Results"),
              "count": len(records), "items": records}
    if isinstance(payload, dict):
        wrapper = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        result["summary"] = {k: v for k, v in wrapper.items() if k in
                             {"total_items", "subtotal", "discount", "discount_total", "total", "total_amount", "currency", "shipping", "tax"}}
        result["pagination"] = {k: v for k, v in wrapper.items() if k in {"page", "per_page", "total", "total_pages", "has_more"}}
    return result


def entity_summary(entity: str, count: int) -> str:
    nouns = {"address": ("address", "addresses"), "cart_item": ("item", "items"), "category": ("category", "categories"),
             "product": ("product", "products"), "order": ("order", "orders"), "brand": ("brand", "brands"),
             "manufacturer": ("manufacturer", "manufacturers"), "profile": ("profile", "profiles")}
    singular, plural = nouns.get(entity, ("item", "items"))
    return f"{'Your cart has' if entity == 'cart_item' else 'Found'} {count} {singular if count == 1 else plural}."
