from __future__ import annotations

import re
from math import isnan
from typing import Iterable


def normalize_name(name: object) -> str:
    return str(name).lower().strip().replace("-", " ").replace("_", " ")


def normalize_key(value: object) -> str:
    text = normalize_name(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def compact_text(parts: Iterable[object]) -> str:
    cleaned = [str(part).strip() for part in parts if str(part).strip()]
    return " ".join(cleaned)


def split_terms(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, float) and isnan(value):
        return []
    terms = re.split(r"[,;\n]+", str(value))
    return [term.strip() for term in terms if term.strip()]


def to_bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    text = normalize_name(value)
    return text in {"1", "true", "yes", "y", "available", "included", "included."}


def to_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))
