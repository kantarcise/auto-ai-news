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

## Opt-in evidence before relevance filtering

Issue #38's first step adds a separate best-effort evidence capture for future
paired report comparisons. It does not replace the reading-time extractor,
change admission/ranking, call a model, or change the daily workflow. Run:

```bash
python3 scripts/generate_report.py \
  --output /tmp/daily-ai-news.md \
  --evaluation-output /tmp/article-evidence.json \
  --evaluation-article-content
```

The new flag requires an evaluation output and conflicts with
`--no-article-bodies`. It explicitly opts into saving bounded article text;
keep these captures local rather than publishing scraped bodies by default.
The existing workflow does not set this flag. Its normal evaluation snapshots
and public reports retain their current behavior.

For fresh, linked candidates not previously published or excluded by the
quiet-day policy, capture evidence **before** title/summary relevance admission.
This includes articles the baseline relevance filter rejects. Each candidate's
`article_evidence` is stored separately from the generator Item: it cannot
alter the baseline's summary, content, score, reading-time estimate or selection.

Evidence preference is usable explicit RSS/Atom content (at least 100 words),
then recognized visible article text, then a short feed excerpt, feed summary
or title. The feed threshold is a retrieval preference, not an editorial rule.
A recognized article can be shorter than 100 words and is marked `short`.
Navigation, hidden text, scripts, forms, comments and related-post regions are
excluded. Explicit body containers are preferred over enclosing article/main
layouts when substantial text is available. Child regions are not also collected
into their layout parent, keeping short recommendation articles out of a
substantial main body. Among equally preferred regions, one substantial body can be used
alongside short cards; multiple plausible substantial bodies remain unavailable.
These heuristics are not a guarantee of correct article boundaries.

Visible subscription previews are usable, marked `public_preview` and
`completeness: partial`. Gate contents and subsequent text within the active
region are excluded. Subscriber text embedded in scripts or hidden HTML is
never used. Other extracted/feed text has unknown completeness, even when no
size truncation occurred. Outgoing links are not fetched, and JavaScript is
not executed. Labels describe the available evidence, not article quality.

The independent evaluation budget is 20 unique HTTP(S) article requests per
run, with an 8-second socket timeout, three redirects, at most 3,000,000 HTML
response bytes and a 12,000-character normalized text excerpt. Script-heavy
pages can exceed the original reading-time extractor's 1 MB response limit
without exceeding this budget. Responses above 3 MB, unsupported encodings/non-HTML
responses and fetch errors produce explicit diagnostics with fallback evidence.
Gzip is supported with the same 3 MB bound on both the response and decoded
stream; other encodings remain unavailable. Oversized HTML is rejected entirely; only successfully extracted text is
excerpted. This budget is additional to feed retrieval, link checks and the
unchanged selected-body reading-time budget. Socket timeouts are not total-run
deadlines.

The canonical-URL cache avoids duplicate article requests within the capture.
The saved JSON freezes the actual evidence for later offline comparisons; it
is not an automatic persistent HTTP cache across ephemeral Actions runners.
Records include provenance, completeness, text truncation, pre-limit character
count, excerpt SHA-256, and (when available) redirect destination, UTC fetch time
and response SHA-256. Failed retrieval diagnostics remain attached to fallback
text; a failed fetch never becomes an editorial rejection.

Synthetic offline fixtures reproduce the observed preview, short-entry and
multiple-region structures without committing publishers' full article text.
Tests also cover script-heavy/oversized responses, caching, request budgets,
feed preference, missing evidence and identical rendered baseline reports with
capture enabled or disabled. Cloudflare assessments and editorial A/B policy
remain later steps of #38.
