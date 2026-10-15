"""Best-effort article evidence for opt-in evaluation, never admission or ranking."""

from __future__ import annotations

import gzip
import hashlib
import http.client
import io
import re
import urllib.parse
import urllib.request
import zlib
from datetime import UTC, datetime
from html.parser import HTMLParser

try:
    from scripts.article_content import MAX_REQUESTS, TIMEOUT, BoundedRedirects
    from scripts.html_evidence import MAX_CONTENT_CHARS, VOID_TAGS, blocked_element
except ModuleNotFoundError:
    from article_content import MAX_REQUESTS, TIMEOUT, BoundedRedirects
    from html_evidence import MAX_CONTENT_CHARS, VOID_TAGS, blocked_element

# HTML can contain substantial scripts without a correspondingly large body.
# Reject oversized responses entirely rather than parse an incomplete document.
MAX_BYTES = 3_000_000
MIN_FEED_WORDS = 100
BODY_CLASSES = {
    "post-content",
    "article-content",
    "article-body",
    "blog-content",
    "prose",
    "entry",
}
GATE = re.compile(r"\b(?:paywall|subscription-gate|subscribe-wall)\b")
CTA = re.compile(
    r"^\s*(?:keep reading with|subscribe to .* to keep reading)", re.IGNORECASE
)


