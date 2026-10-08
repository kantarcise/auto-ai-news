"""Compare frozen title-filter outcomes with topic-word additions offline."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from scripts.generate_report import Item, freshness_reason
from scripts.relevance_topics import TOPICS, topic_matches
from scripts.review_candidates import candidate_id


def compare(snapshot: dict, feedback: dict) -> dict:
    """Compare admission only; never invent link outcomes or run ranking."""
    captured = dt.datetime.fromisoformat(snapshot["captured_at"])
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("Capture clock must be timezone-aware.")
    now = dt.datetime.fromisoformat(
        snapshot.get("assessment_at", snapshot["captured_at"])
    )
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Assessment clock must be timezone-aware.")
    if snapshot["lookback_hours"] <= 0:
        raise ValueError("Coverage window must be positive.")
    if feedback["snapshot_captured_at"] != snapshot["captured_at"]:
        raise ValueError("Feedback belongs to a different snapshot clock.")
    if feedback["snapshot_sha256"] != snapshot["source_snapshot_sha256"]:
        raise ValueError("Feedback belongs to a different source capture.")

    candidates = {}
    for row in snapshot["collection"]:
        published = (
            dt.datetime.fromisoformat(row["published"]) if row["published"] else None
        )
        if published is not None and (
            published.tzinfo is None or published.utcoffset() is None
        ):
            raise ValueError("Candidate dates must be timezone-aware.")
        item = Item(row["title"], row["url"], row["source"], 0, published=published)
        if not row["url"] or freshness_reason(item, now, snapshot["lookback_hours"]):
            continue
        if row["url"] in candidates:
            raise ValueError("Recent collection must contain unique exact URLs.")
        if row["rejection_reason"] not in (
            "",
            "title relevance filter",
            "quiet-day title policy",
        ):
            raise ValueError("Unsupported recent collection outcome.")
        candidates[row["url"]] = row

    labels = {}
    for label in feedback["items"]:
        url = label["url"]
        if url not in candidates or url in labels:
            raise ValueError("Feedback has an unknown or duplicate candidate URL.")
        if (
            label["id"] != candidate_id(url)
            or label["title"] != candidates[url]["title"]
        ):
            raise ValueError("Feedback candidate identity does not match the capture.")
        if label["evidence"] != "user_feedback":
            raise ValueError("Expected direct owner-feedback provenance.")
        if label["include"] not in (None, "yes", "no", "unsure"):
            raise ValueError("Invalid inclusion preference.")
        grade = label["importance"]
        if grade is not None and (type(grade) is not int or grade not in range(4)):
            raise ValueError("Importance must be an integer 0–3 or null.")
        if label["include"] == "yes" and grade not in (1, 2, 3):
            raise ValueError("Wanted articles need importance 1–3.")
        if label.get("inspection_evidence") not in (
            None,
            "article",
            "title",
            "unavailable",
        ):
            raise ValueError("Invalid inspection evidence.")
        labels[url] = label

    selected = {row["url"] for row in snapshot["selected_representatives"]}
    if not selected <= candidates.keys():
        raise ValueError("Selected representatives must belong to the recent pool.")
    decisions = []
    for url, row in sorted(candidates.items()):
        current = row["rejection_reason"] == ""
        matches = topic_matches(row["title"])
        alternative = current or (
            row["rejection_reason"] == "title relevance filter" and bool(matches)
        )
        label = labels.get(url, {})
        decisions.append(
            {
                "id": candidate_id(url),
                "title": row["title"],
                "url": url,
                "source": row["source"],
                "current_admitted": current,
                "alternative_admitted": alternative,
                "added_topic_matches": matches if alternative and not current else [],
                "actually_selected": url in selected,
                "frozen_link_outcome": snapshot["link_outcomes"].get(url),
                "owner_include": label.get("include"),
                "owner_importance": label.get("importance"),
                "inspection_evidence": label.get("inspection_evidence"),
            }
        )
    summaries = {}
    for name in ("current", "alternative"):
        admitted = [row for row in decisions if row[f"{name}_admitted"]]
        summaries[name] = {
            "admitted": len(admitted),
            "owner_wanted_admitted": sum(
                row["owner_include"] == "yes" for row in admitted
            ),
            "owner_unwanted_admitted": sum(
                row["owner_include"] == "no" for row in admitted
            ),
            "no_decided_preference_admitted": sum(
                row["owner_include"] not in ("yes", "no") for row in admitted
            ),
        }
    result = {
        "captured_at": snapshot["captured_at"],
        "lookback_hours": snapshot["lookback_hours"],
        "scope": "Recent linked title admission; not final ranking or report selection.",
        "recent_candidates": len(decisions),
        "owner_wanted": sum(row["owner_include"] == "yes" for row in decisions),
        "owner_unwanted": sum(row["owner_include"] == "no" for row in decisions),
        "confirmed_article_inspections": sum(
            row["inspection_evidence"] == "article" for row in decisions
        ),
        "topic_patterns": TOPICS,
        "policies": summaries,
        "newly_admitted": [
            row["id"]
            for row in decisions
            if row["alternative_admitted"] and not row["current_admitted"]
        ],
        "decisions": decisions,
    }

    if "assessment_at" in snapshot:
        result["assessment_at"] = snapshot["assessment_at"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("feedback", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.snapshot.resolve(), args.feedback.resolve()}:
        parser.error("Output must differ from both inputs.")
    snapshot_bytes = args.snapshot.read_bytes()
    feedback_bytes = args.feedback.read_bytes()
    result = compare(json.loads(snapshot_bytes), json.loads(feedback_bytes))
    result["input_sha256"] = {
        "snapshot": hashlib.sha256(snapshot_bytes).hexdigest(),
        "feedback": hashlib.sha256(feedback_bytes).hexdigest(),
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
