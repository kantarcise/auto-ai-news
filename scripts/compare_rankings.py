"""Replay saved shadow scores and show ordering disagreements without network I/O."""

import argparse
import datetime as dt
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from scripts.generate_report import markdown_escape, markdown_link


def compare(snapshot: dict, *, revision: str = "", limit: int = 20) -> dict:
    if limit < 1:
        raise ValueError("Review limit must be positive")
    inputs = snapshot["ranking_inputs"]
    config = snapshot["editorial_config"]
    by_id = {row["id"]: row for row in inputs}
    if len(by_id) != len(inputs):
        raise ValueError("Duplicate ranking input identities")
    unique = {}
    for row in inputs:
        if urlsplit(row["url"]).scheme not in {"https", "http"}:
            raise ValueError("Unsupported article URL scheme")
        if any(
            type(count) is not int or count < 1
            for count in row["document_counts"].values()
        ):
            raise ValueError("Invalid term counts")
        unique.setdefault(row["canonical_url"], set()).update(row["document_counts"])
    frequency = Counter(term for document in unique.values() for term in document)
    profiles = {
        profile["name"]: Counter(profile["description"].split())
        for profile in config["profiles"]
    }

    def vector(counts, adaptive):
        return {
            term: (1 + math.log(min(count, 3)))
            * (
                1 + math.log((1 + len(unique)) / (1 + frequency[term]))
                if adaptive
                else 1
            )
            for term, count in counts.items()
        }

    def similarity(left, right):
        denominator = math.sqrt(
            sum(value**2 for value in left.values())
            * sum(value**2 for value in right.values())
        )
        return (
            sum(left[term] * right[term] for term in left.keys() & right.keys())
            / denominator
            if denominator
            else 0.0
        )

    bonuses = {}
    parameters = snapshot["scoring_parameters"]
    captured_at = dt.datetime.fromisoformat(snapshot["captured_at"])
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("Capture date must be timezone-aware")
    for row in inputs:
        if row["admitted"]:
            published = dt.datetime.fromisoformat(row["published"])
            if published.tzinfo is None or published.utcoffset() is None:
                raise ValueError("Publication date must be timezone-aware")
            base = parameters["base"]
            if row["source_priority"] >= 5:
                base += parameters["priority_5"]
            elif row["source_priority"] >= 3:
                base += parameters["priority_3"]
            if row["legacy_keyword_score"] >= parameters["keyword_threshold"]:
                base += parameters["keyword_bonus"]
            age_hours = (captured_at - published).total_seconds() / 3600
            if age_hours < 0 or age_hours > snapshot["lookback_hours"]:
                raise ValueError("Ranking input outside the captured coverage window")
            if age_hours <= parameters["recent_hours"]:
                base += parameters["recent_bonus"]
            elif age_hours > parameters["old_hours"]:
                base -= parameters["old_penalty"]
            if row["story_kind"] in {"lab_research", "lab_announcement"}:
                base += parameters["lab_bonus"]
            if not math.isclose(base, row["current_score"], abs_tol=1e-9):
                raise ValueError("Current member score cannot be replayed")
        scores = []
        for adaptive in (False, True):
            best = 0.0
            for name in row["eligible_profiles"]:
                for document in (row["document_counts"], Counter(row["title_terms"])):
                    best = max(
                        best,
                        similarity(
                            vector(document, adaptive), vector(profiles[name], adaptive)
                        ),
                    )
            scores.append(min(config["maximum_rank_bonus"], 2 * best))
        bonuses[row["id"]] = scores

    ranking = snapshot["shadow_ranking"]
    rows = ranking["scores"]
    if len({row["url"] for row in rows}) != len(rows):
        raise ValueError("Duplicate ranked stories")
    for row in rows:
        members = [by_id[index] for index in row["member_ids"]]
        if not members or any(not member["admitted"] for member in members):
            raise ValueError("Ranked groups must have admitted members")
        for field, bonus_index in (
            ("current_score", None),
            ("fixed_score", 0),
            ("proposed_score", 1),
        ):
            expected = max(
                member["current_score"]
                + (bonuses[member["id"]][bonus_index] if bonus_index is not None else 0)
                for member in members
            )
            if not math.isfinite(row[field]) or not math.isclose(
                row[field], expected, abs_tol=1e-9
            ):
                raise ValueError(f"Saved {field} cannot be replayed")
        if urlsplit(row["url"]).scheme not in {"https", "http"}:
            raise ValueError("Unsupported article URL scheme")
    orders = {}
    for name, field, captured in (
        ("current", "current_score", "current_order"),
        ("fixed", "fixed_score", "fixed_order"),
        ("adaptive", "proposed_score", "proposed_order"),
    ):
        order = [
            row["url"] for row in sorted(rows, key=lambda row: row[field], reverse=True)
        ]
        if order != ranking[captured]:
            raise ValueError(f"Saved {name} order differs from replay")
        orders[name] = order
    positions = {
        name: {url: i + 1 for i, url in enumerate(order)}
        for name, order in orders.items()
    }
    disagreements = []
    selected_urls = {row["url"] for row in snapshot["policies"]["frontier"]["selected"]}
    for row in rows:
        ranks = {name: positions[name][row["url"]] for name in orders}
        spread = max(ranks.values()) - min(ranks.values())
        if spread:
            disagreements.append(
                {
                    "url": row["url"],
                    "title": row["title"],
                    "source": by_id[row["member_ids"][0]]["source"],
                    "ranks": ranks,
                    "spread": spread,
                    "selected_url": next(
                        (
                            by_id[index]["url"]
                            for index in row["member_ids"]
                            if by_id[index]["url"] in selected_urls
                        ),
                        None,
                    ),
                }
            )
    disagreements.sort(key=lambda row: (-row["spread"], row["ranks"]["current"]))
    return {
        "schema_version": 1,
        "captured_at": snapshot["captured_at"],
        "revision": revision,
        "scope": ranking["scope"],
        "orders": orders,
        "disagreement_count": len(disagreements),
        "review": disagreements[:limit],
        "omitted_review_count": max(0, len(disagreements) - limit),
        "fresh_rejected": [
            {"title": row["title"], "url": row["url"], "source": row["source"]}
            for row in inputs
            if not row["admitted"]
        ][:limit],
        "fresh_rejected_count": sum(not row["admitted"] for row in inputs),
        "actual_selected": snapshot["policies"]["frontier"]["selected"],
        "link_outcomes": snapshot["link_outcomes"],
    }


