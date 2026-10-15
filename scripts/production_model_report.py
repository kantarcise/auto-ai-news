"""Select a daily report with bounded Cloudflare decisions or complete rules fallback."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts import compare_model_reports as comparison
from scripts.cloudflare_assessment import MODEL
from scripts.generate_report import canonicalize_url
from scripts.model_assessment import QUESTION_SHA256, QUESTION_VERSION, AssessmentError
from scripts.publication_history import receipt_comment


def rules_fallback(text):
    """Keep the generated baseline and its receipt; disclose the failed model step."""
    title, separator, body = text.partition("\n")
    return (
        title
        + separator
        + "\n**Model selection unavailable: this entire report uses the existing rules fallback.**\n"
        + body
    )


def select_report(baseline, snapshot=None, *, mode="model-assisted", provider=None):
    if mode not in {"rules", "model-assisted"}:
        raise ValueError("Unknown selection mode")
    if mode == "rules":
        return baseline, {"selection": "rules", "failure": None}
    try:
        result = comparison.compare(
            snapshot,
            mode="shadow",
            provider=provider,
            fetch_missing_links=True,
            link_request_limit=100,
            production=True,
        )
        status = {
            "selection": "model-assisted",
            "policy": comparison.POLICY_VERSION,
            "model": MODEL,
            "question_version": QUESTION_VERSION,
            "question_sha256": QUESTION_SHA256,
            "failure": result["failure"],
            "usage": result["usage"],
            "runtime_seconds": result["runtime_seconds"],
            "rules_selected": len(result["baseline_selected"]),
            "model_selected": len(result["candidate_selected"]),
            "decisions": [
                {
                    **{
                        key: decision[key]
                        for key in (
                            "id",
                            "url",
                            "baseline_admit",
                            "candidate_admit",
                            "reason",
                            "applied",
                        )
                    },
                    "evidence": {
                        key: snapshot["collection"][decision["id"]]["article_evidence"][
                            key
                        ]
                        for key in ("provenance", "completeness", "truncated")
                    },
                    "answers": result["assessments"]
                    .get(decision.get("assessment_key"), {})
                    .get("answers"),
                }
                for decision in result["decisions"]
            ],
        }
        if result["status"] != "complete":
            status["selection"] = "rules-fallback"
            return rules_fallback(baseline), status
        text = result["candidate_report"]
        history = snapshot.get("publication_history")
        if history is not None:
            day = comparison.aware_date(snapshot["captured_at"]).date().isoformat()
            if history["report_date"] != day:
                raise ValueError("History and capture dates differ")
            urls = list(history["published"].get(day, []))
            urls.extend(row["url"] for row in result["candidate_selected"])
            urls.extend(
                url
                for row in result["alternate_coverage"]["candidate"]
                for url in row["urls"]
            )
            text += "\n" + receipt_comment(day, [canonicalize_url(url) for url in urls])
        return text, status
    except (AssessmentError, ValueError, TypeError, KeyError, OSError, RuntimeError):
        # A failed comparison must not prevent publishing the already generated
        # rules report. Never log exception text: it may contain external input.
        return rules_fallback(baseline), {
            "selection": "rules-fallback",
            "failure": {"code": "comparison_failed"},
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--status-output", required=True, type=Path)
    parser.add_argument(
        "--mode", choices=("rules", "model-assisted"), default="model-assisted"
    )
    parser.add_argument("--force-fallback", action="store_true")
    args = parser.parse_args(argv)
    inputs = {args.baseline_report.resolve()}
    if args.snapshot:
        inputs.add(args.snapshot.resolve())
    if (
        args.output.resolve() in inputs
        or args.status_output.resolve() in inputs
        or args.output.resolve() == args.status_output.resolve()
    ):
        parser.error("Outputs must differ from inputs and each other")
    baseline = args.baseline_report.read_text(encoding="utf-8")
    if args.force_fallback:
        text = rules_fallback(baseline)
        status = {
            "selection": "rules-fallback",
            "failure": {"code": "model_step_failed"},
        }
    else:
        snapshot = None
        if args.mode == "model-assisted":
            try:
                snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
            except (OSError, ValueError, AttributeError):
                pass
        text, status = select_report(
            baseline,
            snapshot,
            mode=args.mode,
            provider=(
                comparison.LazyCloudflare(100, 1_000_000)
                if args.mode == "model-assisted"
                else None
            ),
        )
    status["recorded_at"] = datetime.now(UTC).isoformat()
    args.output.write_text(text, encoding="utf-8")
    args.status_output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status))
    if status["selection"] == "rules-fallback":
        print(
            "::warning::Model selection unavailable; publishing the complete rules fallback."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
