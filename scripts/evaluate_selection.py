"""Replay saved ranking/selection comparisons without network requests."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from scripts.generate_report import (
    MAX_ITEMS,
    MAX_PER_PUBLISHER,
    Item,
    filter_accessible_items,
)


def replay(snapshot: dict, policy: str) -> dict:
    rows = snapshot["policies"][policy]["candidates"]
    outcomes = snapshot["link_outcomes"]
    items = [
        Item(
            row["title"],
            row["url"],
            row["source"],
            0,
            published=dt.datetime.fromisoformat(row["published"]),
            publisher=row["publisher"],
            category=row["category"],
            stars=row["stars"],
            rank_score=row["rank_score"],
            story_kind=row["story_kind"],
        )
        for row in rows
    ]

    def check(url: str) -> tuple[bool, str]:
        if url not in outcomes:
            raise ValueError(
                f"No frozen link outcome for {url}; no network fallback permitted."
            )
        row = outcomes[url]
        return row["accessible"], row["reason"]

    with patch("scripts.generate_report.check_url_accessible", side_effect=check):
        selected, _ = filter_accessible_items(
            items, MAX_ITEMS, None if policy == "baseline" else MAX_PER_PUBLISHER
        )
    expected = [row["url"] for row in snapshot["policies"][policy]["selected"]]
    if [item.url for item in selected] != expected:
        raise ValueError(f"{policy} selection no longer matches the saved result.")
    counts = Counter(item.publisher for item in selected)
    return {
        "articles": len(selected),
        "publishers": len(counts),
        "max_from_one_publisher": max(counts.values(), default=0),
        "publisher_counts": dict(counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    print(
        json.dumps(
            {name: replay(snapshot, name) for name in ("baseline", "frontier")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
