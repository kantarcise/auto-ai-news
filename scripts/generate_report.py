#!/usr/bin/env python3
"""Generate a daily AI news report from trusted public feeds."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "config" / "sources.json"
DEFAULT_OUTPUT = ROOT / "README.md"
USER_AGENT = "auto-ai-news/0.1 (+https://github.com/kantarcise/auto-ai-news)"
READING_WPM = 225
MAX_ITEMS = 30
DEFAULT_LOOKBACK_HOURS = 48
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
    read_minutes: int = 1
    stars: int = 1


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
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
        match = re.search(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b", text)
        title = normalize_space(" ".join(self.title_parts))
        if match and title:
            published = None
            for date_format in ("%B %d, %Y", "%b %d, %Y"):
                try:
                    published = dt.datetime.strptime(match[1], date_format).replace(
                        tzinfo=dt.timezone.utc
                    )
                    break
                except ValueError:
                    continue
            if published:
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


def parse_source(content: str, source: Source) -> list[Item]:
    if source.format == "feed":
        return parse_feed(content, source)
    if source.format != "dated_html":
        raise ValueError(f"Unsupported source format: {source.format}")
    parser = DatedNewsParser(source)
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


def parse_rss_item(entry: ET.Element, source: Source) -> Item:
    title = child_text(entry, "title") or "Untitled"
    link = child_text(entry, "link", "guid")
    summary = child_text(entry, "description", "summary")
    published = parse_datetime(child_text(entry, "pubDate", "published", "updated"))
    return Item(title, link, source.name, source.priority, summary, published)


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
    summary = child_text(entry, f"{ns}summary", f"{ns}content")
    published = parse_datetime(child_text(entry, f"{ns}published", f"{ns}updated"))
    return Item(title, link, source.name, source.priority, summary, published)


def ai_relevance_score(item: Item) -> int:
    text = f"{item.title} {item.summary}".lower()
    score = 0
    for keyword in AI_KEYWORDS:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, text):
            score += 2 if " " in keyword else 1
    return score


def is_ai_related(item: Item) -> bool:
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


def estimate_reading_time(item: Item, article_html: str | None = None) -> int:
    text = (
        extract_text_from_html(article_html)
        if article_html
        else f"{item.title} {item.summary}"
    )
    words = re.findall(r"\b[\w'-]+\b", text)
    item.word_count = len(words)
    item.read_minutes = max(1, round(item.word_count / READING_WPM))
    return item.read_minutes


def score_item(item: Item, now: dt.datetime) -> int:
    score = 1
    if item.source_priority >= 5:
        score += 2
    elif item.source_priority >= 3:
        score += 1
    relevance = ai_relevance_score(item)
    if relevance >= 3:
        score += 1
    if item.published:
        age_hours = max(0.0, (now - item.published).total_seconds() / 3600)
        if age_hours <= 24:
            score += 1
        elif age_hours > 7 * 24:
            score -= 1
    item.stars = max(1, min(5, score))
    return item.stars


def item_sort_key(item: Item) -> tuple[int, dt.datetime]:
    published = item.published or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return item.stars, published


def freshness_reason(item: Item, now: dt.datetime, lookback_hours: int) -> str:
    if item.published is None:
        return "missing or invalid publication date"
    age = (now - item.published).total_seconds()
    if age < 0:
        return "future publication date"
    if age > lookback_hours * 3600:
        return "older than coverage window"
    return ""


def collect_items(
    sources: list[Source],
    now: dt.datetime,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
) -> tuple[list[Item], list[tuple[str, str]]]:
    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be positive")
    items: list[Item] = []
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
            reason = freshness_reason(item, now, lookback_hours)
            if reason:
                freshness_counts[reason] = freshness_counts.get(reason, 0) + 1
                continue
            fresh_count += 1
            if not item.url:
                unavailable.append((source.name, "Feed item missing link."))
                continue
            item.url = urllib.parse.urljoin(final_url, item.url)
            item.canonical_url = canonicalize_url(item.url)
            if is_quiet_day_roundup(item):
                unavailable.append(
                    (
                        f"{item.source}: {item.title}",
                        "Quiet-day roundup excluded by title policy.",
                    )
                )
                continue
            if is_ai_related(item):
                estimate_reading_time(item)
                score_item(item, now)
                items.append(item)
        if not fresh_count:
            unavailable.append(
                (source.name, "Freshness: no dated entries within the coverage window.")
            )
        for reason, count in freshness_counts.items():
            unavailable.append(
                (source.name, f"Freshness: {count} entries excluded: {reason}.")
            )
    candidates = dedupe_items(items)
    accessible, link_failures = filter_accessible_items(candidates, MAX_ITEMS)
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
    items: list[Item], limit: int
) -> tuple[list[Item], list[tuple[str, str]]]:
    accessible: list[Item] = []
    failures: list[tuple[str, str]] = []
    for item in items:
        ok, reason = check_url_accessible(item.url)
        if ok:
            accessible.append(item)
            if len(accessible) == limit:
                break
        else:
            failures.append((f"{item.source}: [{item.title}]({item.url})", reason))
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
    source_count = len({item.source for item in items})
    article_label = "article" if len(items) == 1 else "articles"
    source_label = "source" if source_count == 1 else "sources"
    lines = [
        "# Daily AI News",
        "",
        (
            f"{len(items)} {article_label} · {source_count} {source_label} · "
            f"Generated {generated}"
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
                        f"~{format_reading_time(item.read_minutes)} (feed text)"
                    ),
                    "",
                ]
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
                "Reading times estimate the available feed text at 225 words per minute; "
                "full articles may take longer. Publication dates are shown in UTC."
            ),
            "",
            "Articles with missing/invalid or future dates are excluded. Older articles never backfill a short report. Date-only HTML listings use midnight UTC; boundary decisions are conservative. A story may recur across consecutive reports within the window.",
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
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help="Positive coverage window in hours (default: 48).",
    )
    args = parser.parse_args(argv)
    if args.lookback_hours <= 0:
        parser.error("--lookback-hours must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    now = dt.datetime.now(dt.timezone.utc)
    sources = load_sources(args.sources)
    items, unavailable = collect_items(sources, now, args.lookback_hours)
    args.output.write_text(
        render_report(items, unavailable, now, args.lookback_hours), encoding="utf-8"
    )
    print(
        f"Wrote {args.output} with {len(items)} links and {len(unavailable)} diagnostics."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
