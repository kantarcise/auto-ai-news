"""Gate a seven-day trial and export allowlisted public evaluation summaries."""

import argparse
import json
import os
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from scripts import generate_report as report
from scripts.cloudflare_assessment import MODEL
from scripts.model_assessment import QUESTION_VERSION


def trial_active(start, today):
    if not start:
        return False
    first = date.fromisoformat(start)
    if first.isoformat() != start:
        raise ValueError("Start date must be YYYY-MM-DD")
    return 0 <= (today - first).days < 7


def export(capture, result):
    """Publish derived metadata only, never captured evidence or raw responses."""
    if result["evidence_arm"] != "content" or result["mode"] != "shadow":
        raise ValueError("Expected content shadow comparison")
    if result["status"] not in {"complete", "unavailable"}:
        raise ValueError("Expected completed or explicitly unavailable model arm")
    when = datetime.fromisoformat(result["captured_at"])
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("Capture clock must be timezone-aware")
    if capture["captured_at"] != result["captured_at"]:
        raise ValueError("Capture clocks differ")
    day = when.astimezone(UTC).date().isoformat()
    rows = {i: r for i, r in enumerate(capture["collection"])}
    provenance = Counter()
    for decision in result["decisions"]:
        origin = rows[decision["id"]]["article_evidence"]["provenance"]
        provenance[origin] += 1
    lines = [
        f"# Model evaluation — {day}",
        "",
        "**Experimental, unblinded editorial comparison. The normal daily release still uses rules.**",
        "",
        f"Status: **{result['status']}**. Captured at {when.astimezone(UTC).isoformat()}.",
        "",
        "Download `rules.md` and `content.md` from this release. Both use this evaluation run’s frozen candidates, clock, release history, scores and downstream constraints. The separately scheduled production release can differ because it fetches feeds at another time.",
        "",
        f"Rules selected: {len(result['baseline_selected'])}; content selected: {len(result['candidate_selected'])}.",
        "",
    ]
    if result["status"] == "unavailable":
        lines += [
            "**Model arm unavailable. `content.md` is the entire rules fallback; do not judge it as a completed model comparison.**",
            "",
        ]
    usage = result["usage"]
    lines += [
        f"Model attempts: {usage['new_assessment_attempts']}; reported input tokens: {usage['reported_input_tokens']}; reported output tokens: {usage['reported_output_tokens']}.",
        "",
        f"Unknown input/output usage counts: {usage['unknown_input_usage_count']} / {usage['unknown_output_usage_count']}. These are token metrics, not account neurons or a free-tier guarantee.",
        "",
        f"Comparison runtime: {result['runtime_seconds']:.2f}s (excludes capture); new link checks: {result['new_link_requests']}.",
        "",
        "Evidence counts: "
        + ", ".join(
            f"{report.markdown_escape(k)}: {v}" for k, v in sorted(provenance.items())
        )
        + ".",
        "",
        f"Policy: {report.markdown_escape(result['policy_version'])}; revision: {report.markdown_escape(result['revision'] or 'unknown')}.",
        "",
        f"Model: {report.markdown_escape(MODEL)}; questions: {report.markdown_escape(QUESTION_VERSION)}.",
        "",
        "## Candidate decisions",
        "",
        "Admission is before deduplication, grouping, accessible-link selection and publisher caps. A yes here does not guarantee a report slot. Labels are not editorial quality grades. Partial/truncated negatives retain baseline admission under the current policy.",
        "",
        "| Article | Evidence / completeness | Rules admit | Content admit | AI / detail / type | Applied |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for d in result["decisions"]:
        evidence = rows[d["id"]]["article_evidence"]
        a = result["assessments"].get(d.get("assessment_key"))
        labels = (
            "unavailable"
            if a is None
            else " / ".join(
                a["answers"][k]
                for k in ("ai_subject", "engineering_detail", "article_type")
            )
        )
        origin = f"{evidence['provenance']} / {evidence['completeness']}"
        if evidence["truncated"]:
            origin += " / truncated"
        lines.append(
            f"| {report.markdown_link(d['title'], d['url'])} | {report.markdown_escape(origin)} | {d['baseline_admit']} | {d.get('candidate_admit')} | {report.markdown_escape(labels)} | {d['applied']} |"
        )
    lines += [
        "",
        "## Review",
        "",
        "Record preferred report, useful recoveries, unwanted additions/removals, duplicates, publisher/topic variety and reasons. Evaluate multiple independent dates; this development trial has no automatic promotion threshold. Existing rules remain available.",
        "",
        "Captured article text, raw responses, credentials and assessment caches are not attached. Original article links preserve source attribution.",
        "",
    ]
    return day, "\n".join(lines)


def public_report(text):
    """Relabel generated local disclosures without rewriting article titles."""
    replacements = {
        "# Unpublished paired report comparison": "# Experimental public paired report comparison",
        "Unpublished content-shadow-v1 comparison.": "Experimental public content-shadow-v1 comparison.",
        "Unpublished frozen rules replay.": "Experimental public frozen rules replay.",
    }
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        for old, new in replacements.items():
            if line.startswith(old):
                lines[index] = new + line[len(old) :]
                break
    title, _, body = "".join(lines).partition("\n")
    return (
        title
        + "\n\n**Experimental evaluation; not the production daily report.**\n"
        + body
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    gate = commands.add_parser("window")
    gate.add_argument("--github-output", type=Path, required=True)
    publish = commands.add_parser("export")
    publish.add_argument("capture", type=Path)
    publish.add_argument("comparison_dir", type=Path)
    publish.add_argument("--output-dir", type=Path, required=True)
    publish.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "window":
        try:
            active = trial_active(
                os.environ.get("MODEL_EVALUATION_START_DATE", ""),
                datetime.now(UTC).date(),
            )
        except ValueError:
            parser.error("MODEL_EVALUATION_START_DATE must be YYYY-MM-DD or empty")
        with args.github_output.open("a") as stream:
            stream.write(f"active={str(active).lower()}\n")
        return 0
    if args.output_dir.exists():
        parser.error("--output-dir must be new")
    capture = json.loads(args.capture.read_text())
    result = json.loads((args.comparison_dir / "comparison.json").read_text())
    day, notes = export(capture, result)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "review.md").write_text(notes, encoding="utf-8")
    # These rendered reports contain links and attribution, not captured bodies.
    for source, target in [
        ("baseline.md", "rules.md"),
        ("candidate.md", "content.md"),
        ("comparison.md", "differences.md"),
    ]:
        (args.output_dir / target).write_text(
            public_report((args.comparison_dir / source).read_text()), encoding="utf-8"
        )
    if args.github_output:
        with args.github_output.open("a") as stream:
            stream.write(f"report_date={day}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
