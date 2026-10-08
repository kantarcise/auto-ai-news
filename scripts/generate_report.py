#!/usr/bin/env python3
"""Generate a daily AI news report from trusted public feeds."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import math
import re
import sys
import textwrap
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

try:
    from scripts.article_content import MAX_REQUESTS, fetch_body
except ModuleNotFoundError:
    from article_content import MAX_REQUESTS, fetch_body

try:
    from scripts.editorial_relevance import Relevance, assess
except ModuleNotFoundError:
    from editorial_relevance import Relevance, assess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "config" / "sources.json"
DEFAULT_OUTPUT = ROOT / "README.md"
USER_AGENT = "auto-ai-news/0.1 (+https://github.com/kantarcise/auto-ai-news)"
READING_WPM = 225
MIN_CONTENT_WORDS = 100
MAX_ITEMS = 30
MAX_PER_PUBLISHER = 4
LAB_ANNOUNCEMENT_BONUS = 0.75
DEFAULT_LOOKBACK_HOURS = 72
FETCH_TIMEOUT = 20
LINK_TIMEOUT = 10
AI_KEYWORDS = {
    "ai",
    "agi",
    "agentic",
    "software factory",
    "software factories",
    "spatial intelligence",
    "인공지능",
    "agent",
    "agents",
    "anthropic",
    "artificial intelligence",
    "chatgpt",
    "claude",
    "deepmind",
    "deepseek",
    "mistral",
    "qwen",
    "grok",
    "flux",
    "minimax",
    "kimi",
    "glm",
    "seedance",
    "seedream",
    "muse spark",
    "muse image",
    "muse video",
    "diffusion",
    "embedding",
    "eval",
    "evals",
    "frontier model",
    "generative",
    "gpt",
    "inference",
    "language model",
    "llama",
    "llm",
    "machine learning",
    "model",
    "multimodal",
    "neural",
    "openai",
    "prompt",
    "reasoning model",
    "research lab",
    "transformer",
}
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


@dataclass(frozen=True)
class Source:
    name: str
    homepage: str
    feed_url: str
    priority: int
    enabled: bool = True
    disabled_reason: str = ""
    format: str = "feed"
    category: str = "other"
    publisher: str = ""
    coverage: str = "mixed"


@dataclass
class Item:
    title: str
    url: str
    source: str
    source_priority: int
    summary: str = ""
    published: dt.datetime | None = None
    canonical_url: str = ""
    word_count: int = 0
    read_minutes: int | None = None
    stars: int = 1
    content: str = ""
    content_format: str = "text"
    content_provenance: str = "missing"
    category: str = "other"
    publisher: str = ""
    coverage: str = "mixed"
    story_kind: str = "other"
    rank_score: float | None = None
    related_coverage: list[Item] = field(default_factory=list)
    body_status: str = ""
    editorial_relevance: Relevance | None = None


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.rsplit(":", 1)[-1]
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.rsplit(":", 1)[-1]
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_space(" ".join(self.parts))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def load_sources(path: Path) -> list[Source]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Source(**entry) for entry in data]


def fetch_url(url: str, timeout: int = FETCH_TIMEOUT) -> tuple[int, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, response.geturl(), raw.decode(charset, errors="replace")


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    clean_query = [
        (key, value) for key, value in query if key.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urllib.parse.urlencode(clean_query, doseq=True),
            "",
        )
    )


def child_text(element: ET.Element, *names: str) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return normalize_space(found.text)
    return ""


def parse_datetime(value: str) -> dt.datetime | None:
    value = normalize_space(value)
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def listing_date(text: str) -> dt.datetime | None:
    match = re.search(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b", text)
    if match:
        for date_format in ("%B %d, %Y", "%b %d, %Y"):
            try:
                return dt.datetime.strptime(match[1], date_format).replace(
                    tzinfo=dt.timezone.utc
                )
            except ValueError:
                continue
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    return parse_datetime(match[0]) if match else None


class DatedNewsParser(HTMLParser):
    """Read dated article cards from the validated research/news listings."""

    def __init__(self, source: Source) -> None:
        super().__init__()
        self.source = source
        self.items: list[Item] = []
        self.href = ""
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.title_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a":
            self.href = attributes.get("href") or ""
            self.parts = []
            self.title_parts = []
            self.title_tag = ""
        if self.href and (
            tag in {"h2", "h3", "h4"}
            or (tag == "span" and "title" in (attributes.get("class") or "").lower())
        ):
            self.title_tag = tag

    def handle_data(self, data: str) -> None:
        if self.href:
            self.parts.append(data)
            if self.title_tag:
                self.title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self.title_tag:
            self.title_tag = ""
        if tag != "a" or not self.href:
            return
        text = normalize_space(" ".join(self.parts))
        title = normalize_space(" ".join(self.title_parts))
        published = listing_date(text)
        if published and title:
            self.items.append(
                Item(
                    title,
                    self.href,
                    self.source.name,
                    self.source.priority,
                    published=published,
                )
            )
        self.href = ""


class MetaNewsParser(HTMLParser):
    """Meta places a displayed date after the article title link, outside the anchor."""

    def __init__(self, source: Source) -> None:
        super().__init__()
        self.source = source
        self.items: list[Item] = []
        self.href = ""
        self.title_parts: list[str] = []
        self.in_anchor = False
        self.after_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href") or ""
            self.href = href if href.startswith("https://ai.meta.com/blog/") else ""
            self.title_parts = []
            self.after_title = ""
            self.in_anchor = bool(self.href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self.in_anchor = False

    def handle_data(self, data: str) -> None:
        if not self.href:
            return
        if self.in_anchor:
            self.title_parts.append(data)
            return
        self.after_title += data + " "
        title = normalize_space(" ".join(self.title_parts))
        published = listing_date(self.after_title)
        if published and title and title not in {"FEATURED", "Learn More", "Next"}:
            self.items.append(
                Item(
                    title,
                    self.href,
                    self.source.name,
                    self.source.priority,
                    published=published,
                )
            )
            self.href = ""
        elif len(self.after_title) > 100:
            self.href = ""


def parse_qwen_api(content: str, source: Source) -> list[Item]:
    payload = json.loads(content)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Qwen article API did not return a successful listing.")
    data = payload.get("data")
    rows = data.get("articles") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Qwen article API contained no article list.")  # noqa: TRY004 -- source schema failure
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path, title, extra = row.get("path"), row.get("title"), row.get("extra", {})
        if (
            not isinstance(path, str)
            or not isinstance(title, str)
            or not isinstance(extra, dict)
        ):
            continue
        published = parse_datetime(str(extra.get("date") or ""))
        if path and title and published:
            url = "https://qwen.ai/blog?" + urllib.parse.urlencode({"id": path})
            items.append(
                Item(
                    normalize_space(title),
                    url,
                    source.name,
                    source.priority,
                    published=published,
                )
            )
    if not items:
        raise ValueError("Qwen article API contained no recognized dated articles.")
    return items


def parse_source(content: str, source: Source) -> list[Item]:
    if source.format == "feed":
        return parse_feed(content, source)
    if source.format == "qwen_api":
        return parse_qwen_api(content, source)
    if source.format not in {"dated_html", "meta_html"}:
        raise ValueError(f"Unsupported source format: {source.format}")
    parser = (
        MetaNewsParser(source)
        if source.format == "meta_html"
        else DatedNewsParser(source)
    )
    parser.feed(content)
    if not parser.items:
        raise ValueError("Dated news listing contained no recognized article cards.")
    return parser.items


def parse_feed(xml_text: str, source: Source) -> list[Item]:
    root = ET.fromstring(xml_text)
    if root.tag.endswith("rss") or root.find("channel") is not None:
        entries = root.findall("./channel/item")
        return [parse_rss_item(entry, source) for entry in entries]
    entries = root.findall("{http://www.w3.org/2005/Atom}entry")
    return [parse_atom_entry(entry, source) for entry in entries]


def content_value(element: ET.Element | None) -> str:
    if element is None:
        return ""
    # Preserve XHTML structure for text extraction rather than flattening tags.
    if len(element):
        return (element.text or "") + "".join(
            ET.tostring(child, encoding="unicode") for child in element
        )
    return element.text or ""


def parse_rss_item(entry: ET.Element, source: Source) -> Item:
    title = child_text(entry, "title") or "Untitled"
    link = child_text(entry, "link", "guid")
    summary = child_text(entry, "description", "summary")
    published = parse_datetime(child_text(entry, "pubDate", "published", "updated"))
    content = content_value(
        entry.find("{http://purl.org/rss/1.0/modules/content/}encoded")
    )
    return Item(
        title,
        link,
        source.name,
        source.priority,
        summary,
        published,
        content=content,
        content_format="html",
        content_provenance="rss_content"
        if content.strip()
        else ("summary" if summary else "missing"),
    )


def parse_atom_entry(entry: ET.Element, source: Source) -> Item:
    ns = "{http://www.w3.org/2005/Atom}"
    title = child_text(entry, f"{ns}title") or "Untitled"
    link = ""
    for candidate in entry.findall(f"{ns}link"):
        rel = candidate.attrib.get("rel", "alternate")
        href = candidate.attrib.get("href", "")
        if href and rel == "alternate":
            link = href
            break
    if not link:
        link_node = entry.find(f"{ns}link")
        link = link_node.attrib.get("href", "") if link_node is not None else ""
    summary = child_text(entry, f"{ns}summary")
    published = parse_datetime(child_text(entry, f"{ns}published", f"{ns}updated"))
    node = entry.find(f"{ns}content")
    content_type = node.attrib.get("type", "text") if node is not None else "text"
    supported = (
        node is not None
        and not node.attrib.get("src")
        and content_type in {"text", "html", "xhtml"}
    )
    content = content_value(node) if supported else ""
    if not summary and supported:
        summary = child_text(entry, f"{ns}content")
    return Item(
        title,
        link,
        source.name,
        source.priority,
        summary,
        published,
        content=content,
        content_format="html" if content_type in {"html", "xhtml"} else "text",
        content_provenance="atom_content"
        if content.strip()
        else ("summary" if summary else "missing"),
    )


def ai_relevance_score(item: Item) -> int:
    text = f"{item.title} {item.summary}".lower()
    score = 0
    for keyword in AI_KEYWORDS:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, text):
            score += 2 if " " in keyword else 1
    return score


def is_ai_related(item: Item) -> bool:
    assessment = item.editorial_relevance
    if assessment is None:
        assessment = assess([{"title": item.title, "url": item.url}])[0]
    if assessment.event_listing:
        return False
    if assessment.admitted:
        return True
    if item.source in {"Latent Space", "smol.ai"}:
        return True
    title_only = Item(
        title=item.title,
        url=item.url,
        source=item.source,
        source_priority=item.source_priority,
    )
    return ai_relevance_score(title_only) > 0


def is_quiet_day_roundup(item: Item) -> bool:
    """Identify the publishers' quiet-day editions, not articles quoting the phrase."""
    if item.source not in {"Latent Space", "smol.ai"}:
        return False
    title = normalize_space(item.title).casefold()
    return (
        re.fullmatch(r"(?:\[ainews\]\s*)?not much happened today[.!]?", title)
        is not None
    )


