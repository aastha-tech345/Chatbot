from datetime import date, timedelta
import re


_DAY_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def parse_order_date_range(prompt: str, *, today: date | None = None) -> tuple[str, str] | None:
    normalized = prompt.lower()
    match = re.search(r"\b(?:last|past|previous)\s+(\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten)\s+days?\b", normalized)
    if match is None and re.search(r"\b(?:last|past|previous)\s+week\b", normalized):
        days = 7
    elif match is None:
        return None
    else:
        value = match.group(1)
        days = int(value) if value.isdigit() else _DAY_WORDS[value]
    if days < 1 or days > 3650:
        return None
    end = today or date.today()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()