# Editorial evaluation baseline

This first batch contains all 34 candidates from the frozen October 3 comparison, including selected and unselected candidates. Labels are deliberately blank. It is a pilot review, not a multi-day or representative quality benchmark. Articles rejected before this captured candidate stage are absent; it cannot measure those relevance/collection misses.

## Editorial brief

Prioritize substantive model/capability releases, research with concrete findings or evaluations, and useful AI engineering with reproducible methods. Include independent analysis that adds evidence or insight. Cover general-purpose models and specialist visual/spatial models across regions. Assess the article, not just its publisher; frontier-lab marketing is not automatically important. Deprioritize corporate/customer promotions, generic advice, unsupported claims and repeated summaries that add little.

The 72-hour window is an operational eligibility rule. Assess relevance/value separately; a valuable blocked article is not an irrelevant article. Do not treat star ratings or the new classifier as human labels.

## Review each candidate

Use the [article-level editorial rubric](editorial-rubric.md) for importance anchors, technical substance, firsthand experience, promotion, readable access and shared-story judgments. It refines the brief using the October 4 feedback without assigning labels on the owner's behalf. The [first omitted-candidate queue](omitted-review-batch.md) gives a five-item starting point from the frozen October 3 pool; enter its judgments in the full sheet below.

Browse the [linked candidate list](review-batch.md), open each article and record the evidence you could inspect. Only links and metadata are included; no article body is republished. Edit [review-2026-10-03.json](review-2026-10-03.json), keeping candidate IDs/URLs intact, and set `reviewer` to your name or chosen identifier.

| Field | Values and meaning |
| --- | --- |
| relevant | `yes`, `no`, `unsure`, or `null` (unreviewed): fits the AI editorial brief |
| include | `yes`, `no`, `unsure`, or `null`: worth including before redundancy/diversity selection |
| importance | 0: little value; 1: useful niche material; 2: significant development/analysis; 3: essential coverage; `null`: not judged |
| story_id | A short identifier shared by articles about the same event; included articles require one |
| evidence | `article`: inspected substantive text; `title`: provisional headline judgment; `unavailable`: evidence could not be inspected; `null`: unreviewed |
| notes | Explain the judgment, uncertainty, or what additional analysis distinguishes duplicate coverage |

An included item must be relevant, have importance 1–3 and a story ID. Unavailable evidence requires `unsure` or an unreviewed inclusion label. Disagreement/uncertainty is a useful result, not something to force into a negative label. Scores and policy selections are omitted from the review sheet to avoid anchoring judgments to current ranking. Publisher identity remains visible for attribution.

## Run offline

```bash
python3 -m scripts.review_candidates evaluate docs/frontier-selection-comparison-2026-10-03.json docs/evaluation/review-2026-10-03.json
```

The evaluator validates snapshot/URL identity, complete row coverage and label consistency. It reports label coverage alongside precision among reviewed selections and recall of reviewed include-worthy candidates. Unreviewed/unsure items are never treated as negative; absent denominators produce `null`, not a zero quality score. Recall covers this captured candidate pool, including operationally blocked candidates, not the universe of AI news. On partial reviews, numbers may be biased toward whichever items were reviewed first. Title-only judgments are provisional; metrics are judgments of this reviewer, not fact verification.

To recreate a blank review sheet in a separate file:

```bash
python3 -m scripts.review_candidates prepare docs/frontier-selection-comparison-2026-10-03.json --output /tmp/ai-news-review.json
```

## October 4 release feedback

The owner has reviewed all 21 selected articles in the latest release. [Recorded preferences and limitations](feedback-2026-10-04.md) distinguish firsthand experience, technical substance, useful vendor updates, promotional concerns, access concerns and an explicit AstaBrief duplicate group. These qualitative notes are separate from the blank October 3 batch; no numeric or binary labels are inferred.

## Next evaluation steps

The [topic-profile implementation](adaptive-relevance.md) revises PR #27 to match future model versions and compare headlines/summaries with editorial descriptions, using fresh-pool word weights for relevance and a bounded ranking component. On the same development reviews it admits all 18 wanted articles and excludes both unwanted articles, while adding one unreviewed robotics title. These results are not an independent test or measured ranking-quality gain. The [earlier title-only comparison](apply-reviewed-topics.md) remains historical evidence; its older-date assessment is not a historical report replay.

The [October 6 offline comparison](relevance-comparison-2026-10-06.md) tests extra model/framework/GPU/vector-search title matches against saved gate outcomes and the owner's twelve preferences. It recovers four wanted title-filter misses; the owner subsequently read and approved all four additional matches. Both checks still admit the unwanted event listing. These are same-day development examples, not measured production-quality gains. Test on separate dates and review more negative examples before changing the daily rule.

For new dates, use the [optional broader capture](capture.md) to retain parsed entries rejected before ranking alongside selected stories, source diagnostics and actual link-check outcomes. The existing October 3 snapshot remains unchanged. Broader-pool recall includes operationally ineligible positives and must be distinguished from the older eligible-pool metrics.

The owner has supplied [qualitative feedback on all five omitted candidates](omitted-feedback-2026-10-05.json). The rubric now reflects useful testimonials, frontier-lab practitioner perspectives and tentative lower priority for brief announcements. Explicit inclusion decisions and importance grades remain outstanding; the scored sheet is still unreviewed, so the evaluator reports no quality scores.

Review this pilot and refine the rubric, then capture multiple dates including rejected candidates and representative regions/modalities. Freeze each snapshot's clock and operational outcomes. Group duplicate stories before chronological train/test splits, retain an unseen-publisher check, and measure important-story recall, graded ranking, repetition and concentration. Set acceptance targets from labeled baseline results. This pilot adds no runtime dependencies and changes no production ranking, workflow or releases.