def extract_text_from_html(html_text: str) -> str:
    parser = TextExtractor()
    parser.feed(html_text)
    return parser.text()


def estimate_reading_time(item: Item) -> int | None:
    """Estimate explicit feed content only; completeness is not established."""
    text = (
        extract_text_from_html(item.content)
        if item.content_format == "html"
        else item.content
    )
    item.word_count = len(re.findall(r"\b[\w'-]+\b", text))
    item.read_minutes = None
    if (
        item.content_provenance in {"rss_content", "atom_content", "article_body"}
        and item.word_count >= MIN_CONTENT_WORDS
    ):
        item.read_minutes = math.ceil(item.word_count / READING_WPM)
    return item.read_minutes


def reading_time_label(item: Item) -> str:
    if item.read_minutes is not None:
        label = (
            "extracted body"
            if item.content_provenance == "article_body"
            else "feed content"
        )
        return f"~{format_reading_time(item.read_minutes)} ({label})"
    if item.body_status:
        return "Read time unknown (article body unavailable)"
    if item.content.strip():
        return "Read time unknown (insufficient feed content)"
    if item.summary:
        return "Read time unknown (summary only)"
    return "Read time unknown (no article text)"


def enrich_article_bodies(
    items: list[Item], request_limit: int = MAX_REQUESTS
) -> list[tuple[str, str]]:
    """Enrich selected representatives only; failures never remove a story."""
    cache: dict[str, tuple[str, str]] = {}
    diagnostics = []
    for item in items:
        if estimate_reading_time(item) is not None:
            continue
        key = canonicalize_url(item.url)
        if key not in cache:
            cache[key] = (
                fetch_body(item.url, USER_AGENT)
                if len(cache) < request_limit
                else ("", "Article request budget exhausted.")
            )
        body, reason = cache[key]
        if body:
            item.content = body
            item.content_format = "text"
            item.content_provenance = "article_body"
            estimate_reading_time(item)
        else:
            item.body_status = reason
            diagnostics.append((item.source, f"Content: {item.title}: {reason}"))
    return diagnostics


