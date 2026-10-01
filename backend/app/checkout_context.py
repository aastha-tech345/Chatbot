"""Bounded checkout draft, separate from truncated conversational text."""
import re
from copy import deepcopy


def update_checkout_context(previous: dict, message: str, plan, data=None) -> dict:
    context = deepcopy(previous)
    if re.search(r"\b(cancel checkout|stop checkout|never mind|forget checkout)\b", message, re.I):
        return {}
    if re.search(r"\b(buy|checkout|purchase)\b", message, re.I):
        context["active"] = True
    if data:
        products = [r for r in data if isinstance(r, dict) and ("variants" in r or "brand_name" in r or "sku" in r) and "quantity" not in r]
        if products:
            fields = {"id", "product_id", "name", "product_name", "price", "sale_price", "currency", "variants"}
            context["products"] = [{k: v for k, v in r.items() if k in fields} for r in products[:20]]
    if not context.get("active"):
        return context
    params = context.setdefault("parameters", {})
    products = context.get("products", [])
    selected = None
    match = re.search(r"\b(first|second|third|fourth|fifth)\b", message, re.I)
    if match and not re.search(r"\b(address|order)\b", message, re.I):
        index = ["first", "second", "third", "fourth", "fifth"].index(match.group(1).lower())
        if index < len(products):
            selected = products[index]
    if selected is None:
        selected = next((p for p in products if str(p.get("id", "!missing!")) in message or
                         (p.get("name") and p["name"].lower() in message.lower())), None)
    if selected is None and len(products) == 1 and re.search(r"\b(buy|checkout|purchase|this product)\b", message, re.I):
        selected = products[0]
    if selected:
        variants = selected.get("variants") or []
        variant = next((v for v in variants if v.get("is_default")), variants[0] if variants else {})
        price = selected.get("sale_price") or selected.get("price") or variant.get("price")
        if price is not None and selected.get("id") and selected.get("name"):
            existing = next((item for item in params.get("items", []) if item.get("product_id") == selected["id"]), {})
            params["items"] = [{
                "product_id": selected["id"],
                "variant_id": variant.get("id"),
                "name": selected["name"],
                "quantity": existing.get("quantity", 1),
                "unit_amount": price,
            }]
    email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", message)
    if email:
        params["customer_email"] = email.group(0)
    # Keep only declared checkout fields; never retain auth/tool execution context.
    if plan and plan.route_name and re.search(r"checkout|payment_session", plan.route_name, re.I):
        context["route_name"] = plan.route_name
        fields = {"items", "customer_email", "shipping_name", "address_line1", "city", "state", "postal_code", "coupon_code"}
        params.update({k: v for k, v in plan.parameters.items() if k in fields and v not in (None, "", [])})
    return context
