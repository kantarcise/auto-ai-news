"""Compare adaptive admission with two frozen title checks, without network I/O."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.compare_relevance import compare
from scripts.editorial_relevance import assess, load_config
from scripts.generate_report import Item, is_ai_related


def compare_editorial(
    snapshot: dict, feedback: dict, config: dict | None = None
) -> dict:
    frozen = compare(
        snapshot, feedback
    )  # Reuse dates, identity and provenance validation.
    config = load_config() if config is None else config
    decisions = frozen["decisions"]
    # These captures deliberately contain no summaries; test title evidence only.
    for row, assessment in zip(decisions, assess(decisions, config)):
        item = Item(row["title"], row["url"], row["source"], 0)
        item.editorial_relevance = assessment
        row["profile_admitted"] = (
            is_ai_related(item)
            if not next(
                entry["rejection_reason"] == "quiet-day title policy"
                for entry in snapshot["collection"]
                if entry["url"] == row["url"]
            )
            else False
        )
        row["topic"] = assessment.topic
        row["similarity"] = round(assessment.similarity, 6)
        row["matched_terms"] = list(assessment.terms)
        row["rank_bonus"] = round(assessment.rank_bonus, 6)
        row["event_listing"] = assessment.event_listing
    policies = {}
    for name in ("current", "alternative", "profile"):
        admitted = [row for row in decisions if row[f"{name}_admitted"]]
        policies[name] = {
            "admitted": len(admitted),
            "owner_wanted_admitted": sum(
                row["owner_include"] == "yes" for row in admitted
            ),
            "owner_unwanted_admitted": sum(
                row["owner_include"] == "no" for row in admitted
            ),
            "unreviewed_admitted": sum(
                row["owner_include"] is None for row in admitted
            ),
        }
    return {
        "schema_version": 1,
        "captured_at": snapshot["captured_at"],
        "assessment_at": snapshot.get("assessment_at", snapshot["captured_at"]),
        "profiles": config,
        "policies": policies,
        "decisions": decisions,
        "limitations": [
            "Development set: profiles and threshold were chosen after reading owner feedback.",
            "Targeted reviews, not a random sample or held-out evaluation.",
            "Title-only replay: frozen summaries, source priorities and full ranking inputs are unavailable.",
            "Bonus deltas are shown; final selection and quality improvements are not measured.",
            "No new link checks: preserve frozen outcomes and original actual selections.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("feedback", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.snapshot.resolve(), args.feedback.resolve()}:
        parser.error("Output must not overwrite either input")
    snapshot_bytes = args.snapshot.read_bytes()
    feedback_bytes = args.feedback.read_bytes()
    result = compare_editorial(json.loads(snapshot_bytes), json.loads(feedback_bytes))
    result["input_sha256"] = {
        "snapshot": hashlib.sha256(snapshot_bytes).hexdigest(),
        "feedback": hashlib.sha256(feedback_bytes).hexdigest(),
    }
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
