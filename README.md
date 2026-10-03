# auto-ai-news

Daily AI news reports from validated research and engineering sources.

Reports are published as GitHub Releases so each day has a stable, dated entry with clickable links, star ratings, reading-time estimates, and skipped-source notes.

Reports use a ranked article list with source names and UTC publication dates. Ratings are heuristic ranks; reading times estimate feed text rather than the full linked article. Source diagnostics and methodology appear in expandable sections.

Latest report: https://github.com/kantarcise/auto-ai-news/releases/latest

Quiet-day editions titled “not much happened today” from Latent Space and smol.ai are excluded, with the reason listed in the report's skipped section. These editions can contain substantial recap content; this is a title-based selection preference, not a full-content quality judgment.

Reports cover the last 48 hours by default. Older entries, missing/invalid dates, and future dates are excluded before link checks. Freshness exclusions are grouped separately from network failures. Short or empty reports are allowed; old stories never fill unused slots. A story may recur on consecutive days within this window. Date-only HTML listings use midnight UTC, so boundary decisions are conservative.

## Disclosure

This project was built with AI assistance. The daily reports are generated automatically from public source feeds.

auto-ai-news is an aggregator. Original articles, titles, and linked content belong to their respective sources and authors. This repository does not claim ownership of that original content.

## Run locally

```bash
python3 -m unittest discover -s tests
python3 scripts/generate_report.py --output /tmp/daily-ai-news.md
# Compare a wider window without publishing:
python3 scripts/generate_report.py --lookback-hours 72 --output /tmp/daily-ai-news-72h.md
```

## Automation

The GitHub Actions workflow runs every day at `06:15 UTC` and can also be started manually from the Actions tab. It creates or updates a release named `Daily AI News - YYYY-MM-DD` with the tag `daily-YYYY-MM-DD`.

Merging a freshness change does not rerun a deployment or edit historical releases. The next scheduled or manual run uses the new selection policy; a manual run on the same UTC date updates that day’s release.

Contributor and agent guidance: [AGENTS.md](AGENTS.md).

Source coverage, live-validation results, and collection limitations: [docs/sources.md](docs/sources.md).
