# Source expansion and validation

Ten additional primary sources are enabled, bringing the configured active total from six to sixteen. Existing sources remain configured. New sources use priority 4 so source membership alone does not receive the maximum priority bonus.

| New source | Coverage | Collection |
| --- | --- | --- |
| Google DeepMind | UK-based lab; model/research developments | Official RSS |
| Mistral AI | France; model/research and product developments | Official RSS |
| DeepSeek Research & News | China; model announcements and linked research papers | Official dated HTML cards |
| Hugging Face | Open models, tooling and research ecosystem | Official RSS |
| PyTorch | Engineering and inference/training tooling | Official RSS |
| Google Research | Research findings | Official RSS |
| Microsoft Research | Research and technical findings | Official RSS |
| AI2 | Open models and research | Official RSS |
| OpenAI | Research and product announcements | Official RSS |
| Anthropic Research | Research, evaluations and safety findings | Official dated HTML cards |

The official homepage and collection URL for each source are in [sources.json](../config/sources.json). Primary-source announcements are publisher claims, not independent fact verification. Existing independent analysis remains important.

## Validation

Run from the repository root:

```bash
python3 -m scripts.validate_sources --output /tmp/source-validation.json
python3 scripts/generate_report.py --output /tmp/daily-ai-news-preview.md
```

The audit fetches each enabled input, parses it with the production parser, counts dated/relevant entries, checks one newest article URL, and compares 48/72/168-hour windows. It does not publish a release or enforce a cutoff. It uses the current relevance and quiet-day rules, removes URL duplicates within each source, excludes future/missing dates from window counts, and reports operational failures. Window totals can still include the same story across different publishers. One successful sample does not establish that every link is accessible.

[Saved validation snapshot](source-validation-2026-10-03.json), October 3 at 18:15 Istanbul time:

| Window | Existing: candidates / contributing sources | Expanded: candidates / contributing sources |
| --- | --- | --- |
| 48 hours | 6 / 4 | 11 / 7 |
| 72 hours | 8 / 4 | 15 / 8 |
| 7 days | 20 / 5 | 38 / 11 |

These are eligible candidates before final link checks, not final report sizes. All 16 inputs parsed, and all extracted entries had dates. Nine of ten new-source sample links passed. The OpenAI feed parsed, but its sample article returned HTTP 403 on HEAD and GET fallback. Existing link filtering will exclude inaccessible articles; no bypass is added. The local integrated report completed with 30 articles using the existing unlimited-age policy.

Configured, successfully fetched, contributing, and finally selected source counts are different. A freshness window reduces contribution on a quiet day; it does not disable publishers. The new publishers will not all publish qualifying stories every 48 hours. Some valid headlines currently fail the keyword filter; relevance improvements remain a separate roadmap step.

## HTML-listing limitations

DeepSeek and Anthropic do not expose usable RSS at the probed URLs. Their public listings contain article cards with a title and displayed publication date. The standard-library adapter preserves the source URL/title/date and handles relative news links and external paper links. It raises a diagnostic if no cards are recognized after a layout change. It does not scrape article bodies or invent summaries.

Dates displayed without a time are represented as midnight UTC, an explicit convention rather than a known publication instant. Near-boundary window counts for these sources are therefore conservative. The freshness implementation should document this uncertainty. HTML layouts need fixture coverage and periodic validation.

## Deferred sources

- **Qwen (China):** the old official `https://qwenlm.github.io/blog/index.xml` parses but its newest entry is September 2025. The [official repository](https://github.com/QwenLM/qwenlm.github.io) points readers to `https://qwen.ai/research`; the newer page did not expose dated article cards usable by this adapter. Do not count the legacy feed as current coverage.
- **MiniMax (China):** the official news page was reachable, but the fetched listing did not expose dated cards; guessed RSS endpoints returned 404. A separately validated adapter is needed.
- **BAAI / Shanghai AI Lab (China):** probed feed endpoints returned HTML or 404. No unverified feed is enabled.
- **ELLIS / UK AISI / Aleph Alpha (Europe):** probed feed endpoints returned 404. Additional endpoint discovery or a tested adapter is needed.
- **Inria (France):** the probed RSS parsed but its newest entry was February 2023; unsuitable as evidence of current coverage.

This first expansion includes one directly collected Chinese lab and two European labs. Broader Chinese/European coverage remains a follow-up; the list is not padded with stale or unverified feeds.

## Freshness rollout

Issue #4 should remain a separate PR: make `--lookback-hours` configurable, start with the proposed 48-hour policy, explicitly handle missing/future dates, and group stale-feed diagnostics. Compare 48 and 72 hours on several daily snapshots before deciding the production default. A longer window increases coverage and repetition. Permit short reports and show the actual contributing source count. Do not silently widen the window or backfill old stories to reach 30.
