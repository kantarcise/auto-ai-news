"""Replay source-priority changes against compact, frozen selection inputs."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from scripts import generate_report as report


def source_bonus(priority: int, parameters: dict) -> float:
    if priority >= 5:
        return parameters["priority_5"]
    return parameters["priority_3"] if priority >= 3 else 0.0


def replay(snapshot: dict, priorities: dict[str, int]) -> dict:
    now = dt.datetime.fromisoformat(snapshot["captured_at"])
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Capture clock must be timezone-aware")
    parameters = snapshot["scoring_parameters"]
    items = []
    for row in snapshot["items"]:
        published = dt.datetime.fromisoformat(row["published"])
        if published.tzinfo is None or published.utcoffset() is None:
            raise ValueError("Publication clock must be timezone-aware")
        age = (now - published).total_seconds() / 3600
        if age < 0 or age > snapshot["lookback_hours"]:
            raise ValueError("Frozen item outside coverage window")
        expected = parameters["base"] + source_bonus(row["source_priority"], parameters)
        if row["legacy_keyword_score"] >= parameters["keyword_threshold"]:
            expected += parameters["keyword_bonus"]
        if age <= parameters["recent_hours"]:
            expected += parameters["recent_bonus"]
        elif age > parameters["old_hours"]:
            expected -= parameters["old_penalty"]
        if row["story_kind"] in {"lab_research", "lab_announcement"}:
            expected += parameters["lab_bonus"]
        if not math.isclose(expected, row["current_score"], abs_tol=1e-9):
            raise ValueError("Frozen member score cannot be replayed")
        priority = priorities.get(row["source"], row["source_priority"])
        score = (
            expected
            - source_bonus(row["source_priority"], parameters)
            + source_bonus(priority, parameters)
        )
        items.append(
            report.Item(
                row["title"],
                row["url"],
                row["source"],
                priority,
                published=published,
                canonical_url=row["canonical_url"],
                category=row["category"],
                publisher=row["publisher"],
                story_kind=row["story_kind"],
                rank_score=score,
                stars=max(1, min(5, math.ceil(score))),
            )
        )
    groups = report.group_stories(report.dedupe_items(items))
    order = [item.url for item in groups]

    def check(url: str) -> tuple[bool, str]:
        if url not in snapshot["link_outcomes"]:
            raise ValueError(f"Unknown frozen access for {url}; no network fallback")
        outcome = snapshot["link_outcomes"][url]
        return outcome["accessible"], outcome["reason"]

    with patch.object(report, "check_url_accessible", side_effect=check):
        selected, _ = report.filter_accessible_items(
            groups, report.MAX_ITEMS, report.MAX_PER_PUBLISHER
        )
    return {
        "candidate_order": order,
        "selected": [
            {
                **report.evaluation_metadata(item),
                "score": item.rank_score,
                "stars": item.stars,
            }
            for item in selected
        ],
        "publisher_counts": dict(
            Counter(item.publisher or item.source for item in selected)
        ),
    }


def compare(snapshot: dict, priorities: dict[str, int]) -> dict:
    before = replay(snapshot, {})
    if before["candidate_order"] != snapshot["current_order"]:
        raise ValueError("Baseline grouping/order differs from frozen capture")
    if [row["url"] for row in before["selected"]] != snapshot["selected_urls"]:
        raise ValueError("Baseline selection differs from frozen capture")
    after = replay(snapshot, priorities)
    before_positions = {row["url"]: i for i, row in enumerate(before["selected"], 1)}
    after_positions = {row["url"]: i for i, row in enumerate(after["selected"], 1)}
    return {
        "captured_at": snapshot["captured_at"],
        "original_snapshot_sha256": snapshot["original_snapshot_sha256"],
        "generator_revision": snapshot.get("generator_revision"),
        "workflow_run_url": snapshot.get("workflow_run_url"),
        "priority_changes": {
            row["source"]: {
                "before": row["source_priority"],
                "after": priorities[row["source"]],
            }
            for row in snapshot["items"]
            if row["source"] in priorities
            and priorities[row["source"]] != row["source_priority"]
        },
        "scope": "Frozen eligibility and link outcomes; reruns deduplication, grouping, ranking, publisher caps and selection. No network requests or history changes.",
        "before": before,
        "after": after,
        "entered": sorted(after_positions.keys() - before_positions.keys()),
        "left": sorted(before_positions.keys() - after_positions.keys()),
        "position_changes": [
            {
                "url": row["url"],
                "title": row["title"],
                "source": row["source"],
                "before": before_positions.get(row["url"]),
                "after": after_positions[row["url"]],
            }
            for row in after["selected"]
            if before_positions.get(row["url"]) != after_positions[row["url"]]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--sources", type=Path, default=report.DEFAULT_SOURCES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() in {args.snapshot.resolve(), args.sources.resolve()}:
        parser.error("Output must differ from input paths")
    priorities = {
        source.name: source.priority for source in report.load_sources(args.sources)
    }
    result = compare(json.loads(args.snapshot.read_text(encoding="utf-8")), priorities)
    result["input_sha256"] = hashlib.sha256(args.snapshot.read_bytes()).hexdigest()
    result["sources_sha256"] = hashlib.sha256(args.sources.read_bytes()).hexdigest()
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
