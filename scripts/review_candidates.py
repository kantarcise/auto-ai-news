"""Prepare human review labels and evaluate frozen selections offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def candidate_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def prepare(snapshot: dict) -> dict:
    rows = {row["url"]: row for row in snapshot["policies"]["frontier"]["candidates"]}
    return {
        "snapshot_captured_at": snapshot["captured_at"],
        "reviewer": "",
        "items": [
            {
                "id": candidate_id(url),
                "url": url,
                "title": row["title"],
                "source": row["source"],
                "published": row["published"],
                "relevant": None,
                "include": None,
                "importance": None,
                "story_id": None,
                "evidence": None,
                "notes": "",
            }
            for url, row in sorted(rows.items())
        ],
    }


def validate(snapshot: dict, review: dict) -> dict:
    expected = {item["id"]: item for item in prepare(snapshot)["items"]}
    if review.get("snapshot_captured_at") != snapshot["captured_at"]:
        raise ValueError("Review belongs to a different captured snapshot.")
    items = review.get("items")
    if not isinstance(items, list):
        raise TypeError("Review must contain an items list.")
    labels = {}
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("Candidate label must be an object.")
        identifier = item.get("id")
        if identifier not in expected or identifier in labels:
            raise ValueError("Unknown or duplicate candidate ID.")
        if item.get("url") != expected[identifier]["url"]:
            raise ValueError("Candidate URL does not match its ID.")
        for field in ("relevant", "include"):
            if item.get(field) not in (None, "yes", "no", "unsure"):
                raise ValueError(f"{field} must be yes, no, unsure or null.")
        grade = item.get("importance")
        if grade is not None and (type(grade) is not int or grade not in range(4)):
            raise ValueError("Importance must be an integer 0–3 or null.")
        if item.get("evidence") not in (None, "title", "article", "unavailable"):
            raise ValueError("Evidence must be title, article, unavailable or null.")
        if item.get("evidence") == "unavailable" and item.get("include") in (
            "yes",
            "no",
        ):
            raise ValueError(
                "Unavailable evidence needs an unsure or unreviewed inclusion label."
            )
        if item.get("include") in ("yes", "no"):
            if item.get("evidence") is None:
                raise ValueError("A decided inclusion label needs evidence provenance.")
            if (
                not isinstance(review.get("reviewer"), str)
                or not review["reviewer"].strip()
            ):
                raise ValueError("Decided labels require a named reviewer.")
        if item.get("include") == "yes":
            if item.get("relevant") != "yes" or grade not in (1, 2, 3):
                raise ValueError(
                    "Included items must be relevant and have importance 1–3."
                )
            if (
                not isinstance(item.get("story_id"), str)
                or not item["story_id"].strip()
            ):
                raise ValueError("Included items need a story ID.")
        labels[identifier] = item
    if set(labels) != set(expected):
        raise ValueError("Keep every candidate row; leave unreviewed labels null.")
    return labels


def evaluate(snapshot: dict, review: dict) -> dict:
    labels = validate(snapshot, review)
    positives = {
        identifier
        for identifier, label in labels.items()
        if label.get("include") == "yes"
    }
    result = {
        "reviewed_candidates": sum(
            label.get("include") in ("yes", "no") for label in labels.values()
        ),
        "total_candidates": len(labels),
        "policies": {},
    }
    for name, policy in snapshot["policies"].items():
        selected = {candidate_id(row["url"]) for row in policy["selected"]}
        if not selected <= labels.keys():
            raise ValueError(
                "Policy selection contains candidates outside the review batch."
            )
        judged = {
            identifier
            for identifier in selected
            if labels[identifier].get("include") in ("yes", "no")
        }
        included = judged & positives
        result["policies"][name] = {
            "selected": len(selected),
            "reviewed_selected": len(judged),
            "review_coverage": len(judged) / len(selected) if selected else None,
            "precision_on_reviewed_selected": len(included) / len(judged)
            if judged
            else None,
            "recall_on_reviewed_candidates": len(selected & positives) / len(positives)
            if positives
            else None,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("snapshot", type=Path)
    prep.add_argument("--output", type=Path, required=True)
    score = sub.add_parser("evaluate")
    score.add_argument("snapshot", type=Path)
    score.add_argument("labels", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    if args.command == "prepare":
        args.output.write_text(json.dumps(prepare(snapshot), indent=2) + "\n")
    else:
        print(
            json.dumps(
                evaluate(snapshot, json.loads(args.labels.read_text())), indent=2
            )
        )


if __name__ == "__main__":
    main()