class EvidenceParser(HTMLParser):
    """Collect visible regions; never use scripts, hidden text or gate contents."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.regions = []
        self.region_kinds = []
        self.active = []
        self.preview = False
        self.stopped = set()
        self.visible_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        identity = " ".join([attrs.get("id") or "", attrs.get("class") or ""]).lower()
        classes = set((attrs.get("class") or "").lower().split())
        # Invisible/blocked templates are not visible subscription boundaries.
        blocked = (
            bool(self.stack and self.stack[-1][1])
            or any(region in self.stopped for region in self.active)
            or "entryfooter" in classes
            or blocked_element(tag, attrs)
        )
        gate = not blocked and bool(GATE.search(identity))
        self.preview |= gate
        if gate:
            self.stopped.update(self.active)
            blocked = True
        region = None
        if not blocked and (tag in {"article", "main"} or classes & BODY_CLASSES):
            priority = 3 if classes & BODY_CLASSES else 2 if tag == "article" else 1
            parent = self.active[-1] if self.active else None
            if (
                tag != "article"
                and parent is not None
                and self.region_kinds[parent] in {"article", "body"}
            ):
                # Nested body classes belong to this article, in document order.
                # Only a nested semantic article starts independent evidence.
                rank, parts = self.regions[parent]
                self.regions[parent] = (max(rank, priority), parts)
            else:
                region = len(self.regions)
                self.regions.append((priority, []))
                kind = (
                    "article"
                    if tag == "article"
                    else "body"
                    if classes & BODY_CLASSES
                    else "main"
                )
                self.region_kinds.append(kind)
                self.active.append(region)
        if tag not in VOID_TAGS:
            self.stack.append((tag, blocked, region))

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
        if CTA.search(data):
            self.preview = True
            self.stopped.update(self.active)
        # A child article/body is separate evidence, not part of its layout
        # parent. This keeps recommendation cards out of a main-region body.
        for region in self.active[-1:]:
            if region not in self.stopped:
                self.regions[region][1].append(data)
                self.visible_parts.append(data)


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def evidence(text, provenance, **metadata):
    text = normalize(text)
    excerpt = text[:MAX_CONTENT_CHARS]
    return {
        "text": excerpt,
        "provenance": provenance,
        "completeness": "unknown",
        "truncated": len(excerpt) != len(text),
        "characters_before_limit": len(text),
        "word_count": len(excerpt.split()),
        "text_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
        **metadata,
    }


def extract(document):
    parser = EvidenceParser()
    parser.feed(document)
    candidates = [
        (priority, normalize(" ".join(parts))) for priority, parts in parser.regions
    ]
    candidates = [(priority, text) for priority, text in candidates if text]
    if not candidates:
        return evidence(
            "", "unavailable", reason="No visible article region recognized."
        )
    substantial = [row for row in candidates if len(row[1].split()) >= MIN_FEED_WORDS]
    eligible = substantial or candidates
    priority = max(row[0] for row in eligible)
    texts = list(dict.fromkeys(text for rank, text in eligible if rank == priority))
    substantive = [text for text in texts if len(text.split()) >= MIN_FEED_WORDS]
    if len(substantive) == 1:
        # Ignore short sibling cards, not a second substantial story.
        text = substantive[0]
    elif len(texts) == 1:
        text = texts[0]
    else:
        return evidence("", "unavailable", reason="Multiple plausible article regions.")
    preview = parser.preview or bool(
        re.search(
            r'"isAccessibleForFree"\s*:\s*(?:false|"false")', document, re.IGNORECASE
        )
    )
    return evidence(
        text,
        "public_preview" if preview else "article_body",
        completeness="partial" if preview else "unknown",
        short=len(text.split()) < MIN_FEED_WORDS,
    )


def fetch(url, user_agent):
    if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        return evidence("", "unavailable", reason="Unsupported article URL scheme.")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.build_opener(BoundedRedirects()).open(
            request, timeout=TIMEOUT
        ) as response:
            metadata = {
                "final_url": response.geturl(),
                "fetched_at": datetime.now(UTC).isoformat(),
            }
            if response.headers.get_content_type() not in {
                "text/html",
                "application/xhtml+xml",
            }:
                return evidence(
                    "",
                    "unavailable",
                    reason="Article response was not HTML.",
                    **metadata,
                )
            encoding = (
                response.headers.get("Content-Encoding", "identity").strip().lower()
            )
            if encoding not in {"identity", "gzip"}:
                return evidence(
                    "",
                    "unavailable",
                    reason="Encoded response unsupported.",
                    **metadata,
                )
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return evidence(
                    "",
                    "unavailable",
                    reason="Article exceeded 3 MB response limit.",
                    **metadata,
                )
            decoded = raw
            if encoding == "gzip":
                # Some hosts gzip despite Accept-Encoding: identity. Bound the
                # decoded stream too; gzip.decompress would allocate unboundedly.
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                    decoded = compressed.read(MAX_BYTES + 1)
                if len(decoded) > MAX_BYTES:
                    return evidence(
                        "",
                        "unavailable",
                        reason="Decoded article exceeded 3 MB limit.",
                        **metadata,
                    )
            document = decoded.decode(
                response.headers.get_content_charset() or "utf-8", errors="replace"
            )
            return {
                **extract(document),
                **metadata,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
            }
    except (
        OSError,
        ValueError,
        LookupError,
        EOFError,
        zlib.error,
        http.client.HTTPException,
    ) as exc:
        return evidence(
            "", "unavailable", reason=f"Article retrieval failed: {type(exc).__name__}."
        )


def feed_fragment(text, content_format):
    """Return visible feed text and known subscription-preview status together."""
    if content_format != "html":
        return normalize(text), False
    parser = EvidenceParser()
    # A wrapper supplies a region for an RSS/Atom fragment without its own body.
    parser.feed("<article>" + text + "</article>")
    preview = parser.preview or bool(
        re.search(r'"isAccessibleForFree"\s*:\s*(?:false|"false")', text, re.IGNORECASE)
    )
    return normalize(" ".join(parser.visible_parts)), preview


def feed_text(text, content_format):
    return feed_fragment(text, content_format)[0]


def feed_evidence(text, content_format, provenance):
    text, preview = feed_fragment(text, content_format)
    return evidence(
        text,
        provenance,
        feed_origin=provenance,
        completeness="partial" if preview else "unknown",
    )


class EvidenceCollector:
    """One run's bounded URL cache. Captures never mutate generator Items."""

    def __init__(self, user_agent, request_limit=MAX_REQUESTS):
        self.user_agent = user_agent
        self.request_limit = request_limit
        self.cache = {}

    def capture(self, item):
        content = feed_evidence(
            item.content, item.content_format, item.content_provenance
        )
        if (
            item.content_provenance in {"rss_content", "atom_content"}
            and content["word_count"] >= MIN_FEED_WORDS
        ):
            return content
        # Items already carry canonical URLs; tracking variants share a fetch.
        key = item.canonical_url or item.url
        if key not in self.cache:
            if len(self.cache) >= self.request_limit:
                fetched = evidence(
                    "", "unavailable", reason="Article request budget exhausted."
                )
            else:
                fetched = fetch(item.url, self.user_agent)
                self.cache[key] = fetched
        else:
            fetched = self.cache[key]
        if fetched["text"]:
            return dict(fetched)
        if content["text"]:
            fallback = {**content, "provenance": "feed_excerpt"}
        else:
            summary = feed_evidence(item.summary, "html", "feed_summary")
            fallback = (
                summary if summary["text"] else evidence(item.title, "title_only")
            )
        fallback["retrieval"] = {
            key: value for key, value in fetched.items() if key != "text"
        }
        return fallback