def classify_story(item: Item) -> str:
    """Conservative headline rule; lab membership is not automatic importance."""
    if item.category != "frontier_lab" or not is_ai_related(item):
        return "other"
    title = item.title.casefold()
    if re.search(
        r"\b(partners?|partnership|customers?|case study|funding|raises|investment|acquisition|pricing|hiring|careers|conference)\b",
        title,
    ):
        return "other"
    if item.coverage == "research" or re.search(
        r"\b(research|benchmark|evaluations?|alignment|interpretability|discovers|proof|world model|spatial intelligence)\b",
        title,
    ):
        return "lab_research"
    brand = re.search(
        r"\b(qwen|grok|gpt|mistral|llama|flux|deepseek|claude|gemini|glm|kimi|minimax|seedance|seedream|muse spark|muse image|muse video)\b",
        title,
    )
    family_match = bool(
        item.editorial_relevance is not None
        and "model_family" in item.editorial_relevance.terms
    )
    model_topic = re.search(
        r"\b(model|llm|multimodal|inference|reasoning|agent|agents|diffusion)\b", title
    )
    if (brand or family_match or model_topic) and re.search(
        r"^(introducing|announcing|releasing|unveiling)\b", title
    ):
        return "lab_announcement"
    if (brand or family_match) and re.search(r"\d|\b(model|reasoning|vision)\b", title):
        return "lab_announcement"
    return "other"


