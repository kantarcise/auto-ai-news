# Reduce the forum-source advantage

Today LessWrong AI has priority 5 (+1.25 points), while PyTorch, NVIDIA Developer and Anthropic Research have priority 4 (+1). This contradicts the owner's October 10 preference: useful forum posts can be included, but should have a smaller source-only advantage than strong research and engineering sources.

This proposal sets **LessWrong AI to priority 2**, removing its 1.25-point source bonus. Priority 2 means zero source-only bonus under the existing scoring rule; it is not an importance grade, exclusion or negative score. A recent, relevant forum article can still outrank an older generic vendor update. Other source priorities, eligibility, keyword/recency/lab bonuses, publisher caps, grouping, history and topic-similarity experiments remain unchanged. The specific priority is a transparent preference setting, not an optimized or independently validated constant.

## Actual selection replay

Both comparisons use real saved daily captures and their original access results. The replay reproduces the exact baseline candidate order and selected URL order before proposing any change. It then reruns canonical deduplication, title grouping, sorting, publisher caps and access selection using proposed source priorities. Unknown access stops the comparison rather than inventing an accessible or failed link. No network requests, publication or new article inspections are part of replay.

| Selected article | October 9 before → after | October 10 before → after | Owner feedback |
| --- | --- | --- | --- |
| [Session-Aware Agentic Inference with NVIDIA Dynamo](https://pytorch.org/blog/session-aware-agentic-inference-with-nvidia-dynamo/) | 5 → 2 | 9 → 8 | Keep, importance 3 |
| [Lakebase and Agentic SDLC](https://www.databricks.com/blog/lakebase-and-agentic-sdlc-branching-databases-coding-agents) | 4 → 1 | 8 → 7 | Keep, importance 1; promotional |
| [Europe’s leading AI model still can’t reliably follow European law](https://www.lesswrong.com/posts/XK7qJ3vGjuFuHfxaF/europe-s-leading-ai-model-still-can-t-reliably-follow) | 1 → 4 | Not selected | Keep, importance 1 |
| [AI Scaling vs Human Scaling](https://www.lesswrong.com/posts/2J43xbszsuLv4zAk5/ai-scaling-vs-human-scaling) | 2 → 5 | Not selected | Keep, importance 1 |
| [Proof of useful work for verifying AI treaties](https://www.lesswrong.com/posts/xqjDi7oyadqxkmdLS/proof-of-useful-work-for-verifying-ai-treaties) | 3 → 6 | Not selected | Exclude |
| [Impactful scheduling for GPU clusters](https://huggingface.co/blog/allenai/impactful-scheduling) | Not selected | 7 → 5 | Not reviewed |

Both dates select **the same 30 article URLs as before**, with identical publisher counts. No article enters or leaves either selection. The improvement demonstrated here is order relative to the owner's source preference, not recovered-story recall or a general quality improvement. These are positions in the final cached selection, not just raw candidate positions; blocked representatives and publisher caps are replayed.

## What remains wrong

- The Databricks promotion still outranks the importance-3 PyTorch article on October 9. Source preference alone cannot measure technical substance or distinguish useful marketing from a deep engineering writeup.
- The unwanted treaty article remains selected, although it moves down. Do not turn the owner's difficulty understanding it into a general rejection rule; they explicitly value difficult technical infrastructure material.
- NVIDIA's AICR and Green Contexts articles, previously rated 3, still do not enter October 9's selection. Their raw candidate positions remain 51 and 54. Removing this source advantage does not fix their missing ranking signals.
- Latent Space and smol.ai retain priority 5 and their existing admission bypasses. This is a focused change to the reviewed forum source, not an unreviewed demotion of every community publication, roundup or independent practitioner.
- No automatic importance-3 bonus is assigned to lab articles. Topic-similarity alternatives stay in shadow mode; this change does not activate them or use an LLM.

## Evidence scope and provenance

The October 9 feedback covers only the first five selected articles. It helped design this adjustment and is therefore not held-out evidence. Reading depth was not specified for the first four; the owner supplied and discussed an article passage for PyTorch without saying whether they read the full post. The rejected article's numeric importance remains unset. Exact feedback is normalized in [the owner record](release-feedback-2026-10-09.json).

October 10 is a separate capture, not a blind human-reviewed test. Its article set overlaps October 9, so do not describe these two dates as independent story-level held-out evaluation. This comparison does not infer judgments for unreviewed titles, report precision or claim that all promoted articles are better.

The compact [October 9 input](source-priority-input-2026-10-09.json) and [October 10 input](source-priority-input-2026-10-10.json) retain admitted scoring metadata, actual link outcomes, baseline order and selected URLs, capture timestamps, original snapshot checksums, workflow URLs and generator revisions. The original full shadow captures were validated with `scripts.compare_rankings` before reducing them. Excerpts, normalized document terms and article bodies are omitted from the committed inputs. Eligibility is frozen; the comparison does not attempt to reconstruct a relevance decision from missing text. The October 10 capture was the first run after #32, so it had no earlier publication receipts available for exclusion; future pools will differ as history accumulates.

Reproduce both results without network access or publication:

```bash
python3 -m scripts.compare_source_priority docs/evaluation/source-priority-input-2026-10-09.json --output /tmp/source-priority-oct9.json
python3 -m scripts.compare_source_priority docs/evaluation/source-priority-input-2026-10-10.json --output /tmp/source-priority-oct10.json
```

The [October 9 results](source-priority-results-2026-10-09.json) and [October 10 results](source-priority-results-2026-10-10.json) contain complete before/after selected metadata, candidate orders, score/star changes, publisher counts, entered/left URL lists and input/config checksums. Stars are heuristic score buckets, not the owner's 1–3 usefulness grades.

## Verification and issue status

Offline regressions verify that equally recent/relevant engineering outranks the configured forum source, useful forum posts remain eligible, stronger recent forum material can outrank a generic older engineering update, both real baseline selections reproduce exactly, proposed URL sets/publisher counts are preserved, and invalid scores, orders, dates, unknown link outcomes and output collisions stop replay. Existing relevance, grouping/fallback, access, freshness, body, catch-up and Markdown tests remain in the suite.

This is a focused correction under #12 item 5 and contributes reproducible evidence to item 3. It finishes neither item. Semantic comparisons, content-sensitive ranking, unconditional source admission and substantive-update detection remain separate work. No production dependency, live-feed test, workflow dispatch or release edit is introduced.
