"""Add optional source excerpts to a completed Clef report."""

import argparse
import http.client
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from scripts.cloudflare_assessment import NoRedirect
from scripts.generate_report import markdown_escape, markdown_link
from scripts.preview_clairic import (
    FIELDS,
    TOKEN_STOP,
    request_clairic,
    source_state,
)

MAX_DAILY_REQUESTS = 15


def enrich(report, snapshot, selection, extract):
    status = {"attempts": 0, "shown": 0, "input_tokens": 0, "passes": 0, "stop": None}
    if selection["selection"] != "model-assisted":
        return report, status
    eligible_ids = {
        decision["id"]
        for decision in selection["decisions"]
        if decision["applied"]
        and decision["candidate_admit"] is True
        and (decision["answers"] or {}).get("engineering_detail") == "yes"
    }
    lines = report.splitlines(keepends=True)
    insertions = []
    for rank, article in enumerate(selection["selected_articles"], 1):
        if (
            status["attempts"] >= MAX_DAILY_REQUESTS
            or status["input_tokens"] >= TOKEN_STOP
        ):
            status["stop"] = "budget"
            break
        index = article["id"]
        if index not in eligible_ids:
            continue
        headline = f"{rank}. **{markdown_link(article['title'], article['url'])}**  \n"
        if headline not in lines:
            continue
        first = lines.index(headline)
        end = next((i for i in range(first + 1, len(lines)) if lines[i] == "\n"), None)
        if end is None or end <= first + 1:
            continue
        evidence = snapshot["collection"][index]["article_evidence"]
        state = source_state(evidence)
        if not state.strip() or evidence["provenance"] in {"title_only", "unavailable"}:
            continue
        status["attempts"] += 1
        try:
            usage, fields, warning = extract(state)
        except (ValueError, KeyError, TypeError, OSError, http.client.HTTPException):
            status["stop"] = "request_usage_unknown"
            break
        status["input_tokens"] += usage["input_tokens"]
        status["passes"] += usage["passes"]
        detail = fields.get("detail")
        if warning or not detail or len(detail[0].split()) > 25:
            continue
        indent = " " * (len(str(rank)) + 2)
        insertions.append(
            (end, f"{indent}Source detail (Clairic) · “{markdown_escape(detail[0])}”\n")
        )
        status["shown"] += 1
    for end, excerpt in reversed(insertions):
        lines[end - 1] = lines[end - 1].rstrip(" \n") + "  \n"
        lines.insert(end, excerpt)
    return "".join(lines), status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--selection-status", type=Path, required=True)
    args = parser.parse_args(argv)
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not re.fullmatch(r"[!-~]+", token):
        parser.error("set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")

    report = args.report.read_text(encoding="utf-8")
    opener = urllib.request.build_opener(NoRedirect())
    updated, status = enrich(
        report,
        json.loads(args.snapshot.read_text(encoding="utf-8")),
        json.loads(args.selection_status.read_text(encoding="utf-8")),
        lambda state: request_clairic(
            opener, account, token, state, fields={"detail": FIELDS["detail"]}
        ),
    )
    print(json.dumps({"clairic": status}), flush=True)
    if updated != report:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.report.parent, delete=False
        ) as output:
            path = Path(output.name)
            try:
                output.write(updated)
                output.close()
                path.replace(args.report)
            finally:
                path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