def score_item(item: Item, now: dt.datetime) -> int:
    score = 1.0
    if item.source_priority >= 5:
        score += 1.25
    elif item.source_priority >= 3:
        score += 1.0
    if ai_relevance_score(item) >= 3:
        score += 1.0
    if item.published:
        age_hours = max(0.0, (now - item.published).total_seconds() / 3600)
        if age_hours <= 24:
            score += 1.0
        elif age_hours > 7 * 24:
            score -= 1.0
    item.story_kind = classify_story(item)
    if item.story_kind in {"lab_research", "lab_announcement"}:
        score += LAB_ANNOUNCEMENT_BONUS
    if item.editorial_relevance is not None:
        score += item.editorial_relevance.rank_bonus
    item.rank_score = score
    item.stars = max(1, min(5, math.ceil(score)))
    return item.stars


def item_sort_key(item: Item) -> tuple[float, dt.datetime]:
    published = item.published or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return item.rank_score if item.rank_score is not None else float(
        item.stars
    ), published


def freshness_reason(item: Item, now: dt.datetime, lookback_hours: int) -> str:
    if item.published is None:
        return "missing or invalid publication date"
    age = (now - item.published).total_seconds()
    if age < 0:
        return "future publication date"
    if age > lookback_hours * 3600:
        return "older than coverage window"
    return ""


def evaluation_metadata(item: Item) -> dict:
    """Export attributed metadata only, never feed text or article bodies."""
    return {
        "title": item.title,
        "url": item.url,
        "source": item.source,
        "publisher": item.publisher,
        "category": item.category,
        "published": item.published.isoformat() if item.published else None,
    }


