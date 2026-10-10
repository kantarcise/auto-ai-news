"""Provisional article labels from bounded text cues, never editorial grades."""

from __future__ import annotations

import re
from html.parser import HTMLParser

VERSION = 1
MAX_RAW_CHARS = 24000
MAX_CONTENT_CHARS = 12000
MAX_SUMMARY_CHARS = 4000
MAX_TITLE_CHARS = 500
MIN_SUBSTANTIAL_WORDS = 120

LABEL_NAMES = {
    "technical_walkthrough": "Technical walkthrough",
    "research_evaluation": "Research / evaluation",
    "model_tool_release": "Model / tool release",
    "practical_experience": "Practical experience",
    "promotion_testimonial": "Promotion / testimonial",
    "opinion_discussion": "Opinion / discussion",
    "event_announcement": "Event / announcement",
}
LABEL_PATTERNS = {
    "technical_walkthrough": r"\b(?:walkthrough|step.by.step|implementation|troubleshoot\w*|debugg\w*|how (?:to|we) (?:build|implement|deploy|configure|debug|integrate))\b",
    "research_evaluation": r"\b(?:ablations?|benchmarks?|benchmarking|evaluation|experiments?|methodology|we evaluate|our findings)\b",
    "model_tool_release": r"\b(?:introducing|now available|release notes|we (?:release|announce)|new (?:model|tool|release))\b",
    "practical_experience": r"\b(?:lessons (?:learned|from)|what we learned|our experience|in production|we (?:built|deployed|migrated|operated))\b",
    "promotion_testimonial": r"\b(?:sponsored|testimonials?|customer stor(?:y|ies)|case stud(?:y|ies)|our customers|contact (?:our )?sales|(?:book|request) a demo|trusted by|partnership)\b",
    "opinion_discussion": r"\b(?:i (?:think|believe|argue)|we (?:think|believe|argue)|in my opinion|discussion|opinion|essay)\b",
    "event_announcement": r"\b(?:conference|webinar|meetup|register now|join us|call for papers)\b",
}
TECHNICAL_PATTERNS = {
    "implementation": r"\b(?:implementation|routing|scheduler|algorithm|cache indexing|programmatic cache movement|troubleshoot\w*|debugg\w*)\b",
    "configuration": r"\b(?:configuration|parameters?|command.line|api calls?|kv cach(?:e|es)|environment variables?)\b",
    "measurement": r"\b(?:ablations?|benchmarks?|benchmarking|profiling|p\d{2} latency|\d+(?:\.\d+)?\s*(?:ms|milliseconds|tokens/s|requests/s|gb/s))\b",
    "tradeoffs": r"\b(?:trade.offs?|limitations?|failure modes?|bottlenecks?|maintenance|dependencies)\b",
}
REASONS = {
    "implementation": "Implementation or troubleshooting details",
    "configuration": "Configuration, API or cache details",
    "measurement": "Evaluation or measurement details",
    "tradeoffs": "Trade-offs, limitations or maintenance details",
    "code": "Structured code example",
}
NEGATION = re.compile(
    r"\b(?:no|without|not|lacks?|lacking)\s+(?:(?:any|a|an|technical|detailed|actual)\s+){0,2}$",
    re.IGNORECASE,
)


class TextParser(HTMLParser):
    """Ignore executable/navigation text; record only nonempty code examples."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.text_length = 0
        self.parts = []
        self.stack = []
        self.code = False

    def handle_starttag(self, tag, attrs):
        if tag not in {
            "br",
            "hr",
            "img",
            "input",
            "meta",
            "link",
            "source",
            "wbr",
            "area",
            "base",
            "embed",
            "param",
            "track",
            "col",
        }:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]

    def handle_data(self, data):
        if any(
            tag in {"script", "style", "nav", "footer", "aside"} for tag in self.stack
        ):
            return
        self.parts.append(data)
        self.text_length += len(data) + 1
        if (
            self.text_length <= self.limit
            and any(tag in {"pre", "code"} for tag in self.stack)
            and re.search(
                r"[=(){};]|\b(?:import|def|pip|python|docker|curl|torchrun)\b", data
            )
        ):
            self.code = True


def text_evidence(value: str, html: bool, limit: int) -> tuple[str, bool, bool]:
    bounded = value[:MAX_RAW_CHARS]
    code = False
    if html:
        parser = TextParser(limit)
        parser.feed(bounded)
        bounded = " ".join(parser.parts)
        code = parser.code
    text = re.sub(r"\s+", " ", bounded).strip()
    return text[:limit], code, len(value) > MAX_RAW_CHARS or len(text) > limit


def matches(pattern: str, text: str) -> bool:
    return any(
        not NEGATION.search(text[max(0, match.start() - 60) : match.start()])
        for match in re.finditer(pattern, text, re.IGNORECASE)
    )


def label_article(
    title: str,
    summary: str = "",
    *,
    content: str = "",
    content_format: str = "text",
    content_provenance: str = "missing",
) -> dict:
    title_text = title[:MAX_TITLE_CHARS]
    summary_text, _, summary_truncated = text_evidence(summary, True, MAX_SUMMARY_CHARS)
    content_text, code, content_truncated = text_evidence(
        content, content_format == "html", MAX_CONTENT_CHARS
    )
    if content_text and content_provenance in {
        "rss_content",
        "atom_content",
        "article_body",
    }:
        evidence = (
            "article_body" if content_provenance == "article_body" else "feed_content"
        )
        text = content_text
        truncated = content_truncated
    else:
        evidence = (
            "feed_summary"
            if summary_text
            else ("title_only" if title_text else "missing")
        )
        text = summary_text
        code = False
        truncated = summary_truncated
    combined = title_text + " " + text
    labels = [
        name for name, pattern in LABEL_PATTERNS.items() if matches(pattern, combined)
    ]
    # Depth comes from available content, never publisher identity or title keywords.
    signals = [
        name for name, pattern in TECHNICAL_PATTERNS.items() if matches(pattern, text)
    ]
    if code:
        signals.append("code")
    if len(signals) >= 2 and "technical_walkthrough" not in labels:
        labels.insert(0, "technical_walkthrough")
    depth = "uncertain"
    if len(signals) >= 2:
        depth = "some"
        if (
            evidence in {"feed_content", "article_body"}
            and len(signals) >= 3
            and len(text.split()) >= MIN_SUBSTANTIAL_WORDS
            and ("code" in signals or "implementation" in signals)
        ):
            depth = "substantial"
    return {
        "version": VERSION,
        "method": "bounded_text_rules",
        "provisional": True,
        "labels": labels,
        "technical_depth": depth,
        "evidence": evidence,
        "depth_scope": "available_text_only",
        "analyzed_characters": len(text),
        "truncated": truncated or len(title) > MAX_TITLE_CHARS,
        "signals": signals,
        "reasons": [REASONS[name] for name in signals]
        or ["Insufficient positive evidence to estimate technical depth"],
    }