def render(result: dict) -> str:
    lines = [
        "# Daily ranking comparison",
        "",
        f"Captured: {markdown_escape(result['captured_at'])}",
        f"Generator revision: {markdown_escape(result['revision']) or 'not recorded'}",
        "",
        "Current = existing score. Fixed = existing score plus topic similarity with fixed word weights. Adaptive = existing score plus topic similarity with weights from this candidate pool.",
        "",
        "These are orderings before publisher caps and access checks, not three published reports. Only the current selection undergoes link checks; publication is a separate later workflow step. Unknown access is not a failed link. No editorial quality grades are inferred.",
        "",
        f"{result['disagreement_count']} stories change position. Showing the largest {len(result['review'])} disagreements; {result['omitted_review_count']} others are retained in the saved orders.",
        "",
        "| Article | Source | Current | Fixed | Adaptive | Current link check | Current selection |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in result["review"]:
        outcome = result["link_outcomes"].get(row["url"])
        access = (
            "Not checked"
            if outcome is None
            else ("Accessible" if outcome["accessible"] else outcome["reason"])
        )
        lines.append(
            f"| {markdown_link(row['title'], row['url'])} | {markdown_escape(row['source'])} | {row['ranks']['current']} | {row['ranks']['fixed']} | {row['ranks']['adaptive']} | {markdown_escape(access)} | {markdown_link('Selected link', row['selected_url']) if row['selected_url'] else 'Not selected'} |"
        )
    if not result["review"]:
        lines += ["", "No ordering disagreements in this run."]
    lines += [
        "",
        "## Fresh articles rejected before ranking",
        "",
        f"{result['fresh_rejected_count']} candidates were rejected; showing {len(result['fresh_rejected'])}. These are possible review candidates, not known missed important stories.",
        "",
    ]
    for row in result["fresh_rejected"]:
        if urlsplit(row["url"]).scheme in {"http", "https"}:
            lines.append(
                f"- {markdown_link(row['title'], row['url'])} · {markdown_escape(row['source'])}"
            )
    lines += [
        "",
        "## Review guidance",
        "",
        "Review the largest disagreements first: should this story be included, how useful is it (1–3), and did you read the article or only the headline? Treat inaccessible articles as unknown. Both alternatives share the current admission rules, so rejected stories cannot be rescued by reordering. Review data is needed before claiming that either ordering is better.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--revision", default="")
    args = parser.parse_args()
    if (
        len({path.resolve() for path in (args.snapshot, args.output, args.json_output)})
        != 3
    ):
        parser.error("Input and outputs must be distinct")
    raw = args.snapshot.read_bytes()
    try:
        result = compare(json.loads(raw), revision=args.revision)
    except (KeyError, ValueError, TypeError) as exc:
        parser.error(
            f"Cannot replay snapshot: {exc}. Capture with --evaluation-output and --evaluation-excerpts."
        )
    result["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(render(result), encoding="utf-8")
    args.json_output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
