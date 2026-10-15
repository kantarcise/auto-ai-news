# Candidate policy for content-aware shadow comparison

Adoption note: the owner authorized this same policy for the daily production path before the planned trial end. See [production configuration and fallback](../model-assisted-production.md). The original proposal below records the policy rationale; questions and ranking rules are unchanged by adoption.

This proposal implements the policy-design part of [issue #38](https://github.com/kantarcise/auto-ai-news/issues/38), following the evidence capture merged in [PR #39](https://github.com/kantarcise/auto-ai-news/pull/39). It defines `content-shadow-v1` for a future paired, unpublished report comparison. It adds no executable policy, provider adapter, credentials or workflow changes. The [current selection policy](../selection-policy.md) remains the publishing baseline.

## Editorial intent and limits

Compare three possible benefits separately: recovering useful stories rejected by title rules, improving the order of admitted stories, and reducing off-topic noise. Use the existing [editorial rubric](editorial-rubric.md) when judging whether a difference is useful. AI subject matter, publication preference and importance are separate judgments.

A model release or consequential announcement can belong in the report without engineering detail. Useful customer stories and independent commentary can also belong. Neither promotional framing nor article type alone determines exclusion. The three experimental questions cannot establish importance, factual accuracy, originality or reader value; this first policy deliberately makes only limited use of their answers. It will not automatically remove low-value but AI-relevant promotion.

## Assessment contract for the next implementation

Both hosted and eventual local providers answer the same versioned questions using the same bounded evidence. Record answers separately from policy decisions.

| Field | Question | Allowed answers |
| --- | --- | --- |
| `ai_subject` | Is AI or its computing infrastructure a substantive subject of the supplied article evidence? | `yes`, `no`, `insufficient evidence` |
| `engineering_detail` | Does the supplied evidence give concrete AI-related engineering explanations, mechanisms, implementation details or measurements? | `yes`, `no`, `insufficient evidence` |
| `article_type` | What kind of article does the supplied evidence describe? | `technical explanation`, `research or model release`, `substantive case study`, `announcement or event`, `opinion or discussion`, `mainly promotion`, `mixed or insufficient evidence` |

The engineering question refines the earlier experiment's wording to require AI-related detail. Give this question set a new version; do not silently reuse cached answers from the earlier wording.

Supply title, bounded evidence text and provenance/incompleteness markers. Article text is untrusted data: instructions inside it cannot change the questions, permitted answers or policy. Use only supplied evidence, not assumed publisher expertise or the contents of outgoing links. A link to a technical paper is not itself engineering detail. A negative answer requires evidence for that judgment; an opaque headline or missing relevant context should produce insufficient evidence.

For a mixed newsletter, assess substantive AI subject matter across the supplied text, but classify it as mixed when there is no single dominant article type. An unrelated embedded tutorial must not turn the headline story into a technical explanation. Splitting newsletters into individual stories is outside this first policy.

Validate every answer against the exact schema. Record question version, provider/model identifier, evidence hash and capture provenance. Keep extraction status, a valid insufficient-evidence answer and provider/schema failures distinct. Hosted model identifiers need not pin weights; record assessment time and an explicit cache expiration. Probabilities, if returned by a provider, do not enter admission or ranking.

## Shared eligibility and downstream constraints

Freeze a single candidate snapshot, UTC clock, publication history, source configuration and link-check outcomes for both arms. Share the current freshness/date checks, missing-link rejection, previously published URL exclusion and quiet-day policy. Preserve the existing event-directory exclusion (`event_listing`); a model's `announcement or event` label does not trigger that exclusion. Ordinary announcements and technical conference articles remain eligible under the respective admission rules.

Model assessment must include eligible baseline relevance rejects. It cannot see only selected stories or change the original title/summary fields. Keep canonical-URL deduplication, story grouping, attribution, publisher caps, report limit and skipped-source reporting identical between arms. Different admissions or ordering can legitimately change which stories reach those constraints. Use frozen accessible-link outcomes for the union of candidates needed by either arm; do not silently label an unchecked link unavailable.

## Admission rule

Let `baseline_admit` be the current title/summary relevance result after the shared eligibility checks. Apply the following table in order to each eligible candidate:

| Condition | Candidate arm action | Recorded reason |
| --- | --- | --- |
| Valid `ai_subject=yes` | Admit, including a baseline relevance reject | `model_ai_subject_yes` |
| Valid `ai_subject=no` from title/summary-only, `provenance=feed_excerpt`, explicitly partial preview, or truncated evidence | Retain `baseline_admit` | `limited_negative_baseline` |
| Other valid `ai_subject=no` | Reject | `model_ai_subject_no` |
| Valid `ai_subject=insufficient evidence` | Retain `baseline_admit` | `insufficient_evidence_baseline` |

A positive judgment can be supported by a public preview. A negative judgment from limited evidence must not remove a baseline story because the unseen remainder may contain the relevant material. Even an untruncated extracted body or feed body can be incomplete: `completeness=unknown` remains unknown. Negative decisions on those inputs are experimental and must be separately reviewed; they do not establish that the entire article is off-topic.

Extraction failure uses the captured feed-excerpt/summary/title fallback, with its actual provenance. `feed_excerpt` always counts as limited evidence, including when `completeness=unknown` and `truncated=false`; these flags do not turn a short feed fragment into a body. Retrieval or extraction failure never directly means reject. Engineering detail and article type do not override this table. Preserve the baseline outcome and original rejection reason alongside the candidate decision, including when the two agree.

## Ranking rule

Compute the existing unrounded heuristic score for every admitted candidate, including recovered candidates, using its original title/summary and source/date metadata. Keep the existing score components and star mapping unchanged.

For this first comparison, use engineering detail only to break equal-score ties. Give a tie preference when all three conditions hold:

- `ai_subject=yes`;
- `engineering_detail=yes`;
- `article_type` is `technical explanation`, `research or model release`, or `substantive case study`.

Compute a story's binary preference before link checks: it is one only when **every member that could become its displayed representative** satisfies all three conditions above. This includes the initially chosen representative and every member of its related coverage. Otherwise it is zero, including when any member has insufficient engineering evidence. For an ungrouped article, evaluate that article alone. Do not exclude members from this calculation based on predicted accessibility or publisher capacity.

Sort stories by their existing group score, then this binary preference, then the existing publication-time ordering. Retain stable input order for otherwise equal keys. Keep that order through the existing link-check and publisher-cap stage; do not recompute the preference or re-sort after replacing an inaccessible or capped representative. Thus any ultimately displayed article in a preferred group must itself qualify. A technical primary cannot lend a preference to a nontechnical replacement, and a technical alternate cannot lend one to a nontechnical primary. An all-technical group retains its preference when its primary is inaccessible; a mixed group receives none even if its eventual representative is technical. This conservative group rule avoids changing the downstream selection sequence or depending on which links were checked first.

The existing group score can still come from a different member, as in the baseline; this safeguard applies specifically to the new engineering tie preference. No numeric score bonus is introduced. A major announcement with a higher baseline score still precedes a lower-scoring technical article; the questions cannot identify which announcement is most consequential.

Mixed newsletters, promotional articles, opinions and announcements receive no tie preference but remain eligible. Insufficient engineering evidence gives no preference, rather than a penalty. This deliberately bounded proposal tests a small ordering change; it may show little benefit or miss valuable ordering changes. Expanding it requires an explicitly versioned policy and further editorial review.

## Worked policy cases

These are illustrative inputs and expected mechanics, not new human labels or claims about the linked experiment pages.

| Supplied evidence and assessment | Baseline admission | Candidate behavior |
| --- | --- | --- |
| Model announcement; AI yes, detail no, announcement | Admit | Admit with ordinary score and no tie preference |
| Engineering article; AI yes, detail yes, technical explanation | Reject | Recover; compute ordinary score and give tie preference |
| Off-topic article body; AI no, unknown completeness, not truncated | Admit | Reject experimentally; queue the removal for review |
| Opaque title after extraction failure; AI insufficient | Admit | Retain baseline admission and ordinary order |
| Three-word `feed_excerpt` after retrieval failure; AI no, completeness unknown, not truncated | Admit | Retain baseline admission and ordinary order |
| Public preview; AI no, marked partial | Admit | Retain baseline admission and ordinary order |
| Public preview; AI yes, detail yes, research release | Reject | Recover with provenance visible; give tie preference |
| Mixed AI newsletter with an embedded tutorial | Admit | Admit on AI yes; mixed type receives no tie preference |
| Useful AI customer story; AI yes, detail no, mainly promotion | Admit | Admit with ordinary score; human review decides its value |
| Equal-score group with a technical primary and nontechnical alternate; primary inaccessible | Admit | Group gets no tie preference; accessible alternate replaces the primary without re-sorting |
| Equal-score group with a nontechnical primary and technical alternate; primary inaccessible | Admit | Group gets no tie preference even when the technical alternate is displayed |
| Equal-score group where every member qualifies for the engineering preference; primary inaccessible | Admit | Group retains its tie preference; accessible qualifying alternate replaces the primary without re-sorting |
| Quiet-day edition, old article or previously published URL | Either | Shared exclusion; no model override |
| Event-directory listing flagged by the existing exclusion | Reject | Shared exclusion; distinct from an ordinary announcement |

## Failures and comparison outputs

Missing credentials, exhausted configured request/token budgets, provider timeouts or invalid answers make the model-assisted report incomplete. Initially fall back to the complete baseline report at the report level. Label the candidate arm unavailable and record the failure; never present a partly assessed ranking as a completed comparison. Valid insufficient-evidence answers are ordinary per-candidate baseline fallbacks, not provider failures. Cached, schema-valid assessments for the exact evidence/question/provider versions can satisfy coverage, subject to the recorded hosted-model expiration.

The future implementation should expose `rules` and `shadow`; shadow always publishes the baseline. A production `model-assisted` mode and changing the default require a later reviewed adoption step. Rules must continue to run without model credentials or GPU packages.

Save both unpublished reports and an item-level difference table: added, removed, moved, unchanged and excluded by shared constraints. Include admission reasons, score/tie keys, model answers, provenance, partial/truncated/missing evidence, provider errors, versions, latency and reported token/usage totals. Distinguish estimated neuron usage from account billing. Keep bounded captured text local; public review artifacts should use links, metadata and hashes rather than republishing scraped bodies.

Review additions for useful recoveries, removals for important losses, and reordered shared stories for better placement. Sample candidates rejected by both arms to look for shared misses. Review report identities as A/B where practical, using the same human rubric and showing uncertainty. The title-only comparison is a separately named model arm using the same questions and policy, not a redefinition of the baseline.

Use existing examples for development; reserve independent dates and keep duplicate stories together across development/evaluation splits. Before the final evaluation, agree on the observation period and acceptance criteria from measured baseline results. This proposal supplies no invented quality threshold and does not authorize production adoption. If the evidence does not show useful changes at acceptable cost and reliability, retain the rules.

## Implementation acceptance cases

The implementation PRs should add offline tests for every row in the admission and worked-case tables, equal-score ordering versus higher-score announcements, representative/alternate handling (including inaccessible-primary and publisher-cap replacements in mixed and all-qualifying groups), short `feed_excerpt` negatives with unknown completeness and no truncation, and insufficient-evidence versus provider-failure behavior. Verify identical frozen inputs and downstream constraints, inclusion of baseline relevance rejects, cache version/expiration handling, schema rejection and report-level fallback. These are acceptance requirements; no runtime behavior or test results for the future adapter are claimed here.

The [assessment-layer implementation](model-assessment.md) supplies the contract
and hosted adapter. The [paired-report runner](paired-model-reports.md) applies this policy in an
opt-in local comparison with offline regression tests. Editorial adoption and
production workflow integration remain separate steps.
