# Best-effort article labels, before changing ranking

The ranking system currently sees source preferences, dates, keywords and topic matches. It does not distinguish a technical walkthrough from a customer pitch. This PR adds provisional content labels and an estimate of technical depth to saved daily comparisons. **Labels do not change inclusion, scores, stars, publisher caps, article history or release Markdown.** No filtering is activated.

A customer story with implementation details can be **promotion / testimonial + technical walkthrough + practical experience**. A forum post can be a technical walkthrough too; the labeler receives no publisher, category, priority, URL or lab-tier information. Neither “promotion” nor “opinion” means “exclude.”

## First version

| Suggested label | Positive clues in available text |
| --- | --- |
| Technical walkthrough | Walkthrough/implementation/debugging language, or several distinct technical signals |
| Research / evaluation | Experiments, methodology, evaluations, benchmarks or ablations |
| Model / tool release | Introducing, new model/tool, release notes or explicit release language |
| Practical experience | Lessons learned, deployments, migrations or production experience |
| Promotion / testimonial | Customer stories, testimonials, sponsorship, sales/demo language or partnership |
| Opinion / discussion | Explicit opinion, discussion or argument framing |
| Event / announcement | Conference, webinar, meetup, registration or call for papers |

Each assessment records algorithm version/method, multiple suggested labels, technical depth, evidence type, analyzed character count, truncation, matched signal categories and short reasons. Reasons name fixed signal categories rather than copying article passages. All assessments are marked provisional. No probability or calibrated confidence is invented.

Technical depth describes **only the available text**, not the full article or its usefulness:

- **Uncertain:** fewer than two independent positive technical signal categories. Title keywords alone cannot establish depth. Missing evidence is not called shallow, and this first version never assigns “little” based on absent words.
- **Some:** at least two categories among implementation, configuration/API/cache details, measurement/evaluation, trade-offs/maintenance and structured nonempty code examples. A summary can provide positive clues, but this does not establish whole-article depth.
- **Substantial:** feed content or an extracted body with at least three categories, including implementation or a code example, and at least 120 available words. This minimum is a conservative evidence gate, not a word-count quality grade or article-length exclusion. Long text alone cannot qualify. The numerical gates are initial heuristics, not tuned or validated constants.

Rules are English lexical/structure clues, **not semantic understanding**. For example, a vendor can mention benchmarks without presenting a useful evaluation. Basic directly preceding negations are ignored, but quotation, irony, nuanced negation and unsupported claims remain difficult. Technical vocabulary may create false positives; sparse teasers or unfamiliar language may create false negatives. No label verifies factual claims or usefulness. Feedback and later article-level checks are required before using these labels for ranking.

## Evidence and capture

The existing `--evaluation-excerpts` opt-in also enables labels. Without it, metadata-only capture keeps its prior scope and does not emit label annotations. There are two separate evidence stages:

1. **Candidate assessments:** fresh, linked, non-quiet, non-history entries reaching relevance receive a label assessment in their `ranking_inputs` row, including candidates the relevance check rejects. Feed content takes precedence over summaries; otherwise the summary or title is used. Candidates excluded earlier by freshness, missing URLs, quiet-day policy or history are outside this labeling scope. Capture-local identities preserve duplicate URL occurrences.
2. **Selected-article annotations:** after existing bounded body retrieval, selected articles receive separate `selected_article_labels` assessments using whatever text is already available. The labeler adds **no feed, access or body requests**. Articles without fetched bodies may still have only summary/title evidence. `--no-article-bodies` continues to disable retrieval. Feed content and extracted bodies can be incomplete; neither is described as guaranteed full-article text.

The initial capture and all ranking features remain frozen before body retrieval. After enrichment, only the selected-article label metadata is added to the same capture file. Article text is not serialized by the labeler. The existing bounded summary-excerpt opt-in is unchanged. Historical snapshots and saved judgments are not rewritten.

The parser examines at most 24,000 raw characters per text field and normalizes at most 12,000 content characters or 4,000 summary characters, with titles capped at 500. Executable/navigation HTML is ignored. Only nonempty structured code within the analyzed content region contributes a code signal. Text is treated as data; it is never executed or followed as instructions.

## What appears in the comparison

The saved `comparison.md` gains a **Best-effort article labels — no ranking effect** table with article links, suggested labels, technical depth, evidence and reasons. It shows up to 20 assessments, selected articles first, preferring their post-enrichment annotations over the earlier feed assessment. Complete candidate assessments and separate selected-article annotations remain in `comparison.json`. Selected annotations must reference unique actually selected URLs. Old captures remain readable and explicitly say labels were not captured.

This first display is a review aid, not a new published report section or an ordering proposal. The daily workflow already captures excerpts and runs the comparison, so no new workflow step is required. Future normal runs get labels after merge; no run or publication is triggered by this PR.

## Check against existing feedback

[Five frozen examples](article-label-examples-2026-10-09.json) retain only the existing saved feed-summary excerpts (at most 1,000 characters), source attribution, owner inclusion/importance and the resulting assessment. They come from the first five reviewed October 9 selections, and were visible during development. They are diagnostics, not held-out label accuracy measurements.

**All five excerpts leave technical depth uncertain, and no content-type label is suggested by the current rules.** In particular:

- Databricks' 83-character teaser does not establish whether the article is mainly promotion, even though the owner read it that way.
- PyTorch's 295-character teaser does not contain the routing/cache details the owner valued. Its importance-3 rating cannot be inferred from that teaser.
- The LessWrong excerpts do not establish technical depth from the available signal categories. They are not labeled opinion merely because they came from a forum, and the rejected treaty article is not excluded by these labels.

This demonstrates why the selected-body reuse stage matters and why “uncertain” must not become a rejection rule. The owner's separate Dynamo passage mentioning routing and KV cache details yields technical-walkthrough/some clues in the regression test, while a synthetic mixed customer story retains both promotional and technical labels. Neither example is a new independent human judgment of the labels.

Next, inspect labels from normal daily runs, especially disagreements between summary evidence and extracted-body evidence, useful promotional/forum articles, and technical articles still unclassified. Keep labels in observation mode until article-level review shows whether they help. No extra owner review batch is required to merge the capture mechanics.

## Verification and roadmap

Offline tests cover mixed promotion/technical content, difficult infrastructure details, title-only/empty/long evidence, direct negation, ignored scripts/navigation, nonempty code and truncation, admitted and relevance-rejected candidates, unchanged selection/request counts, existing body reuse, no copied body text, old-capture compatibility, invalid selected annotation URLs and Markdown escaping. All existing ranking, history, freshness, access, body and renderer regressions continue to run.

This contributes diagnostic evidence to #12 item 3 and groundwork for item 5. It does not complete either, activate a new ranker, add dependencies, call an LLM or replace the remaining semantic comparison.
