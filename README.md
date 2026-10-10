# auto-ai-news

Daily AI news reports from validated research and engineering sources.

Reports are published as GitHub Releases so each day has a stable, dated entry with clickable links, star ratings, reading-time estimates, and skipped-source notes.

Reports use a ranked article list with source names and UTC publication dates. Ratings are heuristic ranks; reading times estimate explicit RSS/Atom content when at least 100 words are available. For selected stories with insufficient feed text, bounded HTML retrieval attempts to extract the article body. Successful estimates say “extracted body”; unavailable or short bodies show “Read time unknown.” See [content extraction limits](docs/content-extraction.md). Feed content is not guaranteed to be the full linked article; estimates round up at 225 words per minute. Source diagnostics and methodology appear in expandable sections.

Latest report: https://github.com/kantarcise/auto-ai-news/releases/latest

Quiet-day editions titled “not much happened today” from Latent Space and smol.ai are excluded, with the reason listed in the report's skipped section. These editions can contain substantial recap content; this is a title-based selection preference, not a full-content quality judgment.

Reports cover the last 72 hours by default. Older entries, missing/invalid dates, and future dates are excluded before link checks. Freshness exclusions are grouped separately from network failures. Short or empty reports are allowed; old stories never fill unused slots. Automated reports put new articles first and move canonical URLs recorded in earlier reports into an expandable “Previously included — catch up” section, with article links and links to the earlier reports. Catch-up entries do not consume new-article slots and stay within the same coverage window. Same-day reruns keep today’s articles eligible. Local runs omit history unless requested. See [publication history](docs/publication-history.md) for persistence, rollout and update limits. Date-only HTML listings use midnight UTC, so boundary decisions are conservative.

Selection gives qualifying frontier-lab research/model announcements a bounded bonus, using a headline rule that excludes common corporate/customer marketing. Scores are sorted before being mapped to stars. The cap is four accessible articles per publisher; Anthropic News and Research share one publisher. Cap/report-limit exclusions appear separately from freshness and network diagnostics. Short reports are allowed, and the 72-hour window is unchanged. See [the selection policy](docs/selection-policy.md) for weights and limitations.

## Disclosure

This project was built with AI assistance. The daily reports are generated automatically from public source feeds.

auto-ai-news is an aggregator. Original articles, titles, and linked content belong to their respective sources and authors. This repository does not claim ownership of that original content.

## Run locally

```bash
python3 -m unittest discover -s tests
python3 scripts/generate_report.py --output /tmp/daily-ai-news.md
# Compare a shorter window without publishing:
python3 scripts/generate_report.py --lookback-hours 48 --output /tmp/daily-ai-news-48h.md
```

## Automation

The GitHub Actions workflow runs every day at `06:15 UTC` and can also be started manually from the Actions tab. It creates or updates a release named `Daily AI News - YYYY-MM-DD` with the tag `daily-YYYY-MM-DD`.

Merging a freshness change does not rerun a deployment or edit historical releases. The next scheduled or manual run uses the new selection policy; a manual run on the same UTC date updates that day’s release.

Contributor and agent guidance: [AGENTS.md](AGENTS.md).

Source coverage, live-validation results, and collection limitations: [docs/sources.md](docs/sources.md).

Editorial rubric, human review batch and offline evaluation: [docs/evaluation](docs/evaluation/README.md).

Shared announcements with identical detailed titles published within 24 hours are shown as one story with checked alternate source links. Different titles/versions remain separate; this is conservative grouping rather than semantic similarity. Story limits apply to representative publishers; alternate attribution does not consume extra headline slots.