def collect_items(
    sources: list[Source],
    now: dt.datetime,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    *,
    evaluation: dict | None = None,
) -> tuple[list[Item], list[tuple[str, str]]]:
    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be positive")
    if evaluation is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("Evaluation capture requires a timezone-aware clock")
    collection = []
    items: list[Item] = []
    pending: list[tuple[Item, dict | None]] = []
    unavailable: list[tuple[str, str]] = []
    for source in sources:
        if not source.enabled:
            unavailable.append(
                (source.name, source.disabled_reason or "Source disabled.")
            )
            continue
        if not source.feed_url:
            unavailable.append((source.name, "No feed URL configured."))
            continue
        try:
            status, final_url, feed_text = fetch_url(source.feed_url)
            if status >= 400:
                unavailable.append(
                    (source.name, f"HTTP {status} from {source.feed_url}.")
                )
                continue
            parsed_items = parse_source(feed_text, source)
        except (
            ET.ParseError,
            ValueError,
            TimeoutError,
            urllib.error.URLError,
            UnicodeDecodeError,
        ) as exc:
            unavailable.append((source.name, reason_from_error(exc)))
            continue
        freshness_counts: dict[str, int] = {}
        fresh_count = 0
        for item in parsed_items:
            item.category = source.category
            item.publisher = source.publisher or source.name
            item.coverage = source.coverage
            reason = freshness_reason(item, now, lookback_hours)
            record = None
            if evaluation is not None:
                record = evaluation_metadata(item)
                record["url"] = (
                    urllib.parse.urljoin(final_url, item.url) if item.url else ""
                )
                record["rejection_reason"] = reason
                collection.append(record)
            if reason:
                freshness_counts[reason] = freshness_counts.get(reason, 0) + 1
                continue
            fresh_count += 1
            if not item.url:
                if record is not None:
                    record["rejection_reason"] = "missing link"
                unavailable.append((source.name, "Feed item missing link."))
                continue
            item.url = urllib.parse.urljoin(final_url, item.url)
            item.canonical_url = canonicalize_url(item.url)
            if is_quiet_day_roundup(item):
                if record is not None:
                    record["rejection_reason"] = "quiet-day title policy"
                unavailable.append(
                    (
                        f"{item.source}: {item.title}",
                        "Quiet-day roundup excluded by title policy.",
                    )
                )
                continue
            pending.append((item, record))
        if not fresh_count:
            unavailable.append(
                (source.name, "Freshness: no dated entries within the coverage window.")
            )
        for reason, count in freshness_counts.items():
            unavailable.append(
                (source.name, f"Freshness: {count} entries excluded: {reason}.")
            )
    relevance = assess(
        [
            {"title": item.title, "summary": item.summary, "url": item.canonical_url}
            for item, _ in pending
        ]
    )
    for (item, record), assessment in zip(pending, relevance):
        item.editorial_relevance = assessment
        if record is not None:
            record["editorial_relevance"] = {
                "similarity": round(assessment.similarity, 6),
                "topic": assessment.topic,
                "matched_terms": list(assessment.terms),
                "rank_bonus": round(assessment.rank_bonus, 6),
            }
        if is_ai_related(item):
            estimate_reading_time(item)
            score_item(item, now)
            items.append(item)
        elif record is not None:
            record["rejection_reason"] = (
                "event listing without technical topic"
                if assessment.event_listing
                else "title relevance filter"
            )
    candidates = group_stories(dedupe_items(items))
    # Freeze group membership before selection mutates related coverage on fallback.
    groups = (
        [
            [member.url for member in [item, *item.related_coverage]]
            for item in candidates
        ]
        if evaluation is not None
        else []
    )
    link_outcomes = {} if evaluation is not None else None
    accessible, link_failures = filter_accessible_items(
        candidates, MAX_ITEMS, link_outcomes=link_outcomes
    )
    if evaluation is not None:
        # One review row per exact resolved URL; retain all occurrences in collection.
        rows = {}
        for record in collection:
            if record["url"]:
                rows.setdefault(
                    record["url"],
                    {k: v for k, v in record.items() if k != "rejection_reason"},
                )
        evaluation.update(
            schema_version=1,
            captured_at=now.astimezone(dt.timezone.utc).isoformat(),
            lookback_hours=lookback_hours,
            candidate_scope="all parsed entries with links, including pre-ranking rejects",
            collection=collection,
            story_groups=groups,
            link_outcomes=link_outcomes,
            diagnostics=unavailable + link_failures,
            policies={
                "frontier": {
                    "candidates": list(rows.values()),
                    "selected": [evaluation_metadata(item) for item in accessible],
                    "alternate_coverage": [
                        {
                            "representative_url": item.url,
                            "urls": [member.url for member in item.related_coverage],
                        }
                        for item in accessible
                        if item.related_coverage
                    ],
                }
            },
        )
    return accessible, unavailable + link_failures


def check_url_accessible(url: str, timeout: int = LINK_TIMEOUT) -> tuple[bool, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}, method="HEAD"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status < 400:
                return True, ""
            return False, f"HTTP {response.status}."
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 405}:
            return check_url_accessible_with_get(url, timeout)
        return False, f"HTTP {exc.code}."
    except urllib.error.URLError as exc:
        return False, f"Network error: {exc.reason}."


