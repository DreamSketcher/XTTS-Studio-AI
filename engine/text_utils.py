import re

# =========================
# LIST DETECTION (shared)
# =========================
LIST_PATTERNS = [
    r"^\s*[\-•–—]\s",
    r"^\s*\d+[.)]\s",
]

_LIST_ITEM_RE = re.compile("|".join(LIST_PATTERNS))


def is_list_item(text: str) -> bool:
    """True, если строка начинается как пункт списка (маркер или нумерация)."""
    return bool(_LIST_ITEM_RE.match(text or ""))


def has_inline_list(text: str) -> bool:
    """True, если внутри строки похоже на перечисление через запятые (2+ запятых)."""
    return (text or "").count(",") >= 2
