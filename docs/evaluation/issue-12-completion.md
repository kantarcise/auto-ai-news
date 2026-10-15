# Finish issue #12: final filter comparison and scope boundary

**Decision: keep the current production filter.** Relaxing generic keyword checks recovers no additional article the owner has marked wanted in the saved reviews. It adds one unreviewed engineering-looking headline, whose usefulness remains undecided. That is insufficient evidence to ship another filter change.

This finishes the agreed bounded work on [issue #12](https://github.com/kantarcise/auto-ai-news/issues/12). It does not mean every original research proposal was implemented. The remaining ambitions are explicitly deferred to [optional follow-up #35](https://github.com/kantarcise/auto-ai-news/issues/35), rather than conditions for closing #12. No new article-rating batch is required for this decision.

## What was compared

Both policies use the same saved candidates and owner feedback:

- **Current:** today's topic/model-family/context rules, generic keyword fallback and existing source bypasses, replayed on titles only.
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

Article labels from #34 remain observation-only. Their correctness, content-sensitive ranking, semantic alternatives and unconditional publisher admission are future optional work in #35. None is silently enabled here.

## What issue #12 delivered

| Original area | Delivered | Explicitly deferred |
| --- | --- | --- |
| Freshness | Configurable UTC window, unknown/future-date handling, stale diagnostics, no old filler | No additional requirement |
| Content and reading times | Feed content retained; bounded article extraction; provenance and unknown estimates | Representative extractor comparisons |
| Evaluation | Editorial brief/rubric, saved candidates and owner feedback, daily comparisons, final lexical decision, auditable experimental labels | Independent chronological/duplicate-aware evaluation and semantic comparison |
| Publication history | Receipts across runs, repeated-link catch-up, previous-report links | Substantive changes at the same URL; optional history index |
| Relevance and ranking | Stable family/version handling, context checks, continuous ordering, reduced forum prior | Content-sensitive ranking, bypass removal, demonstrated held-out quality improvement |
| Grouping and diversity | Conservative identical-title grouping, alternate attribution, publisher caps | Broader story grouping and measured diversity alternatives |
| Optional reranker | Deferred rather than added without evidence | Embeddings/cross-encoder/LLM decision only if a separately scoped experiment justifies it |

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
