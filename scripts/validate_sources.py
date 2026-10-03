"""Audit configured sources without publishing or changing selection policy."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.generate_report import (
    DEFAULT_SOURCES,
    canonicalize_url,
    check_url_accessible,
    fetch_url,
    is_ai_related,
    is_quiet_day_roundup,
    load_sources,
    parse_source,
)


def validate_sources(now: dt.datetime) -> dict:
    rows = []
    for source in load_sources(DEFAULT_SOURCES):
        if not source.enabled:
            continue
        row = {"source": source.name, "url": source.feed_url, "format": source.format}
        try:
            status, final_url, content = fetch_url(source.feed_url)
            items = parse_source(content, source)
            relevant = [
                item
                for item in items
                if is_ai_related(item) and not is_quiet_day_roundup(item)
            ]
            dated = [item for item in items if item.published]
            newest = max(dated, key=lambda item: item.published) if dated else None
            row.update(
                {
                    "status": status,
                    "final_url": final_url,
                    "entries": len(items),
                    "dated_entries": len(dated),
                    "relevant_candidates": len(relevant),
                    "newest_date": newest.published.isoformat() if newest else None,
                    "windows": {
                        str(hours): len(
                            {
                                canonicalize_url(item.url)
                                for item in relevant
                                if item.published
                                and 0
                                <= (now - item.published).total_seconds()
                                <= hours * 3600
                            }
                        )
                        for hours in (48, 72, 168)
                    },
                }
            )
            if newest:
                row["sample_url"] = urllib.parse.urljoin(final_url, newest.url)
                ok, reason = check_url_accessible(row["sample_url"])
                row["sample_accessible"] = ok
                row["sample_failure"] = reason
        except (ValueError, OSError, ET.ParseError) as exc:
            row["error"] = str(exc)
        rows.append(row)
    return {"checked_at": now.isoformat(), "sources": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = (
        json.dumps(validate_sources(dt.datetime.now(dt.timezone.utc)), indent=2) + "\n"
    )
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
