"""Read publication receipts from release notes; never publish or edit releases."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

MARKER = "auto-ai-news-publication-v1:"
RECEIPT = re.compile(r"<!-- " + MARKER + r" (.*?) -->", re.DOTALL)


def validate_receipt(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Unsupported publication receipt")
    date = value.get("report_date")
    if not isinstance(date, str) or dt.date.fromisoformat(date).isoformat() != date:
        raise ValueError("Invalid publication date")
    urls = value.get("urls")
    if not isinstance(urls, list) or any(
        not isinstance(url, str)
        or urlsplit(url).scheme not in {"http", "https"}
        or not urlsplit(url).netloc
        for url in urls
    ):
        raise ValueError("Invalid publication URLs")
    return value


def receipt_comment(date: str, urls: list[str]) -> str:
    receipt = validate_receipt(
        {"schema_version": 1, "report_date": date, "urls": sorted(set(urls))}
    )
    # Prevent an external URL from terminating the HTML comment.
    payload = (
        json.dumps(receipt, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return f"<!-- {MARKER} {payload} -->\n"


def history_from_releases(pages: list, today: str) -> dict:
    dt.date.fromisoformat(today)
    published: dict[str, list[str]] = {}
    legacy_count = 0
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("Expected paginated release arrays")
    for page in pages:
        for release in page:
            tag = release.get("tag_name", "")
            if not re.fullmatch(r"daily-\d{4}-\d{2}-\d{2}", tag):
                continue
            date = tag.removeprefix("daily-")
            dt.date.fromisoformat(date)
            if release.get("draft") or release.get("prerelease") or date > today:
                continue
            body = release.get("body") or ""
            matches = RECEIPT.findall(body)
            if not matches:
                if MARKER in body:
                    raise ValueError(f"Malformed publication receipt in {tag}")
                legacy_count += 1
                continue
            if len(matches) != 1:
                raise ValueError(f"Multiple publication receipts in {tag}")
            receipt = validate_receipt(json.loads(matches[0]))
            if receipt["report_date"] != date:
                raise ValueError(f"Publication date does not match {tag}")
            published[date] = sorted(set(published.get(date, []) + receipt["urls"]))
    return {
        "schema_version": 1,
        "report_date": today,
        "published": published,
        "legacy_release_count": legacy_count,
    }


def load_history(path: Path, today: str) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("report_date") != today
    ):
        raise ValueError("History must be captured for the current UTC report date")
    if not isinstance(value.get("published"), dict):
        raise TypeError("Invalid publication history")
    count = value.get("legacy_release_count", 0)
    if not isinstance(count, int) or count < 0:
        raise ValueError("Invalid legacy release count")
    for date, urls in value["published"].items():
        validate_receipt({"schema_version": 1, "report_date": date, "urls": urls})
        if date > today:
            raise ValueError("Future publication history")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = subprocess.run(
        [
            "gh",
            "api",
            "repos/{owner}/{repo}/releases?per_page=100",
            "--paginate",
            "--slurp",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    history = history_from_releases(
        json.loads(result.stdout), dt.datetime.now(dt.timezone.utc).date().isoformat()
    )
    args.output.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
