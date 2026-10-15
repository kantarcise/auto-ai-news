"""Final bounded admission comparison for issue #12; never change production rules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.compare_editorial import compare_editorial
from scripts.generate_report import AI_KEYWORDS, Item, ai_relevance_score


def compare_final(snapshot: dict, feedback: dict) -> dict:
    # Reuse frozen clock, freshness, identity, label and provenance validation.
    baseline = compare_editorial(snapshot, feedback)
    original = {row["url"]: row for row in snapshot["collection"]}
    decisions = []
    for row in baseline["decisions"]:
        current = row["profile_admitted"]
        gated = (
            row["event_listing"]
            or original[row["url"]]["rejection_reason"] == "quiet-day title policy"
        )
        item = Item(row["title"], row["url"], row["source"], 0)
        # Relax only keyword context. Retain current topic/family matches and
        # source bypasses; never override event or quiet-day exclusions.
        broader = current or (not gated and ai_relevance_score(item) > 0)
        decisions.append(
            {
                "title": row["title"],
                "url": row["url"],
                "source": row["source"],
                "current_admitted": current,
                "broader_admitted": broader,
                "owner_include": row["owner_include"],
                "owner_importance": row["owner_importance"],
            }
        )
    policies = {}
    for policy in ("current", "broader"):
        admitted = [row for row in decisions if row[f"{policy}_admitted"]]
        policies[policy] = {
            "admitted": len(admitted),
            "wanted_admitted": sum(row["owner_include"] == "yes" for row in admitted),
            "unwanted_admitted": sum(row["owner_include"] == "no" for row in admitted),
            "undecided_admitted": sum(
                row["owner_include"] not in {"yes", "no"} for row in admitted
            ),
        }
    changes = [
        row for row in decisions if row["current_admitted"] != row["broader_admitted"]
    ]
    return {
        "schema_version": 1,
        "captured_at": baseline["captured_at"],
        "assessment_at": baseline["assessment_at"],
        "candidate_count": len(decisions),
        "reviewed_wanted": sum(row["owner_include"] == "yes" for row in decisions),
        "reviewed_unwanted": sum(row["owner_include"] == "no" for row in decisions),
        "policies": policies,
        "changes": changes,
        "wanted_still_rejected": [
            row
            for row in decisions
            if row["owner_include"] == "yes" and not row["current_admitted"]
        ],
        "recovered_wanted": [row for row in changes if row["owner_include"] == "yes"],
        "added_unwanted": [row for row in changes if row["owner_include"] == "no"],
        "profiles": baseline["profiles"],
        "keywords": sorted(AI_KEYWORDS),
        "limitations": [
            "Targeted development reviews, not a random or held-out accuracy test.",
            "Title-only replay: frozen feed summaries and article bodies are unavailable.",
            "September 30 is a retrospective assessment of entries captured October 6.",
            "Unknown preferences remain undecided; an added match is not a recovered wanted story.",
            "Admission only, not ranking, access, publisher caps or final report selection.",
            "Existing source bypasses remain in both policies.",
            "No network, dependency, publication or production-rule changes.",
        ],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("feedback", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() in {args.snapshot.resolve(), args.feedback.resolve()}:
        parser.error("Output must not overwrite an input")
    raw = [args.snapshot.read_bytes(), args.feedback.read_bytes()]
    result = compare_final(*(json.loads(data) for data in raw))
    result["input_sha256"] = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in zip(("snapshot", "feedback"), raw)
    }
    result["implementation_sha256"] = {
        name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
        for name in (
            "compare_final_admission.py",
            "compare_editorial.py",
            "compare_relevance.py",
            "editorial_relevance.py",
            "generate_report.py",
        )
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
