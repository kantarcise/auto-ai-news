"""Preview source-backed Clairic details for selected articles in a local report."""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from scripts.article_evidence import EvidenceCollector
from scripts.cloudflare_assessment import NoRedirect
from scripts.evaluate_clairic import MODEL
from scripts.generate_report import (
    USER_AGENT,
    Item,
    canonicalize_url,
    markdown_escape,
    markdown_link,
)
from scripts.publication_history import RECEIPT, validate_receipt

FIELDS = {
    "model": "Copy only the exact name of the main AI model discussed. Omit libraries and frameworks.",
    "hardware": "Copy only the exact name of hardware actually used in the reported work.",
    "detail": "Copy one short verbatim excerpt with a useful numeric engineering specification or "
    "benchmark. Include its unit and what was measured, including a comparison baseline when "
    "needed. Omit dates, versions, dollar amounts and unsupported or ambiguous claims.",
}
MAX_ARTICLES = 5
MAX_STATE_BYTES = 8000
MAX_DETAIL_CHARS = 160
TOKEN_STOP = 30_000


def select_articles(report, snapshot, urls):
    receipts = RECEIPT.findall(report)
    if len(receipts) != 1:
        raise ValueError("expected one publication receipt in the report")
    receipt = validate_receipt(json.loads(receipts[0]))
    selected = set(map(canonicalize_url, receipt["urls"]))
    requested = [canonicalize_url(url) for url in urls]
    if not 1 <= len(requested) <= MAX_ARTICLES or len(set(requested)) != len(requested):
        raise ValueError("choose one to five distinct report articles")
    if any(not url or url not in selected for url in requested):
        raise ValueError("each article must appear in the report's new-article receipt")
    by_url = {}
    for row in snapshot["collection"]:
        candidate = row.get("comparison_candidate")
        if candidate and ("article_evidence" in row or "evidence_input" in row):
            by_url.setdefault(candidate["canonical_url"], row)
    return receipt["report_date"], [(url, by_url.get(url)) for url in requested]


def article_evidence(row, collector):
    if "article_evidence" in row:
        return row["article_evidence"]
    item = Item(row["title"], row["url"], row["source"], 0, **row["evidence_input"])
    item.canonical_url = row["comparison_candidate"]["canonical_url"]
    return collector.capture(item)


def source_state(evidence):
    return evidence["text"].encode("utf-8")[:MAX_STATE_BYTES].decode("utf-8", "ignore")


def read_response(body, state):
    if not isinstance(body, dict) or body.get("success") is not True:
        raise ValueError("invalid provider envelope")
    result = body["result"]
    if not isinstance(result, dict) or not isinstance(result.get("usage"), dict):
        raise TypeError("invalid provider result")
    usage = result["usage"]
    if any(
        type(usage.get(k)) is not int or usage[k] < 1
        for k in ("input_tokens", "passes")
    ):
        raise ValueError("invalid usage counters")
    answers = result.get("answers")
    if not isinstance(answers, dict):
        return usage, {}, "invalid_answers"
    accepted = {}
    for name in FIELDS:
        field = answers.get(name)
        if (
            not isinstance(field, dict)
            or field.get("valid") is False
            or field.get("complete") is False
        ):
            continue
        value = field.get("value")
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > MAX_DETAIL_CHARS
        ):
            continue
        if name == "detail" and (not re.search(r"\d", value) or len(value.split()) < 3):
            continue
        # A source slice is independently verified. Fall back to a unique
        # literal match if the provider omits offsets or counts them differently.
        span = field.get("span")
        if (
            isinstance(span, list)
            and len(span) == 2
            and all(type(offset) is int for offset in span)
            and 0 <= span[0] < span[1] <= len(state)
            and state[span[0] : span[1]] == value
        ):
            start, end = span
        else:
            start = state.find(value)
            if start < 0 or state.find(value, start + 1) >= 0:
                continue
            end = start + len(value)
        accepted[name] = (value, state[max(0, start - 55) : end + 55])
    return usage, accepted, "partial_response" if result.get("truncated") else None


def request_clairic(opener, account, token, state):
    payload = {
        "model": "clairic",
        "state": state,
        "fields": {
            name: {"type": "text", "instructions": instruction}
            for name, instruction in FIELDS.items()
        },
    }
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with opener.open(request, timeout=20) as response:
        data = response.read(64_001)
    if len(data) > 64_000:
        raise ValueError("provider response exceeds byte limit")
    return read_response(json.loads(data), state)


def preview(date, articles, extract, collect):
    lines = [
        f"# Clairic preview for {date}",
        "",
        "Source wording for editorial review.",
        "",
    ]
    tokens = passes = attempts = unknown = 0
    for url, row in articles:
        label = row["title"] if row else url
        lines.extend([f"## {markdown_link(label, url)}", ""])
        if row is None:
            lines.extend(["Snapshot has no evidence for this article.", ""])
            continue
        if tokens >= TOKEN_STOP or unknown:
            lines.extend(["Skipped after reaching the usage stop condition.", ""])
            continue
        evidence = collect(row)
        state = source_state(evidence)
        provenance = markdown_escape(evidence["provenance"])
        if not state.strip() or evidence["provenance"] == "title_only":
            lines.extend([f"No usable article text ({provenance}).", ""])
            continue
        started = time.monotonic()
        attempts += 1
        try:
            usage, fields, warning = extract(state)
        except urllib.error.HTTPError as exc:
            unknown += 1
            lines.extend([f"Clairic request failed (HTTP {exc.code}).", ""])
            continue
        except (ValueError, KeyError, TypeError, OSError):
            unknown += 1
            lines.extend(["Clairic request did not return usable usage data.", ""])
            continue
        tokens += usage["input_tokens"]
        passes += usage["passes"]
        for name, (value, context) in fields.items():
            lines.extend(
                [
                    f"- **{name.title()}** · {markdown_escape(value)}",
                    f"  - Source context · {markdown_escape(context)}",
                ]
            )
        if not fields:
            lines.append("No source-backed fields to display.")
        if warning:
            lines.append(f"Provider warning · {markdown_escape(warning)}")
        cropped = evidence.get("truncated") or state != evidence["text"]
        lines.extend(
            [
                "",
                (
                    f"Evidence · {provenance}{' (excerpt)' if cropped else ''} · "
                    f"{usage['input_tokens']:,} input tokens · {usage['passes']} passes · "
                    f"{time.monotonic() - started:.2f} s"
                ),
                "",
            ]
        )
    lines.append(
        f"Usage · {attempts} requests · {tokens:,} reported input tokens · "
        f"{passes} reported passes · {unknown} requests with unknown usage"
    )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--article", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not re.fullmatch(r"[!-~]+", token):
        parser.error("set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")
    try:
        date, articles = select_articles(
            args.report.read_text(encoding="utf-8"),
            json.loads(args.snapshot.read_text(encoding="utf-8")),
            args.article,
        )
        opener = urllib.request.build_opener(NoRedirect())
        collector = EvidenceCollector(USER_AGENT)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(
                preview(
                    date,
                    articles,
                    lambda state: request_clairic(opener, account, token, state),
                    lambda row: article_evidence(row, collector),
                )
            )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Preview stopped ({type(exc).__name__}).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