def check_url_accessible_with_get(url: str, timeout: int) -> tuple[bool, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status < 400:
                return True, ""
            return False, f"HTTP {response.status}."
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}."
    except urllib.error.URLError as exc:
        return False, f"Network error: {exc.reason}."


def filter_accessible_items(
    items: list[Item],
    limit: int,
    publisher_limit: int | None = MAX_PER_PUBLISHER,
    *,
    link_outcomes: dict | None = None,
) -> tuple[list[Item], list[tuple[str, str]]]:
    accessible: list[Item] = []
    if publisher_limit is not None and publisher_limit <= 0:
        raise ValueError("publisher_limit must be positive")
    publisher_counts: dict[str, int] = {}
    failures: list[tuple[str, str]] = []
    for index, item in enumerate(items):
        publisher = item.publisher or item.source
        if (
            publisher_limit is not None
            and publisher_counts.get(publisher, 0) >= publisher_limit
        ):
            failures.append(
                (
                    item.source,
                    f"Selection: publisher cap ({publisher_limit}) excluded {item.title}.",
                )
            )
            continue
        verified = []
        for member in [item, *item.related_coverage]:
            ok, reason = check_url_accessible(member.url)
            if link_outcomes is not None:
                link_outcomes[member.url] = {"accessible": ok, "reason": reason}
            if ok:
                verified.append(member)
            else:
                failures.append(
                    (f"{member.source}: [{member.title}]({member.url})", reason)
                )
        primary = next(
            (
                member
                for member in verified
                if publisher_limit is None
                or publisher_counts.get(member.publisher or member.source, 0)
                < publisher_limit
            ),
            None,
        )
        if primary is not None:
            primary.related_coverage = [
                member for member in verified if member is not primary
            ]
            accessible.append(primary)
            publisher = primary.publisher or primary.source
            publisher_counts[publisher] = publisher_counts.get(publisher, 0) + 1
            if len(accessible) == limit:
                remaining: dict[str, int] = {}
                for candidate in items[index + 1 :]:
                    remaining[candidate.source] = remaining.get(candidate.source, 0) + 1
                for source, count in remaining.items():
                    failures.append(
                        (
                            source,
                            f"Selection: report limit ({limit}) left {count} lower-ranked candidates unselected; links not checked.",
                        )
                    )
                break
        elif verified:
            failures.append(
                (
                    item.source,
                    "Selection: all accessible representatives reached their publisher cap.",
                )
            )
    return accessible, failures


def reason_from_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} from source."
    if isinstance(exc, urllib.error.URLError):
        return f"Network error: {exc.reason}."
    if isinstance(exc, ET.ParseError):
        return "Feed XML could not be parsed."
    return str(exc) or exc.__class__.__name__


def dedupe_items(items: list[Item]) -> list[Item]:
    best_by_url: dict[str, Item] = {}
    for item in items:
        existing = best_by_url.get(item.canonical_url)
        if existing is None or item_sort_key(item) > item_sort_key(existing):
            best_by_url[item.canonical_url] = item
    return sorted(best_by_url.values(), key=item_sort_key, reverse=True)


def story_title_key(title: str) -> tuple[str, ...]:
    tokens = tuple(
        re.findall(
            r"\w+(?:[+#]+|\.\d+)*", unicodedata.normalize("NFKC", title).casefold()
        )
    )
    # Short/generic headlines are poor evidence of a shared announcement.
    return tokens if len(tokens) >= 6 else ()


def group_stories(items: list[Item]) -> list[Item]:
    """Group only identical normalized detailed titles published within 24 hours."""
    groups: list[list[Item]] = []
    for item in items:
        key = story_title_key(item.title)
        match = next(
            (
                group
                for group in groups
                if key
                and story_title_key(group[0].title) == key
                and item.published is not None
                and all(
                    member.published is not None
                    and abs((item.published - member.published).total_seconds())
                    <= 24 * 3600
                    for member in group
                )
            ),
            None,
        )
        if match is None:
            groups.append([item])
        else:
            match.append(item)
    representatives = []
    for group in groups:
        preferred = sorted(
            group,
            key=lambda item: (
                item.category in {"frontier_lab", "research"},
                item_sort_key(item),
            ),
            reverse=True,
        )
        primary = preferred[0]
        primary.related_coverage = preferred[1:]
        representatives.append(primary)
    return sorted(
        representatives,
        key=lambda item: max(
            item_sort_key(member) for member in [item, *item.related_coverage]
        ),
        reverse=True,
    )


