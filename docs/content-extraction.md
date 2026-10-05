# Article text and reading-time estimates

After ranking, grouping, and link checks, the generator attempts HTML retrieval for selected representative stories with no usable feed-content estimate. This does not change ranking or remove stories. Alternate coverage is not fetched. Explicit RSS/Atom content containing at least 100 words is preferred; that threshold does not establish that the feed contains the full article.

The standard-library extractor recognizes `article`, `main`, and common body classes. It removes navigation, footers, sidebars, scripts, forms, hidden elements, and common comments/share/signup blocks. It prefers an article region over a main region. Multiple article regions, short excerpts, recognizable subscription gates, or absent body regions produce unknown estimates. It does not bypass paywalls, execute JavaScript, or extract PDFs.

Limits per report: 20 unique selected URLs, an 8-second socket timeout, at most three redirects, and 1,000,000 response bytes. Redirects must remain HTTP(S). Non-HTML, encoded responses, and oversized responses remain unknown; truncated text is never estimated. URL results are cached within the run. Existing feed retrieval and link checks are separate from this budget. Socket timeouts are not a total-run deadline.

Reading times round up at 225 words per minute, with a 100-word minimum. Labels distinguish feed content from extracted body. Extraction is heuristic: a recognized region can still contain an excerpt or boilerplate, and estimates do not guarantee complete article text or judge editorial quality. Failures appear separately under “Article text unavailable.”

Use `--no-article-bodies` for feed-only generation. For a local preview, keep output outside the repository:

```bash
python3 scripts/generate_report.py --output /tmp/daily-ai-news.md
```

Offline regression tests mock HTTP responses and cover body isolation, excerpts, gates, size/time bounds, feed preference, caching, and request budgets. No runtime dependencies are added.
