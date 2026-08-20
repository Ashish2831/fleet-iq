"""Input sanitization for user-controlled strings (notes, names, free text)."""

from __future__ import annotations

import html
import re
from typing import Any

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAGS = re.compile(r"<[^>]*>")
_SCRIPTISH = re.compile(
    r"(?is)javascript\s*:|data\s*:|vbscript\s*:|on\w+\s*=",
)


def strip_control_chars(value: str) -> str:
    return _CONTROL.sub("", value)


def strip_html(value: str) -> str:
    no_tags = _TAGS.sub("", value)
    return html.unescape(no_tags)


def sanitize_text(value: Any, *, max_len: int = 4000, allow_blank: bool = True) -> str:
    if value is None:
        return ""
    text = strip_control_chars(strip_html(str(value))).strip()
    text = _SCRIPTISH.sub("", text)
    if max_len and len(text) > max_len:
        text = text[:max_len]
    if not text and not allow_blank:
        raise ValueError("value must not be blank")
    return text


def sanitize_dict_strings(data: dict[str, Any], keys: list[str], *, max_len: int = 4000) -> dict[str, Any]:
    out = dict(data)
    for key in keys:
        if key in out and out[key] is not None:
            out[key] = sanitize_text(out[key], max_len=max_len)
    return out


def sanitize_errors(detail: Any, *, debug: bool = False) -> Any:
    """Hide internals from API clients when not in DEBUG."""
    if debug:
        return detail
    if isinstance(detail, dict):
        return {str(k): sanitize_errors(v, debug=False) for k, v in detail.items()}
    if isinstance(detail, list):
        return [sanitize_errors(v, debug=False) for v in detail]
    text = str(detail)
    lowered = text.lower()
    if any(
        token in lowered
        for token in (
            "traceback",
            "operationalerror",
            "psycopg",
            "sqlalchemy",
            "django.db",
            "redis.",
            "file \"/",
            "line ",
        )
    ):
        return "An unexpected error occurred"
    return text[:500]
