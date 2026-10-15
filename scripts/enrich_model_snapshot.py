"""Collect optional evidence from saved candidates without fetching feeds again."""

import argparse
import copy
import json
from pathlib import Path

from scripts.article_evidence import EvidenceCollector
from scripts.generate_report import USER_AGENT, Item


def enrich(snapshot):
    enriched = copy.deepcopy(snapshot)
    collector = EvidenceCollector(USER_AGENT)
    for row in enriched["collection"]:
        if "comparison_candidate" not in row:
            continue
        fields = row.pop("evidence_input")
        item = Item(row["title"], row["url"], row["source"], 0, **fields)
        item.canonical_url = row["comparison_candidate"]["canonical_url"]
        row["article_evidence"] = collector.capture(item)
    return enriched


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.resolve() == args.snapshot.resolve():
        parser.error("Output must differ from frozen input")
    result = enrich(json.loads(args.snapshot.read_text(encoding="utf-8")))
    # Only a fully completed stage produces the input used for model selection.
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
