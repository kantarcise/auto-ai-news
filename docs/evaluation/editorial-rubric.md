# Article-level editorial review rubric

This refinement uses the owner's [October 4 feedback](feedback-2026-10-04.md) and [October 5 omitted-candidate feedback](omitted-feedback-2026-10-05.json) to guide the human-review pilot for issue #12. It does not convert those qualitative notes into scored labels. Use the existing fields and validation rules in the [evaluation guide](README.md); assess each article before checking its saved selection outcome or ranking.

## Inclusion and importance

First decide whether the article fits the AI editorial brief (`relevant`). Then decide whether it offers enough reader value to include (`include`) before redundancy and publisher balancing. An AI-relevant customer story can still lack useful substance. A valuable article blocked by the collector can still deserve inclusion if the reviewer can inspect it through ordinary public access.

| Importance | Anchor for the judgment |
| --- | --- |
| 0 | Little useful contribution: generic advice, unsupported assertions, or promotion without concrete lessons. |
| 1 | Useful niche material: a practical API change, specific implementation lesson, or firsthand account with actionable observations. |
| 2 | Significant development or analysis: substantial findings, detailed engineering tradeoffs, or evidence that changes how readers understand a capability or practice. |
| 3 | Essential coverage: a major capability/research development or unusually consequential, well-supported analysis for this editorial brief. Explain why it deserves this grade. |

These anchors guide judgment; they are not keyword rules. Length, lab membership, publisher reputation, and the report's stars do not determine importance. Short announcements can be valuable. Do not force mixed feedback such as "fine" into a particular grade or inclusion decision. Use `unsure` when the evidence does not support a decision.

## What to look for in the article

| Dimension | Evidence to record in `notes` |
| --- | --- |
| Technical substance | Concrete methods, implementation details, evaluations, reproducible resources, constraints, or tradeoffs. Explain what the reader learns; a code link alone is insufficient. |
| Firsthand experience | What the author actually did or observed, lessons learned, and limits of the experience. Bootcamp and practice accounts can qualify without a model launch. |
| Frontier-lab practitioner perspective | The owner values statements from people close to frontier-lab work. Record the attributed speaker, their role where supported, and what insight they contribute. This preference applies to interviews or commentary in other publications too; proximity does not itself verify claims or establish an importance grade. |
| Useful product/API update | What changed and what it enables, including limitations or usage details. Vendor publication is not itself a negative. |
| Promotional framing | Whether customer praise, sales claims, or generic advice dominate without adding evidence or practical lessons. Weigh substance alongside framing rather than rejecting all corporate posts. |
| Testimonials and presentation | The owner can value a well-produced testimonial, including useful information in promotional material. Record concrete reader value separately from presentation quality; neither customer-story format nor polished design settles inclusion. |
| Synthesis or independent analysis | What evidence, comparison, or interpretation the article adds. A useful roundup can qualify; identify the substantive section when it mixes topics. |
| Readable access | What text the reviewer could inspect: substantive article, excerpt, subscription gate, sign-in gate, or unavailable page. Record the review date in UTC and any uncertainty. HTTP success and a reading-time estimate do not prove full-text access. |

The owner's positive examples include bootcamp experience posts, Airbnb's engineering account, AutoSynthData, the technical Databricks retail article, and Cloudflare API/workspace updates. NVIDIA samples/skills posts, Genie Agents advice, and the Vercel customer story prompted promotional concerns. These examples calibrate discussion; they are not automatic labels for other articles from those publishers.

The October 5 feedback adds positive examples: the OpenAI model guide's short summary followed by extensive technical detail; useful information in the promotional Chatham story; the quality of The Den testimonial; and OpenAI practitioner content in the Latent Space article. The brief Vercel announcement received a tentative lower-priority assessment. Consider how much a short update contributes when comparing priority, but do not impose a word-count or one-minute-read exclusion. The reported page length and contributor affiliations are owner observations, not independently verified facts.

The October 10 feedback on the first five October 9 selections expresses a smaller prior for LessWrong as a community forum than for strong research/engineering sources, especially frontier labs. Useful forum posts remain eligible. The owner rated two forum posts 1, rejected the treaty post, rated the promotional Databricks article 1 and the technical PyTorch/Dynamo article 3. Difficulty alone is not a rejection rule: challenging infrastructure details were explicitly valued. These are targeted labels used to design a source-priority adjustment, not independent validation of it; see [the recorded feedback](release-feedback-2026-10-09.json).

## Evidence, access, and shared stories

Use `evidence=article` only after inspecting substantive article text. A headline-only judgment uses `title` and remains provisional. An inaccessible page uses `unavailable` with an unsure or unreviewed inclusion label. If only an excerpt is visible, describe that limit and leave inclusion unsure when it is insufficient. Do not bypass access controls. A historical HTTP 403 is a collector outcome at the frozen clock, not proof of a permanent paywall; current browser access cannot rewrite that outcome.

Give included articles a `story_id`. Use the same ID for coverage of the same event, including the owner's explicit AI2/Hugging Face AstaBrief pair. Inclusion is judged before redundancy: two useful accounts can both receive `include=yes`, while notes distinguish a repeated announcement from independent analysis that adds substance. Same-story labels do not imply identical value. A substantive update should explain what changed.

Suggested notes structure (plain text; no new JSON fields):

```text
Reviewed at (UTC): ...; inspected: article / excerpt / headline / unavailable.
Value: ...; substance: ...; promotional concerns: ...
Access limits: ...; same-story relationship / added analysis: ...
Decision rationale or unresolved question: ...
```

## First review and decision gate

Start with the [five omitted candidates](omitted-review-batch.md), entering labels in the existing full 34-row sheet. Keep all other rows intact and unreviewed until inspected. Then review selected candidates with the same rubric to make a comparison possible. Keep owner feedback provenance separate from new article inspections.

Run the offline evaluator after labeling and report its coverage with every metric. A five-item omission review alone cannot establish overall precision or justify new ranking weights. Document disagreements, unavailable evidence, and possible missed stories before proposing a production change. Later snapshots must include candidates rejected before ranking and multiple dates/regions/modalities; this pilot cannot measure those collection or relevance misses.
