# auto-ai-news

Daily AI news reports from a small set of trusted sources.

Reports are published as GitHub Releases so each day has a stable, dated entry with clickable links, star ratings, reading-time estimates, and skipped-source notes.

Latest report: https://github.com/kantarcise/auto-ai-news/releases/latest

## Disclosure

This project was built with AI assistance. The daily reports are generated automatically from public source feeds.

auto-ai-news is an aggregator. Original articles, titles, and linked content belong to their respective sources and authors. This repository does not claim ownership of that original content.

## Run locally

```bash
python3 -m unittest discover -s tests
python3 scripts/generate_report.py --output daily-ai-news.md
```

## Automation

The GitHub Actions workflow runs every day at `06:15 UTC` and can also be started manually from the Actions tab. It creates or updates a release named `Daily AI News - YYYY-MM-DD` with the tag `daily-YYYY-MM-DD`.

Contributor and agent guidance: [AGENTS.md](AGENTS.md).
