import re


def normalize_category_value(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"(^-|-$)", "", normalized)


def format_category_label(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    parts = [part for part in cleaned.split("-") if part]
    if not parts:
        return value.strip()
    return "-".join(part.capitalize() for part in parts)
