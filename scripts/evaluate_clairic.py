"""Run the five-case Clairic extraction experiment against Workers AI."""

import argparse
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from scripts.cloudflare_assessment import NoRedirect

SAMPLE = Path(__file__).resolve().parents[1] / "docs/evaluation/clairic-sample.json"
MODEL = "@cf/cloudflare/clairic"


def payload(case):
    return {
        "model": "clairic",
        "state": case["text"],
        "fields": {
            "model_name": {
                "type": "text",
                "instructions": "Exact name of the AI model discussed, if present. "
                "Software libraries and frameworks are not AI models.",
            },
            "hardware": {
                "type": "text",
                "instructions": "Exact name of the accelerator or hardware platform "
                "used in the reported work, if present.",
            },
            "metric_value": {
                "type": "number",
                "instructions": f"Extract only an explicit value. {case['metric']}",
            },
        },
    }


def review_result(body, case):
    if body.get("success") is not True:
        raise ValueError("provider reported failure")
    result = body["result"]
    if result.get("truncated"):
        raise ValueError("provider returned incomplete output")

    reviewed = {}
    for key, expected in case["expected"].items():
        answer = result["answers"][key]
        if answer.get("valid") is False or answer.get("complete") is False:
            raise ValueError("provider returned an invalid or incomplete field")
        value = answer["value"]
        numeric = type(value) in (int, float) and math.isfinite(value)
        if value is not None and not (
            numeric if key == "metric_value" else isinstance(value, str)
        ):
            raise ValueError("unexpected field type")
        field = {"value": value, "expected": expected, "match": value == expected}
        span = answer.get("span")
        if (
            value is not None
            and isinstance(span, list)
            and len(span) == 2
            and all(type(offset) is int for offset in span)
            and 0 <= span[0] < span[1] <= len(case["text"])
        ):
            field["span"] = span
            field["source_slice"] = case["text"][span[0] : span[1]]
        reviewed[key] = field

    usage = result["usage"]
    billed = {}
    for key in ("input_tokens", "passes"):
        count = usage[key]
        if type(count) is not int or count < 1:
            raise ValueError("invalid usage counter")
        billed[key] = count
    return {"fields": reviewed, "usage": billed}


def run(account, token):
    cases = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if len(cases) != 5:
        raise ValueError("expected exactly five frozen cases")
    requests = [json.dumps(payload(case)).encode() for case in cases]
    # Bound the text sent across all five requests. The input is small even
    # when Cloudflare reads it again for each of the three requested fields.
    if sum(map(len, requests)) > 8_000:
        raise ValueError("sample exceeds the 8 KB request budget")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    opener = urllib.request.build_opener(NoRedirect())
    for case, data in zip(cases, requests, strict=True):
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        started = time.monotonic()
        with opener.open(request, timeout=25) as response:
            raw = response.read(64_001)
        if len(raw) > 64_000:
            raise ValueError("response exceeds 64 KB")
        result = review_result(json.loads(raw), case)
        yield {
            "case": case["id"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
            **result,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="store_true", help="Send five live API requests"
    )
    options = parser.parse_args()
    if not options.run:
        parser.print_help()
        return 0
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not re.fullmatch(r"[!-~]+", token):
        parser.error("set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")
    try:
        for result in run(account, token):
            print(json.dumps(result), flush=True)
    except urllib.error.HTTPError as exc:
        parser.exit(1, f"Cloudflare returned HTTP {exc.code}\n")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Experiment stopped ({type(exc).__name__})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
