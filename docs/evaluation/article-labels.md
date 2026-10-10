# Article evidence review, before changing ranking

Saved comparisons now record provisional content clues from titles, summaries, feed content and already retrieved article bodies. **These clues do not change inclusion, scores, stars, publisher caps, history or daily release Markdown.** No extra requests, LLM or runtime dependencies are added.

A customer story can be both promotional and technically useful. The labeler receives no publisher, category, priority, URL, owner rating or lab-tier information. Promotion and opinion are not exclusion rules.

## Separate, auditable evidence

Version 2 normalizes and bounds **title, summary and content independently**. A nonempty content stub cannot erase an informative summary. Positive label matches from every field are retained with a stable rule ID, field name and fixed human-readable description. Article passages are not copied into label metadata.

| Suggested label | Example rule IDs and clues |
| --- | --- |
| Technical walkthrough | `implementation-guide`, `multiple-technical-signals`: implementation/debugging or multiple distinct technical categories in one non-title field |
| Research / evaluation | `evaluation-language`, `comparative-testing`: evaluation vocabulary or reported testing/comparison of models |
| Model / tool release | `release-announcement`: explicit model/tool release language |
| Practical experience | `deployment-experience`: lessons, deployments or production experience |
| Promotion / testimonial | `customer-promotion`, `sales-demo-invitation`: customer/sponsorship language or a sales invitation |
| Opinion / discussion | `opinion-framing`: explicit opinion or argument framing |
| Event / announcement | `event-invitation`: conference, webinar or registration language |

Each label has its own explanation, independent of technical signals. “Book a demo” therefore explains promotion even when there is no technical evidence. Multiple labels and multiple matching fields can coexist.

Technical signals are deduplicated categories: implementation, configuration/API/cache, measurement, trade-offs/maintenance and meaningful structured code. Repeating configuration in both summary and content still counts as **one** category. Title matches never contribute technical signals.

## Preserve structure through extraction

Feed HTML and downloaded HTML use shared visibility, normalization and meaningful-code checks in `scripts/html_evidence.py`. A code example must contain nonempty code-like material inside `pre`/`code`, within the normalized analyzed window. Navigation, hidden content and other blocked boilerplate do not contribute. Empty and out-of-window code do not count.

The existing body extractor chooses the same article region and returns the same plain text for reading-time callers. Its evidence-aware API also returns bounded structural metadata from that region. Existing retrieval optionally fills that metadata on the selected item, including cached copies, without another request. Labels accept matching-window code metadata alongside flattened text. Only feature metadata reaches saved assessments, never the full body.

The labeler examines at most 24,000 raw characters per field and normalizes at most 12,000 content characters, 4,000 summary characters and 500 title characters. Downloaded structural metadata describes the first 12,000 normalized characters of the chosen region. These windows can omit relevant material. Text is data, never executable instructions.

## Depth remains experimental

The main comparison table shows **technical clues**, not an aggregate depth grade or usefulness rating. For diagnostic compatibility, JSON retains explicitly experimental categories:

- **Uncertain:** fewer than two distinct non-title signal categories. Missing signals do not establish shallowness.
- **Some:** at least two distinct categories across summary/content, deduplicated across fields.
- **Substantial:** content alone supplies at least three categories including implementation or code, with at least 120 analyzed words. Summary-only clues cannot elevate weak content to this category.

These numerical gates are unvalidated heuristics. Long text alone cannot qualify. They must not be interpreted as quality, inclusion preferences or calibrated confidence.

Rules are English word/structure clues, **not semantic understanding**. A promotional claim mentioning benchmarks can still trigger a research clue; the artifact makes that ambiguity inspectable rather than verifying the claim. Comparative-testing language has a separate explanation. Direct negations are ignored, but nuanced negation, quotations, irony and unsupported claims remain difficult.

## Capture and comparison

The existing `--evaluation-excerpts` opt-in enables labels. Metadata-only capture retains its previous scope.

1. Candidate assessments are frozen before body retrieval in `ranking_inputs`, including fresh, linked, non-quiet, non-history entries rejected by relevance. Capture-local IDs preserve duplicate URL occurrences. Earlier freshness/history/quiet-day exclusions are outside this scope.
2. Selected-stage assessments are appended as `selected_article_labels` after existing bounded retrieval, reusing whatever evidence is available. `--no-article-bodies` still disables retrieval. No requests are added. Failed retrieval can leave only feed evidence.

The comparison pairs each candidate assessment with its selected-stage assessment. **Both stages remain visible together**, with provenance, technical clues and label-specific explanations. Added/removed labels and signals are shown and saved in `article_label_reviews`. Changed assessments appear first, then unresolved cases, within a 20-article review limit. Complete data remains in JSON. Older captures without labels or field-specific explanations remain readable.

A teaser may remain unclassified at the feed stage while downloaded content adds implementation, configuration and profiling clues. The table shows that transition instead of silently replacing the teaser assessment. A selected stage need not be a downloaded body; its evidence field states what was actually available.

## Evidence checks and limits

The [five frozen reviewed excerpts](article-label-examples-2026-10-09.json) preserve their original version-1 assessments and append separate version-2 reassessments. Owner include/importance judgments are kept separate from content-type evidence.

The first LessWrong excerpt **does contain comparative-testing evidence**: testing 12 frontier models and measured improvements. Version 1 missed that vocabulary; version 2 records a research/evaluation label and measurement signal. All five still have uncertain aggregate depth. Databricks and PyTorch teasers omit the article details the owner valued, while the other excerpts remain unclassified by these rules. This is retrospective development evidence, not held-out accuracy.

The [representative offline controls](../../tests/fixtures/article-label-evidence.json) cover engineering, benchmarks, marketing only, mixed customer/technical stories, opinion, short releases and missing evidence. Expected content clues and their supporting evidence are stated independently of owner preferences or usefulness grades. **Seven controls are authored synthetic examples; one is an existing inspected feed excerpt.** They test mechanics and expose an ambiguous benchmark claim; they do not establish real-article label accuracy. Additional unseen article examples have not been evaluated. Reserve future normal captures for independent inspection without tuning against every example.

Tests also cover identical feed/downloaded code evidence, stub/summary retention, signal deduplication, title-only vocabulary, label explanations without depth, body retrieval/cache metadata, paired stage differences, unchanged selection/request counts, no full-body export, historical compatibility and Markdown escaping.

This remains observation-only groundwork for issue #12 items 3 and 5. Normal daily captures can supply the next independent evidence; no publication or historical release changes are triggered by this PR. Article-level checks are still required before using labels or experimental depth categories to change ranking.
