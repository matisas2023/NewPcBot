import re
from typing import Iterable, Optional

_COMMAND_PREFIX_RE = re.compile(r"^[\W_]+", re.UNICODE)


def normalize_command(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = _COMMAND_PREFIX_RE.sub("", cleaned)
    return cleaned


def is_command(text: Optional[str], command: str) -> bool:
    return normalize_command(text) == command


def is_allowed_command(text: Optional[str], allowed: Iterable[str]) -> bool:
    return normalize_command(text) in allowed
