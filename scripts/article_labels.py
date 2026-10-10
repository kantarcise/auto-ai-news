"""Provisional article labels from bounded text cues, never editorial grades."""

from __future__ import annotations

import re
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

VERSION = 2
MAX_RAW_CHARS = 24000
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
# Stable rule IDs and fixed descriptions make labels auditable without quotations.
LABEL_RULES = {
    "technical_walkthrough": {
        "implementation-guide": (
            "Implementation or troubleshooting language",
            r"\b(?:walkthrough|step.by.step|implementation|troubleshoot\w*|debugg\w*|how (?:to|we) (?:build|implement|deploy|configure|debug|integrate))\b",
        ),
    },
    "research_evaluation": {
        "evaluation-language": (
            "Evaluation, experiment or methodology language",
            r"\b(?:ablations?|benchmarks?|benchmarking|evaluation|experiments?|methodology|we evaluate|our findings)\b",
        ),
        "comparative-testing": (
            "Reported comparative testing",
            r"\b(?:we (?:tested|compared)|test(?:ed|ing) \d+ (?:frontier )?models|measured improvements?|improves (?:performance )?by \d+)\b",
        ),
    },
    "model_tool_release": {
        "release-announcement": (
            "Explicit model or tool release language",
            r"\b(?:introducing|now available|release notes|we (?:release|announce)|new (?:model|tool|release))\b",
        ),
    },
    "practical_experience": {
        "deployment-experience": (
            "Lessons or reported deployment experience",
            r"\b(?:lessons (?:learned|from)|what we learned|our experience|in production|we (?:built|deployed|migrated|operated))\b",
        ),
    },
    "promotion_testimonial": {
        "customer-promotion": (
            "Customer story, sponsorship or partnership language",
            r"\b(?:sponsored|testimonials?|customer stor(?:y|ies)|case stud(?:y|ies)|our customers|trusted by|partnership)\b",
        ),
        "sales-demo-invitation": (
            "Sales or demo invitation",
            r"\b(?:contact (?:our )?sales|(?:book|request) a demo)\b",
        ),
    },
    "opinion_discussion": {
        "opinion-framing": (
            "Explicit opinion or discussion framing",
            r"\b(?:i (?:think|believe|argue)|we (?:think|believe|argue)|in my opinion|discussion|opinion|essay)\b",
        ),
    },
    "event_announcement": {
        "event-invitation": (
            "Event or registration language",
            r"\b(?:conference|webinar|meetup|register now|join us|call for papers)\b",
        ),
    },
}
TECHNICAL_PATTERNS = {
    "implementation": r"\b(?:implementation|routing|scheduler|algorithm|cache indexing|programmatic cache movement|troubleshoot\w*|debugg\w*)\b",
    "configuration": r"\b(?:configuration|parameters?|command.line|api calls?|kv cach(?:e|es)|environment variables?)\b",
    "measurement": r"\b(?:ablations?|benchmarks?|benchmarking|profiling|we (?:tested|compared)|test(?:ed|ing) \d+ (?:frontier )?models|improves (?:performance )?by \d+|p\d{2} latency|\d+(?:\.\d+)?\s*(?:ms|milliseconds|tokens/s|requests/s|gb/s))\b",
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
    """Use the body extractor's visibility rules, without requiring an article region."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        blocked = bool(self.stack and self.stack[-1][1]) or blocked_element(
            tag, dict(attrs)
        )
        if tag not in VOID_TAGS:
            self.stack.append((tag, blocked))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            return
        self.parts.append((data, any(tag in {"pre", "code"} for tag, _ in self.stack)))


def text_evidence(value: str, html: bool, limit: int) -> tuple[str, bool, bool]:
    bounded = value[:MAX_RAW_CHARS]
    if html:
        parser = TextParser()
        parser.feed(bounded)
        parts = parser.parts
    else:
        parts = [(bounded, False)]
    text, code, truncated = analyze_parts(parts, limit)
    return text, code, truncated or len(value) > MAX_RAW_CHARS


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
    content_structure: dict | None = None,
) -> dict:
    fields = {}
    for name, value, html, limit in (
        ("title", title, True, MAX_TITLE_CHARS),
        ("summary", summary, True, MAX_SUMMARY_CHARS),
        ("content", content, content_format == "html", MAX_CONTENT_CHARS),
    ):
        if name == "content" and content_provenance not in {
            "rss_content",
            "atom_content",
            "article_body",
        }:
            continue
        text, code, truncated = text_evidence(value, html, limit)
        if (
            name == "content"
            and content_provenance == "article_body"
            and content_structure
        ):
            # Only metadata from the same normalized extractor window is accepted.
            code |= (
                content_structure.get("analyzed_characters") == len(text)
                and content_structure.get("limit") == MAX_CONTENT_CHARS
                and content_structure.get("code") is True
            )
        if text:
            fields[name] = {"text": text, "code": code, "truncated": truncated}
    label_evidence = []
    signal_evidence = []
    for name, data in fields.items():
        for label, rules in LABEL_RULES.items():
            for rule, (description, pattern) in rules.items():
                if matches(pattern, data["text"]):
                    label_evidence.append(
                        {
                            "label": label,
                            "rule_id": rule,
                            "field": name,
                            "description": description,
                        }
                    )
        if name == "title":
            continue
        signals = [
            signal
            for signal, pattern in TECHNICAL_PATTERNS.items()
            if matches(pattern, data["text"])
        ]
        if data["code"]:
            signals.append("code")
        signal_evidence.extend(
            {"signal": signal, "field": name, "description": REASONS[signal]}
            for signal in signals
        )
        if len(signals) >= 2:
            label_evidence.append(
                {
                    "label": "technical_walkthrough",
                    "rule_id": "multiple-technical-signals",
                    "field": name,
                    "description": "Several distinct technical signal categories",
                }
            )
    labels = [
        label
        for label in LABEL_NAMES
        if any(row["label"] == label for row in label_evidence)
    ]
    signals = [
        signal
        for signal in REASONS
        if any(row["signal"] == signal for row in signal_evidence)
    ]
    content_signals = {
        row["signal"] for row in signal_evidence if row["field"] == "content"
    }
    # Aggregate depth is experimental. Stronger claims require content evidence alone.
    depth = "some" if len(signals) >= 2 else "uncertain"
    if (
        len(content_signals) >= 3
        and content_signals & {"code", "implementation"}
        and len(fields["content"]["text"].split()) >= MIN_SUBSTANTIAL_WORDS
    ):
        depth = "substantial"
    evidence = (
        ("article_body" if content_provenance == "article_body" else "feed_content")
        if "content" in fields
        else (
            "feed_summary"
            if "summary" in fields
            else ("title_only" if "title" in fields else "missing")
        )
    )
    return {
        "version": VERSION,
        "method": "bounded_text_rules",
        "provisional": True,
        "labels": labels,
        "label_evidence": label_evidence,
        "technical_depth": depth,
        "depth_experimental": True,
        "evidence": evidence,
        "depth_scope": "available_text_only",
        "fields": {
            name: {
                "analyzed_characters": len(data["text"]),
                "truncated": data["truncated"],
                "code": data["code"],
            }
            for name, data in fields.items()
        },
        "analyzed_characters": sum(
            len(data["text"]) for name, data in fields.items() if name != "title"
        ),
        "truncated": any(data["truncated"] for data in fields.values()),
        "signals": signals,
        "signal_evidence": signal_evidence,
        "reasons": [REASONS[name] for name in signals]
        or ["Insufficient positive evidence to estimate technical depth"],
    }
