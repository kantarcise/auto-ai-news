"""Compare tightened context rules with frozen PR #27 admission outcomes."""

import argparse
import hashlib
import json
from pathlib import Path

from scripts.compare_editorial import compare_editorial


def compare_context(snapshot: dict, feedback: dict, previous: dict) -> dict:
    current = compare_editorial(snapshot, feedback)
    if any(previous[key] != current[key] for key in ("captured_at", "assessment_at")):
        raise ValueError("Previous outcomes belong to a different capture/assessment")
    old = {row["url"]: row for row in previous["decisions"]}
    if len(old) != len(previous["decisions"]) or old.keys() != {
        row["url"] for row in current["decisions"]
    }:
        raise ValueError("Previous candidate identities differ")
    changes = []
    for row in current["decisions"]:
        prior = old[row["url"]]
        if any(
            prior[key] != row[key]
            for key in ("title", "source", "owner_include", "owner_importance")
        ):
            raise ValueError("Previous title/source/feedback differs")
        if type(prior["profile_admitted"]) is not bool:
            raise ValueError("Previous admission must be boolean")
        if prior["profile_admitted"] != row["profile_admitted"]:
            changes.append(
                {
                    "title": row["title"],
                    "url": row["url"],
                    "before": prior["profile_admitted"],
                    "after": row["profile_admitted"],
                    "owner_include": row["owner_include"],
                    "owner_importance": row["owner_importance"],
                }
            )
    return {
        "schema_version": 1,
        "captured_at": current["captured_at"],
        "assessment_at": current["assessment_at"],
        "config": current["profiles"],
        "before": previous["policies"]["profile"],
        "after": current["policies"]["profile"],
        "changes": changes,
        "limitations": [
            "Title-only comparison; frozen summaries are unavailable.",
            "Profiles/context rules were developed with these targeted owner reviews visible.",
            "Unreviewed exclusions may be useful stories; no negative preference is inferred.",
            "No new link checks, historical selections or ranking-quality claims.",
            "Existing Latent Space/smol.ai bypass and original keyword rank points remain.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("feedback", type=Path)
    parser.add_argument("previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [args.snapshot, args.feedback, args.previous]
    if args.output.resolve() in {path.resolve() for path in paths}:
        parser.error("Output must not overwrite an input")
    raw = [path.read_bytes() for path in paths]
    if json.loads(raw[2])["input_sha256"] != {
        name: hashlib.sha256(data).hexdigest()
        for name, data in zip(("snapshot", "feedback"), raw[:2])
    }:
        parser.error("Previous outcomes do not match input hashes")
    result = compare_context(*(json.loads(data) for data in raw))
    result["input_sha256"] = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in zip(("snapshot", "feedback", "previous"), raw)
    }
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
