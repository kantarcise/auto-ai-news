# Source expansion and validation

The first expansion added ten primary sources (six to sixteen active inputs). The global engineering expansion adds ten more, bringing the active total to 26. Research/tooling sources use priority 4; broad engineering blogs use priority 3 and still require an AI-related headline.

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

- **Qwen (China):** the old RSS was deferred as stale. The frontier-lab expansion now uses the official site’s public `/api/v2/article/retrieval` endpoint with publisher dates and its `/blog?id=...` article route. It does not count the legacy RSS as current coverage.
- **MiniMax (China):** the initial news/RSS probes failed. The frontier-lab expansion now collects `/blog`, whose cards contain explicit ISO publication dates.
- **BAAI / Shanghai AI Lab (China):** probed feed endpoints returned HTML or 404. No unverified feed is enabled.
- **ELLIS / UK AISI / Aleph Alpha (Europe):** probed feed endpoints returned 404. Additional endpoint discovery or a tested adapter is needed.
- **Inria (France):** the probed RSS parsed but its newest entry was February 2023; unsuitable as evidence of current coverage.

This first expansion includes one directly collected Chinese lab and two European labs. Broader Chinese/European coverage remains a follow-up; the list is not padded with stale or unverified feeds.

## Freshness rollout

The freshness PR for issue #4 adds a positive `--lookback-hours` (default 72), excludes missing/invalid and future dates, and groups freshness diagnostics separately from network failures. Use 72 hours as the initial production default, as requested. Compare 48 and 72 hours over additional daily snapshots to assess coverage and repetition. A longer window increases coverage and repetition. Permit short reports and show the actual contributing source count. Do not silently widen the window or backfill old stories to reach 30.

## Global engineering expansion

| Source | Coverage | Collection |
| --- | --- | --- |
| Cloudflare | US; agents, developer infrastructure and AI engineering | Official RSS |
| AMD ROCm | US; inference, training and accelerator engineering | Official Atom |
| World Labs | US; spatial intelligence and world models | Official dated HTML cards |
| NVIDIA Developer | US; AI development and accelerated computing | Official RSS |
| NAVER D2 | South Korea; engineering, including Korean-language AI posts | Official Atom |
| Kakao Tech | South Korea; engineering and AI development | Official RSS |
| LY Corporation Engineering | Japan; engineering (successor to LINE Engineering blog) | Official Atom |
| GitHub Engineering | US; development tooling and engineering | Official RSS |
| Vercel | US; developer platform and AI tooling | Official Atom |
| Databricks | US; data/AI engineering | Official RSS |

Broad engineering feeds are filtered using the existing title policy. Added terms recognize agentic development, software factory/factories, spatial intelligence, and Korean 인공지능. This remains a heuristic: it can miss Korean headlines without a recognized term and can include tangential matches. No source-wide relevance bypass is introduced.

Bending Spoons is recorded as disabled: its verified [Medium publication feed](https://medium.com/feed/bendingspoons) has a newest entry of November 7, 2024. Its main website did not expose a validated current engineering feed. A current dated publication URL is needed before enabling it. StrongDM's software-factory material is a separate publisher and has not been substituted for Bending Spoons.

Chinese coverage remains DeepSeek. The Qwen and MiniMax adapter gaps above remain open; this expansion does not claim additional Chinese research coverage. European coverage from the previous expansion remains available.

World Labs uses the same date-only convention as DeepSeek and Anthropic. The snapshot below validates the current layout; an offline card test protects title/date extraction. No workflow, publication schedule, freshness cutoff, production dependency, or historical release is changed.

[Global validation snapshot](source-validation-global-2026-10-03.json), October 3 at 18:34 Istanbul time:

| Window | First 16 sources: candidates / contributors | All 26 sources: candidates / contributors |
| --- | --- | --- |
| 48 hours | 11 / 7 | 17 / 11 |
| 72 hours | 15 / 8 | 33 / 12 |
| 7 days | 38 / 11 | 67 / 16 |

All ten new inputs parsed with dates and all ten newest-article samples passed link checks. Across the entire configuration, 25 of 26 inputs parsed: the existing DeepMind endpoint returned a parsing failure in this snapshot. The existing OpenAI sample still returned 403. These are current failures, not guarantees of future availability. Counts are candidates before final link checks and story grouping. World Labs, NAVER, Kakao, LY and GitHub contributed no matching articles within 48 hours in this snapshot. More configured publishers do not guarantee ten or thirty fresh articles every day.

## Frontier-lab content resources

Every lab in the October 3 shortlist is registered in `config/sources.json`. Seven additional inputs are enabled, bringing the active total to 33. Registration is not a ranking bonus and does not guarantee a recent qualifying article. Two labs remain visibly disabled because a reliable dated input is still missing.

| Lab | Collection status |
| --- | --- |
| OpenAI | Existing official RSS; sampled article access can return 403 |
| Anthropic | Existing Research listing plus new News listing |
| Google DeepMind | Existing official RSS |
| Mistral | Existing official RSS |
| DeepSeek | Existing dated news listing |
| Alibaba Qwen | New official public article API; explicit publisher timestamp, timezone preserved |
| xAI | New dated News cards |
| Meta AI | New blog adapter; visible publication date follows title link |
| Z.ai / GLM | Registered, disabled: client-rendered blog bundle; stable dated listing adapter pending |
| Moonshot / Kimi | Registered, disabled: fetched listing/article HTML has no verified publication dates |
| MiniMax | New dated Blog cards with ISO dates |
| ByteDance Seed | New dated homepage announcement cards |
| Black Forest Labs | New dated Blog cards |
| World Labs | Existing dated Blog cards |

Kimi image-file timestamps and evaluation dates in prose are not publication dates. Z.ai’s page bundle is not treated as a dated feed. These two gaps are tracked in issue #17; they are not described as active coverage. No inferred dates, release-history backfill, or unrestricted GitHub commit feeds are used to fill them.

The HTML adapters use displayed publication dates and midnight UTC for date-only values. Qwen uses its explicit timezone-aware date. Its API article body is intentionally not copied into the report or passed to a whole-page reading-time estimator. Layout/schema failures are reported rather than silently inventing entries. Primary publisher titles are preserved; model-brand keywords (FLUX, Grok, MiniMax, Kimi, GLM, Seedance, Seedream, Muse model names) allow branded headlines through the existing title filter. This is still a lexical heuristic, not a frontier-membership relevance bypass.

Frontier-lab ranking preferences, publisher caps and announcement classification remain separate issue #17 work. PR #18 independently preserves explicit RSS/Atom content for reading-time estimates and marks excerpts/insufficient content unknown. This source expansion neither changes the 72-hour policy nor adds production dependencies.

[Frontier-source validation snapshot](source-validation-frontier-2026-10-03.json), October 3 at 19:31 Istanbul: all 33 active inputs parsed; all seven new sample article links passed. Among the new inputs, only Anthropic News had qualifying posts within 72 hours (two candidates). Newest extracted entries for several valid listings were older: BFL September 23, xAI September 28, Qwen September 20, Meta July 27, MiniMax August 13 and Seed August 5. These listings establish operational collection, not guaranteed up-to-date coverage of every lab announcement. Stale listings are exposed by freshness diagnostics and are never backfilled into daily reports. Some listings only expose featured/latest cards, not a complete publisher archive.
