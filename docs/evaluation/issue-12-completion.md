# Finish issue #12: delivered work and historical filter comparison

**Updated October 24, 2026 against current main.** Daily production now uses Cloudflare Clef-flash with complete rules fallback, adopted in PR #45 on October 15. PR #46, merged October 23, fixes the request-size mismatch that rejected valid multilingual evidence. See the [production selection guide](../model-assisted-production.md) for the current behavior and operating limits. This close-out PR changes no production behavior.

**Historical decision, October 11: do not broaden the keyword baseline on this evidence.** Relaxing generic keyword checks recovered no additional article the owner had marked wanted in the saved reviews. It added one unreviewed engineering-looking headline, whose usefulness remained undecided. That comparison did not justify a broader keyword rule. It did not evaluate decision models and is not a recommendation to revert the subsequent model-assisted rollout.

This finishes the agreed bounded work on [issue #12](https://github.com/kantarcise/auto-ai-news/issues/12). It does not mean every original research proposal was implemented. The remaining ambitions are explicitly deferred to [optional follow-up #35](https://github.com/kantarcise/auto-ai-news/issues/35), rather than conditions for closing #12. No new article-rating batch is required for this decision.

## What was compared

Both policies use the same saved candidates and owner feedback:

- **Current (historical comparison label):** the October 11 topic/model-family/context rules, generic keyword fallback and existing source bypasses, replayed on titles only. This label in the saved result files refers to the rules baseline, not today's model-assisted production pipeline.
- **Broader alternative:** retain everything current admits; also admit headlines with any existing AI keyword even when its supporting AI context is absent. Keep quiet-day and nontechnical event-listing exclusions. This is a small lexical alternative, not a new list of article-specific exceptions or a meaning-based model.

The [October 6 input](relevance-input-2026-10-06.json) contains all 45 parsed entries in its original coverage window. The [September 30 input](relevance-input-2026-09-30.json) contains 24 older entries assessed retrospectively at the end of their publication date. Both originate from the same October 6 feed capture. Original inputs, feedback, historical filter decisions and link outcomes remain unchanged.

The [October 6 result](final-admission-results-2026-10-06.json) and [September 30 result](final-admission-results-2026-09-30.json) record policy counts, all changed decisions, unresolved wanted misses, input/implementation checksums, profile configuration and keyword list. The comparator reuses existing freshness, clock, identity and feedback validation. It runs without network access and changes no production rule.

## Results

| Saved pool | Candidates | Wanted admitted: current → broader | Unwanted admitted: current → broader | Undecided admitted: current → broader | All admitted: current → broader |
| --- | --- | --- | --- | --- | --- |
| September 30 retrospective | 24 | 7 → 7 | 0 → 0 | 10 → 10 | 17 → 17 |
| October 6 | 45 | 11 → 11 | 0 → 0 | 15 → 16 | 26 → 27 |
| Combined | 69 | 18 → 18 | 0 → 0 | 25 → 26 | 43 → 44 |

There are **18 wanted and two unwanted judgments** across these pools. Both policies admit all 18 wanted articles and reject both unwanted articles. The other 49 candidates have no decided owner inclusion preference; they are not negatives. Counts describe admission among reviewed examples, not report-wide precision or general recall.

The only changed decision is [The Agent Said It Was Done. The Database Disagreed.](https://huggingface.co/blog/microsoft/thinkingbox). The broader rule admits it because “agent” appears in its title. The current title-only check lacks supporting context. It may be valuable AI engineering, but it has not been reviewed; a live feed summary might also provide enough context under the current rule. This is **one potential recovery**, not a confirmed wanted recovery or an unwanted match.

No newly admitted story has a negative owner judgment either. We therefore do not claim that the broader rule is measurably worse. A synthetic regression demonstrates its ambiguity—an insurance-agent headline also passes—but that authored counterexample is kept out of the real-data counts. The unwanted march listing stays excluded under both rules; useful conference coverage stays eligible.

## Filter success is not ranking success

All 18 reviewed wanted articles pass the current filter in these title-only pools. That does **not** mean they appear in the published report or in a good order. Link failures, freshness at another clock, publisher caps and ranking can still prevent selection.

The [separate October 9–10 ranking replay](source-priority.md) already documents that the importance-3 NVIDIA AICR and Green Contexts articles remained outside October 9's selection at raw candidate positions 51 and 54. Reducing the forum-source bonus improved some positions but did not change the selected URL sets. Databricks still outranked the importance-3 PyTorch Dynamo article on October 9. This final admission comparison fixes none of those ranking limitations and does not obscure them with an “18 of 18” quality claim.

The October 11 comparison left article labels from #34 observation-only. Since then, the separately reviewed model-assisted policy has used AI-subject answers for admission and engineering-detail answers for constrained equal-score tie breaking. Article type is not an automatic quality grade or blanket exclusion. Original feed-derived scores and star buckets remain in use. Broader content-sensitive ranking, independent quality measurement and other unfinished ambitions remain optional work in #35.

## Work shipped since this PR opened

- PRs #39–#43 added pre-admission article evidence, a versioned assessment contract and Cloudflare adapter, paired comparisons, and a public evaluation workflow.
- The [October 13](feedback-2026-10-13.md) and [October 14](feedback-2026-10-14.md) owner feedback favored useful model-selected additions. These are development examples, with overlapping stories, not an independent accuracy benchmark.
- PR #45 made the owner-approved decision-model policy the production default, preserving the complete rules fallback, audit records, freshness, publication history and publisher limits.
- PR #46 aligned the serialized request guard with valid multilingual input bounds. Regression tests verify the fix offline; this record does not claim that the next live daily run has confirmed recovery.

These later deliveries supersede the earlier plan to leave all model integration for future work. They do not turn the historical title-only comparison into evidence about the model's accuracy or ranking quality.

## What issue #12 delivered

| Original area | Delivered | Explicitly deferred |
| --- | --- | --- |
| Freshness | Configurable UTC window, unknown/future-date handling, stale diagnostics, no old filler | No additional requirement |
| Content and reading times | Feed content retained; bounded article extraction; provenance and unknown estimates | Representative extractor comparisons |
| Evaluation | Editorial brief/rubric, saved candidates and owner feedback, daily comparisons, historical lexical comparison, paired model reports and audit records | Independent chronological/duplicate-aware evaluation and measured general quality improvement |
| Publication history | Receipts across runs, repeated-link catch-up, previous-report links | Substantive changes at the same URL; optional history index |
| Relevance and ranking | Stable family/version handling, context checks, continuous ordering, reduced forum prior; subsequent model-assisted admission and constrained engineering-detail tie breaking | Broader content-sensitive ranking, baseline bypass removal, demonstrated held-out quality improvement |
| Grouping and diversity | Conservative identical-title grouping, alternate attribution, publisher caps | Broader story grouping and measured diversity alternatives |
| Optional reranker | Model-assisted admission shipped separately; a general reranker was not added | Embeddings, cross-encoder or broader ranking changes only through separately scoped evaluation |

Closing #12 means the owner-agreed incremental delivery is finished and the unresolved ambitions have an explicit home. It does not mark the historical seven-item checklist fully implemented. The original source audit and research remain historical evidence, not descriptions of today's generator.

## Reproduce and verify

Run from the repository root; use temporary outputs so committed evidence is not overwritten:

```bash
python3 -m scripts.compare_final_admission docs/evaluation/relevance-input-2026-09-30.json docs/evaluation/owner-feedback-2026-09-30.json --output /tmp/final-september-30.json
python3 -m scripts.compare_final_admission docs/evaluation/relevance-input-2026-10-06.json docs/evaluation/owner-feedback-2026-10-06.json --output /tmp/final-october-6.json
python3 -m unittest discover -s tests
ruff check scripts tests
ruff format --check scripts tests
```

Implementation checksums identify the code used for this decision. Future code changes may alter them and the replay; the committed results are historical evidence, not files to silently refresh after unrelated changes.

Offline regressions check the exact pool counts and reviewed outcomes, the single undecided addition, preserved event/quiet-day gates, synthetic generic-word ambiguity, unchanged inputs, feedback provenance, CLI output and overwrite protection. The existing report-rendering, history, access and extraction tests remain applicable. Production generator, configuration and workflow behavior are unchanged, so the release appearance is unchanged too. No live feed checks, additional article retrieval, workflow dispatch, release edits or publication are performed by this comparison.
