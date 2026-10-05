# First omitted-candidate review queue

This queue contains all five URLs in `policies.frontier.candidates` absent from `policies.frontier.selected` in the [October 3 frozen snapshot](../frontier-selection-comparison-2026-10-03.json). The snapshot clock is `2026-10-03T16:53:17.216262+00:00`, with a 72-hour eligibility window. This is an October 3 candidate review, not a reconstruction of the October 4 release reviewed by the owner.

Use the [article-level rubric](editorial-rubric.md) and enter judgments in the existing [34-row JSON sheet](review-2026-10-03.json), matching the IDs below. Set `reviewer` to your chosen identifier and keep every row. This queue supplies no inferred inclusion, relevance, importance, or story labels. Its omission-focused sampling is deliberately biased; it is not a representative quality benchmark.

## Review links

Assess the article before consulting the operational outcomes below. Queue membership itself reveals that the frontier policy omitted the article; this is not a blinded review. The [full review batch](review-batch.md) omits selection outcomes and scores for broader review.

| Candidate ID | Article | Source | Published (UTC) |
| --- | --- | --- | --- |
| c38af6e5cae43e23 | [A model guide for the GPT\-6 family](https://openai.com/index/practical-guide-building-gpt-6) | OpenAI | 2026-10-02T16:15:00+00:00 |
| 882596cbc7639eb4 | [Chatham scales its capital markets expertise with OpenAI](https://openai.com/index/chatham-financial) | OpenAI | 2026-10-02T00:00:00+00:00 |
| 2167384f51e2a446 | [The Den frees up 10\-15 hours a week to grow with ChatGPT Work](https://openai.com/index/the-den-family-social) | OpenAI | 2026-10-01T00:00:00+00:00 |
| cfe32cdb08fcc91a | [Why Dwarkesh is Wrong about Computer Use \+ How OpenAI shipped its Jev competitor in 1 Week](https://www.latent.space/p/devday-2026) | Latent Space | 2026-09-30T22:23:40+00:00 |
| 1e8ed424c4f3832a | [AI Gateway adds Browserbase Search and Fetch tools](https://vercel.com/changelog/ai-gateway-adds-browserbase-search-and-fetch-tools) | Vercel | 2026-09-30T21:00:00+00:00 |

## Frozen operational outcomes

The saved frontier diagnostics attribute the Latent Space and Vercel omissions to the four-article publisher cap. All three OpenAI URLs returned HTTP 403 in the saved link checks. These reasons describe collection/selection behavior, not editorial value. The two capped articles were selected by the saved baseline; the three blocked articles were selected by neither policy.

A later readable page may support a new article-level judgment; record when and what you inspected while retaining the historical link outcome. If the text remains unavailable, leave inclusion `unsure` or `null`, with `evidence=unavailable`. Do not label a blocked article irrelevant merely because it failed retrieval.

The captured pool excludes articles rejected before the candidate stage. Source-level diagnostics record freshness and other failures, but do not supply a complete article-level review queue for those rejects. A subsequent capture must retain that metadata to evaluate relevance-filter and ingestion misses.

## Owner feedback received October 5

[Structured qualitative feedback](omitted-feedback-2026-10-05.json) records the owner's response on all five links: strong praise for the technical model guide and frontier-lab practitioner discussion, appreciation of useful promotional/testimonial content, and tentative lower priority for the short Vercel announcement. Snapshot URLs and submitted feedback URLs are both retained, including trailing-slash differences; redirect/canonical equivalence was not independently checked.

This completes qualitative feedback collection for this queue. It does not complete scored labeling: the owner supplied no explicit binary inclusion decisions or numeric importance grades. Those fields remain null in the feedback record and the full review sheet. Owner-reported article observations remain separate from independent inspection and do not change the historical HTTP 403 outcomes. Next, agree on inclusion decisions and importance grades, then review selected candidates with the same rubric before reporting quality metrics.

## Validate partial labels offline

```bash
python3 -m scripts.review_candidates evaluate docs/frontier-selection-comparison-2026-10-03.json docs/evaluation/review-2026-10-03.json
```

The evaluator requires the complete sheet; do not create a five-row replacement. Unreviewed and unsure labels are not negatives. With only this queue reviewed, selected-article coverage will be incomplete and precision may be undefined. Report counts and coverage alongside results, and interpret recall only within the reviewed captured candidates. No comparison of current story grouping or body extraction follows from this older snapshot, which predates both changes.
