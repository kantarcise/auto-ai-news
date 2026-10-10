"""Shared visibility, normalization and bounded code-example evidence."""

import re

MAX_CONTENT_CHARS = 12000

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def blocked_element(tag: str, attrs: dict) -> bool:
    identity = " ".join([attrs.get("id") or "", attrs.get("class") or ""]).lower()
    return (
        tag in {"script", "style", "nav", "footer", "aside", "form", "noscript", "svg"}
        or "hidden" in attrs
        or (attrs.get("aria-hidden") or "").lower() == "true"
        or (attrs.get("role") or "").lower() in {"navigation", "banner", "contentinfo"}
        or re.search(
            r"display\s*:\s*none|visibility\s*:\s*hidden",
            (attrs.get("style") or "").lower(),
        )
        or re.search(
            r"\b(comments?|related-posts|share-buttons|newsletter-signup)\b",
            identity,
        )
    )


def analyze_parts(parts: list[tuple[str, bool]], limit: int) -> tuple[str, bool, bool]:
    """Shared normalized text window and meaningful-code definition for both paths."""
    text = ""
    code = False
    truncated = False
    for data, in_code in parts:
        normalized = re.sub(r"\s+", " ", data).strip()
        if not normalized:
            continue
        separator = " " if text else ""
        available = max(0, limit - len(text) - len(separator))
        excerpt = normalized[:available]
        if excerpt:
            text += separator + excerpt
            if in_code and re.search(
                r"[=(){};]|\b(?:import|def|pip|python|docker|curl|torchrun)\b", excerpt
            ):
                code = True
        truncated |= len(normalized) > available
    return text, code, truncated