def stars(value: int) -> str:
    return "★" * value + "☆" * (5 - value)


def format_reading_time(minutes: int) -> str:
    return f"{minutes} min"


def markdown_escape(value: str) -> str:
    value = html.escape(normalize_space(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~>\-])", r"\\\1", value)


def markdown_link(title: str, url: str) -> str:
    destination = urllib.parse.quote(url, safe=":/?#@!$&'*+,;=%~._-")
    return f"[{markdown_escape(title)}]({destination})"


def render_report(
    items: list[Item],
    unavailable: list[tuple[str, str]],
    now: dt.datetime,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
) -> str:
    generated = now.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    selection = [
        (source, reason.removeprefix("Selection: "))
        for source, reason in unavailable
        if reason.startswith("Selection: ")
    ]
    unavailable = [
        (source, reason)
        for source, reason in unavailable
        if not reason.startswith("Selection: ")
    ]
    freshness = [
        (source, reason.removeprefix("Freshness: "))
        for source, reason in unavailable
        if reason.startswith("Freshness: ")
    ]
    unavailable = [
        (source, reason)
        for source, reason in unavailable
        if not reason.startswith("Freshness: ")
    ]
    start = (
        (now - dt.timedelta(hours=lookback_hours))
        .astimezone(dt.timezone.utc)
        .strftime("%Y-%m-%d %H:%M UTC")
    )
    coverage = [member for item in items for member in [item, *item.related_coverage]]
    source_count = len({member.source for member in coverage})
    publisher_count = len({member.publisher or member.source for member in coverage})
    article_label = "story" if len(items) == 1 else "stories"
    source_label = "source" if source_count == 1 else "sources"
    publisher_label = "publisher" if publisher_count == 1 else "publishers"
    lines = [
        "# Daily AI News",
        "",
        (
            f"{len(items)} {article_label} · {source_count} {source_label} · "
            f"{publisher_count} {publisher_label} · Generated {generated}"
        ),
        "",
        f"Coverage: last {lookback_hours} hours ({start} through {generated}, inclusive).",
        "",
        "## Articles",
        "",
    ]
    if items:
        for index, item in enumerate(items, start=1):
            indent = " " * (len(str(index)) + 2)
            source = markdown_escape(item.source)
            published = (
                item.published.astimezone(dt.timezone.utc).strftime("%Y-%m-%d")
                if item.published
                else "Date unknown"
            )
            lines.extend(
                [
                    f"{index}. **{markdown_link(item.title, item.url)}**  ",
                    (
                        f"{indent}{stars(item.stars)} · {source} · {published} · "
                        f"{reading_time_label(item)}"
                    ),
                    "",
                ]
            )
            if item.related_coverage:
                lines[-2] += "  "
                lines.insert(
                    len(lines) - 1,
                    f"{indent}Also published by: "
                    + "; ".join(
                        markdown_link(member.source, member.url)
                        for member in item.related_coverage
                    ),
                )
    else:
        lines.extend(
            ["No accessible AI-related articles found within the coverage window.", ""]
        )
    lines.extend(
        [
            "<details>",
            f"<summary>Freshness exclusions ({len(freshness)} source diagnostics)</summary>",
            "",
        ]
    )
    lines.extend(
        f"- **{markdown_escape(source)}**: {markdown_escape(reason)}"
        for source, reason in freshness
    )
    if not freshness:
        lines.append("- None.")
    lines.extend(["", "</details>", ""])
    lines.extend(
        ["<details>", f"<summary>Selection exclusions ({len(selection)})</summary>", ""]
    )
    lines.extend(
        f"- **{markdown_escape(source)}**: {markdown_escape(reason)}"
        for source, reason in selection
    )
    if not selection:
        lines.append("- None.")
    lines.extend(["", "</details>", ""])
    content_failures = [
        (source, reason.removeprefix("Content: "))
        for source, reason in unavailable
        if reason.startswith("Content: ")
    ]
    unavailable = [
        (source, reason)
        for source, reason in unavailable
        if not reason.startswith("Content: ")
    ]
    lines.extend(
        [
            "<details>",
            f"<summary>Article text unavailable ({len(content_failures)})</summary>",
            "",
        ]
    )
    lines.extend(
        f"- **{markdown_escape(source)}**: {markdown_escape(reason)}"
        for source, reason in content_failures
    )
    if not content_failures:
        lines.append("- None.")
    lines.extend(["", "</details>", ""])
    lines.extend(
        [
            "<details>",
            f"<summary>Skipped sources and links ({len(unavailable)})</summary>",
            "",
        ]
    )
    if unavailable:
        for source, reason in unavailable:
            lines.append(f"- **{markdown_escape(source)}**: {markdown_escape(reason)}")
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "</details>",
            "",
            "<details>",
            "<summary>About this report</summary>",
            "",
            "## Disclosure",
            "",
            textwrap.fill(
                "This report was generated automatically by auto-ai-news, a project built with "
                "AI assistance. auto-ai-news is an aggregator: original articles, titles, and "
                "linked content belong to their respective sources and authors.",
                width=100,
                break_on_hyphens=False,
            ),
            "",
            "Ratings range from 1 to 5 stars and indicate heuristic rank, not article quality.",
            (
                "Reading times estimate available text at 225 words per minute with a 100-word minimum. Feed content and extracted bodies may be incomplete; "
                "full articles may take longer. Selected stories with insufficient feed text receive bounded HTML body retrieval; estimates are labeled extracted body when successful, and failures remain unknown. Publication dates are shown in UTC."
            ),
            "",
            "Articles with missing/invalid or future dates are excluded. Older articles never backfill a short report. Date-only HTML listings use midnight UTC; boundary decisions are conservative. A story may recur across consecutive reports within the window.",
            "",
            "Selection uses a continuous score before mapping to stars. Source bonuses are 1.25 for priority 5 and 1 for priorities 3–4; qualifying frontier-lab research/model announcements add 0.75. Topic descriptions matched against headlines and feed summaries add up to 1 point, with word weights calculated from the fresh candidate pool. Known model families accept future version numbers. Matching is lexical, not content understanding; event-directory listings without a technical topic are excluded. Headline classification is heuristic; corporate posts receive no lab bonus. At most four story headlines per representative publisher are selected, with shared lab channels grouped together. Detailed identical titles within 24 hours are grouped, preferring research/lab representatives when available; other accessible source links appear as alternate coverage. This is a conservative title rule, not semantic story matching. No older articles fill excluded slots.",
            "",
            "## Source policy",
            "",
            textwrap.fill(
                "This report is generated from trusted public feeds. Links are deduplicated by "
                "canonical URL, filtered for AI relevance, and scored with a transparent heuristic "
                "based on source priority, recency, and title or summary relevance.",
                width=100,
                break_on_hyphens=False,
            ),
            "",
            (
                "Quiet-day editions titled ‘not much happened today’ from Latent Space and "
                "smol.ai are excluded by title policy, even when they contain recap content."
            ),
            "",
            "</details>",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--evaluation-output",
        type=Path,
        help="Optional metadata-only review snapshot including pre-ranking rejects.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help="Positive coverage window in hours (default: 72).",
    )
    parser.add_argument(
        "--no-article-bodies",
        action="store_true",
        help="Disable bounded body retrieval for selected stories.",
    )
    args = parser.parse_args(argv)
    if args.lookback_hours <= 0:
        parser.error("--lookback-hours must be positive")
    if (
        args.evaluation_output is not None
        and args.evaluation_output.resolve() == args.output.resolve()
    ):
        parser.error("--evaluation-output must differ from --output")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    now = dt.datetime.now(dt.timezone.utc)
    sources = load_sources(args.sources)
    evaluation = {} if args.evaluation_output is not None else None
    items, unavailable = collect_items(
        sources, now, args.lookback_hours, evaluation=evaluation
    )
    if args.evaluation_output is not None:
        args.evaluation_output.write_text(
            json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if not args.no_article_bodies:
        unavailable.extend(enrich_article_bodies(items))
    args.output.write_text(
        render_report(items, unavailable, now, args.lookback_hours), encoding="utf-8"
    )
    print(
        f"Wrote {args.output} with {len(items)} stories and {len(unavailable)} diagnostics."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
