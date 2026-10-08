# Topic profiles and future model versions

This revises PR #27 for issue #12: the daily generator compares headlines and feed summaries with short descriptions of the news the owner values. It uses the resulting score for both relevance admission and ranking. The earlier title-only additions are preserved as an offline comparison, not the production implementation.

## What changes

Known families live in [config/editorial_profiles.json](../../config/editorial_profiles.json), separately from release numbers. A family such as Qwen matches Qwen99.17 without a code or configuration edit. Whole-name boundaries prevent matches like `Qwen99foo`. New families still need an editorial configuration entry; the generator does not discover or verify unknown models. Ambiguous names such as Seed, Nova, Muse and Inkling need a version number or explicit AI/model context.

The configuration also describes five interests: model releases/research, GPU/framework engineering, speech/evaluation, robotics, and retrieval/agent systems. They are editorial choices derived from the owner's feedback, not a claim to understand all AI news. The supplied lab tier list informs coverage preferences; it does not set automatic importance grades.

Word weights adapt to each collection's fresh candidate pool. A word appearing in many articles receives less weight than a rarer word. Repeated words have capped influence. Each URL contributes once to document frequency, including a union of terms from duplicate feed occurrences. Titles and summaries are bounded to 4,000 characters each. A summary can strengthen a match, but an article needs a topic anchor in its headline; summaries alone cannot admit gardening or other unrelated headlines. The stronger of headline-only and headline-plus-summary evidence is used, so a long summary cannot erase a useful headline. Known family matches always pass relevance.

Implementation uses log term weights, smoothed inverse document frequency and cosine similarity, following the standard vector-space approach described in [Stanford's Introduction to Information Retrieval, chapter 6](https://nlp.stanford.edu/IR-book/pdf/06vect.pdf). This is adaptive lexical matching, not semantic understanding, model training or an LLM call. The descriptions remain editable editorial input.

A similarity of at least 0.04 admits a topic match. It adds `min(1, 2 * similarity)` points to the existing continuous score, before stars are assigned. The threshold and bonus are explicit development choices, selected with these reviews available; they have not been optimized or independently validated. Existing generic title keywords and the Latent Space/smol.ai bypass remain fallbacks. Event-directory URLs without a technical topic are rejected, including the march listing; technical conference guides can qualify. The classifier's existing lab bonus, source priorities, publisher caps, grouping and access checks remain in place.

All scoring happens after the same inclusive 72-hour date and quiet-day checks, before grouping and link selection. This adds no requests or runtime dependencies. The evaluation capture records the matched topic, profile terms, similarity and bonus; it does not copy summaries or article bodies.

## Comparison with the earlier checks

The [October 6 results](editorial-results-2026-10-06.json) and [September 30 results](editorial-results-2026-09-30.json) replay the same frozen pools and feedback. The latter is a retrospective assessment of September 30 entries captured on October 6, as documented in [the original comparison](apply-reviewed-topics.md). Both original static comparison outputs remain unchanged.

| Check | Wanted articles admitted, out of 18 reviewed | Unwanted articles admitted, out of 2 reviewed |
| --- | --- | --- |
| Original title check | 5 | 1 |
| Earlier title-word additions | 16 | 1 |
| Topic profiles and family normalization | 18 | 0 |

The two newly recovered wanted stories are the Open TTS Leaderboard (importance 2) and Anthropic robotics research (3). The unwanted march listing is excluded; the space-weather article stays excluded. The PyTorch conference guide stays eligible at the owner's importance 1. Those importance labels are feedback, not runtime scores.

There is also **one newly admitted unreviewed title** beyond the earlier alternative: “California crashes robot fight club” from The Rundown AI. It matches robotics but may have little technical substance. It is an unresolved false-positive risk, not a success. The first pool now admits 27 articles, including 16 unreviewed; the second admits 17, including 10 unreviewed. Admission does not guarantee final report placement or accessible links.

These 20 judgments were purposefully selected, and the new profiles were developed after seeing them. The results are development-set evidence, not an independent test or measured overall precision. Frozen captures lack summaries and source priorities; replay therefore uses titles only. It shows admission decisions and new score components, without inventing historical full rankings, link checks or report selections. Controlled offline regression tests demonstrate that the new bonus can change ordering, but **improved ranking quality has not been measured**. A broad unseen pool with negative examples is needed to establish that.

To reproduce without network access:

```bash
python3 -m scripts.compare_editorial docs/evaluation/relevance-input-2026-10-06.json docs/evaluation/owner-feedback-2026-10-06.json --output /tmp/editorial-october-6.json
python3 -m scripts.compare_editorial docs/evaluation/relevance-input-2026-09-30.json docs/evaluation/owner-feedback-2026-09-30.json --output /tmp/editorial-september-30.json
```

Each output contains the exact profile configuration and input hashes, per-title explanations, all unreviewed matches, and original actual selections/link outcomes. User feedback and old snapshots are not rewritten.

## Verification and limits

Regression tests exercise unseen version numbers and a new configured family, ambiguous names, word boundaries, summary-only false positives, evolving pool weights, duplicate/order stability, bounded bonuses and changed ordering, complete collection integration, stale rejection, event/conference distinction, deterministic replay and feedback provenance. The existing Markdown escaping, missing dates, empty-report, source-diagnostic, access-fallback and publisher-cap tests also run.

Remaining limitations include synonym misses, false matches on generic technical words, English-focused tokenization, evolving per-pool scores, short headlines with little context, and the existing publisher bypass. Runtime stars are heuristic ranking buckets, not editorial-quality judgments. This is a substantive relevance/ranking implementation step within issue #12; it does not finish the whole issue. No release publication or live-feed quality validation was performed for this change.
