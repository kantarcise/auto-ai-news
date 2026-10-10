"""Conservative, bounded public article-body retrieval using the standard library."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

try:
    from scripts.html_evidence import (
        MAX_CONTENT_CHARS,
        VOID_TAGS,
        analyze_parts,
        blocked_element,
    )
except ModuleNotFoundError:
    from html_evidence import (
        MAX_CONTENT_CHARS,
        VOID_TAGS,
        analyze_parts,
        blocked_element,
    )

MAX_BYTES = 1_000_000
TIMEOUT = 8
MAX_REQUESTS = 20
MIN_WORDS = 100


class BodyParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.regions = []
        self.active = []
        self.paywall = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").lower().split())
        identity = " ".join([attrs.get("id") or "", attrs.get("class") or ""]).lower()
        if re.search(r"\b(paywall|subscription-gate|subscribe-wall)\b", identity):
            self.paywall = True
        blocked = bool(self.stack and self.stack[-1][1]) or blocked_element(tag, attrs)
        region = None
        if not blocked and (
            tag in {"article", "main"}
            or classes
            & {
                "post-content",
                "article-content",
                "article-body",
                "blog-content",
                "prose",
            }
        ):
            region = len(self.regions)
            self.regions.append((tag == "article", []))
            self.active.append(region)
        if tag not in VOID_TAGS:
            self.stack.append((tag, bool(blocked), region))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                for _, _, region in self.stack[index:]:
                    if region is not None:
                        self.active.remove(region)
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not self.stack or self.stack[-1][1]:
            return
        for region in self.active:
            self.regions[region][1].append(
                (data, any(tag in {"pre", "code"} for tag, _, _ in self.stack))
            )


def extract_body_evidence(document: str) -> tuple[str, str, dict]:
    parser = BodyParser()
    parser.feed(document)
    if parser.paywall or re.search(
        r'"isAccessibleForFree"\s*:\s*(?:false|"false")', document, re.IGNORECASE
    ):
        return "", "Possible subscription gate; full body not established.", {}
    if sum(article for article, _ in parser.regions) > 1:
        return "", "Multiple article regions; a single body not established.", {}
    candidates = []
    for article, parts in parser.regions:
        text = re.sub(r"\s+", " ", " ".join(data for data, _ in parts)).strip()
        if len(re.findall(r"\b[\w'-]+\b", text)) >= MIN_WORDS:
            candidates.append((article, len(text), text, parts))
    if not candidates:
        return "", "No sufficiently long article/main body recognized.", {}
    _, _, text, parts = max(candidates, key=lambda row: row[:2])
    analyzed, code, _ = analyze_parts(parts, MAX_CONTENT_CHARS)
    return (
        text,
        "",
        {
            "code": code,
            "analyzed_characters": len(analyzed),
            "limit": MAX_CONTENT_CHARS,
        },
    )


def extract_body(document: str) -> tuple[str, str]:
    """Preserve the text-only API and reading-time behavior."""
    text, reason, _ = extract_body_evidence(document)
    return text, reason


class BoundedRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme not in {"http", "https"}:
            raise ValueError("Unsupported article redirect scheme.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_body(
    url: str, user_agent: str, *, structure: dict | None = None
) -> tuple[str, str]:
    """Optionally fill bounded structural metadata without another request."""
    if structure is not None:
        structure.clear()
    if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        return "", "Unsupported article URL scheme."
    request = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "text/html"}
    )
    try:
        with urllib.request.build_opener(BoundedRedirects()).open(
            request, timeout=TIMEOUT
        ) as response:
            if response.headers.get_content_type() not in {
                "text/html",
                "application/xhtml+xml",
            }:
                return "", "Article response was not HTML."
            if response.headers.get("Content-Encoding", "identity") != "identity":
                return "", "Encoded article response not supported."
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return (
                    "",
                    "Article exceeded response-size limit; truncated text not estimated.",
                )
            charset = response.headers.get_content_charset() or "utf-8"
            text, reason, metadata = extract_body_evidence(
                raw.decode(charset, errors="replace")
            )
            if structure is not None:
                structure.update(metadata)
            return text, reason
    except (OSError, ValueError, LookupError) as exc:
        return "", f"Article retrieval failed: {type(exc).__name__}."
