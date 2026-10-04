# Frontier announcement selection

The registry in `config/sources.json` assigns source category, publisher identity, and coverage channel. Frontier membership is an editorial coverage choice, not a benchmark ranking. The same publisher can have multiple source channels (Anthropic News and Research); the cap applies to their combined selection. Engineering/commentary/research categories remain useful and receive the ordinary score.

## Eligibility and classification

The existing 72-hour inclusive UTC cutoff, missing/future-date exclusions, quiet-day title policy, AI title relevance and canonical-URL deduplication still apply. The existing Latent Space/smol.ai relevance bypass is unchanged in this step and remains evaluation work.

Only an eligible `frontier_lab` item can earn the additional preference. Headline classification excludes common marketing terms (customer/case study, funding, partnerships, pricing, hiring and conferences). Research-channel items and research/evaluation/interpretability/world-model headlines can qualify as `lab_research`. Model-topic/brand headlines beginning with introducing/announcing/releasing/unveiling, or numbered model-brand headlines, can qualify as `lab_announcement`.

These are conservative lexical rules, not content understanding. They can miss legitimate model releases, mistake a tangential headline for research, and exclude valuable partnership announcements. Ordinary AI-relevant lab posts still compete without a lab bonus. A headline label does not verify the publisher's claims. No lab receives automatic five-star ratings or a freshness exception.

## Ranking and selection

| Component | Points |
| --- | --- |
| Base | 1 |
| Source priority >=5 | +1.25 |
| Source priority 3–4 | +1 |
| Existing title/summary keyword score >=3 | +1 |
| Publication within 24 hours | +1 |
| Qualifying frontier research/model announcement | +0.75 |

The old priority-5 bonus was +2. Reducing that advantage to 0.25 over priority 3–4 lets a qualifying lab item outrank a generic priority-5 item with otherwise equal components. The selected bonus is bounded; a strong recent engineering or independent-analysis article can still beat an older lab announcement. This retains the existing keyword and 24-hour components rather than introducing an untested semantic model.

Sort by the unrounded score, then publication timestamp. Map stars afterward using `ceil(score)`, clamped to 1–5. Stars are heuristic rank buckets, not verified quality or importance. A legacy seven-day scoring penalty remains for direct scoring callers; the collection cutoff removes such items beforehand.

Check candidate links in rank order. Only successful links consume publisher slots. Select at most four accessible story headlines per representative publisher and at most 30 overall; skip additional publisher entries before making their link requests. There is no quota requiring a lab to appear and no old-story backfill. Shared channels cannot evade the cap. Publisher-cap exclusions and unexamined lower-ranked candidates after the report limit are disclosed separately from network/freshness failures.

## Evaluation and remaining work

The 0.75 bonus and four-article cap are initial transparent heuristics, not optimized constants. Offline examples cover lab-versus-commentary competition, marketing negatives, visual/spatial/general-purpose announcements, shared channels, failed links, and unchanged freshness. Compare both policies using one cached set of feed responses and article-link outcomes at one UTC instant. Saved comparison records contain selected/candidate metadata, not copied article bodies.

A one-day comparison establishes mechanics and publisher concentration, not editorial precision or important-story recall. A human-labeled, chronological benchmark is still needed before tuning weights confidently. Story grouping, substantive-update detection, replacement of unconditional relevance admission, full per-lab funnel reporting, and dated Z.ai/Kimi collection remain separate issue #17/#12 steps.

## October 3 captured comparison

[Saved candidate/selection metadata and cached link outcomes](frontier-selection-comparison-2026-10-03.json) use identical candidate URLs for both policies. Replay without any network requests:

```bash
python3 -m scripts.evaluate_selection docs/frontier-selection-comparison-2026-10-03.json
```

| Measure | Baseline | Proposed policy |
| --- | --- | --- |
| Selected articles | 30 | 29 |
| Publishers | 11 | 11 |
| Maximum from one publisher | 5 | 4 |
| Selected frontier-lab articles | 3 | 3 |
| Anthropic “Claude-shaped science” position | 24 | 7 |

The research article gains placement, while the two corporate lab posts receive no announcement bonus. Latent Space and Vercel each fall from five selections to four; NVIDIA gains an eligible engineering item. The empty thirtieth slot is not filled with older or excess-publisher content. Most registered labs had no eligible recent candidates, and OpenAI links were blocked; this policy cannot solve those collection gaps. No claim of measured editorial-quality improvement follows from this snapshot alone.

## Conservative shared-announcement grouping

After URL deduplication and freshness/relevance checks, detailed normalized titles (at least six tokens) published within 24 hours can form one story. Normalization handles case, Unicode compatibility and ordinary punctuation, while preserving version numbers and C++/C# distinctions. Every member must be within 24 hours of every other member; chains cannot bridge a wider time span. Unknown dates do not group. Differently titled analysis remains separate. Identical titles are evidence, not a semantic guarantee; generic same-title cases remain a limitation.

Prefer a research/frontier-lab source as the representative when available, then its rank. This is a source-category heuristic, not proof of original authorship. Group ordering uses the highest member score, so alternate publication does not artificially increase ranking. Check the representative and alternates, disclose failures, and fall back to a checked accessible member if necessary. Render one headline plus alternate source links; preserve the representative's own rating/date/read-time. The header counts stories and all attributed source channels/publishers.

Publisher caps count story representatives, not alternate links. A group whose preferred publisher already reached its cap is skipped before requests; duplicates cannot switch their credited publisher merely to evade that cap. A blocked representative can fall back to an accessible uncapped publisher. Grouping does not relax freshness, introduce history persistence, or merge differently titled stories semantically. Those remain future evaluated work.
