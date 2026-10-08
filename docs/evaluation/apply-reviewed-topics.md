# Apply the reviewed title matches

For issue #12, this change lets the daily collector recognize the same extra title words tested in PR #26: versioned model names, PyTorch/GPU/CUDA/ROCm terms, and vector search. The word patterns are unchanged. They are shared between the collector and the offline test so the two cannot quietly drift apart.

## Second review: September 30 articles

The owner supplied eight more decisions on October 8. Seven were wanted; one was unwanted. The owner skimmed most and read a couple, without specifying which were read fully. That distinction is preserved. No importance grade was supplied for the unwanted space-weather article; it stays null. The Google URL supplied for Gemini is retained alongside the original queue URL without assuming verified redirect equivalence.

| Reviewed article | Include | Importance | Old check | Tested check |
| --- | --- | --- | --- | --- |
| [Helping small businesses put AI to work](https://openai.com/index/helping-small-businesses-put-ai-to-work) | yes | 2 | Pass | Pass |
| [Forecasting space weather risks on power grids](https://www.microsoft.com/en-us/research/blog/forecasting-space-weather-risks-on-power-grids/) | no | Not supplied | Miss | Miss |
| [Open TTS Leaderboard: Scalable Evaluation for Multilingual Text\-to\-Speech and Voice Cloning](https://huggingface.co/blog/open-tts-leaderboard) | yes | 2 | Miss | Miss |
| [From Upstream Changes to Downstream Confidence: Inside Torch Spyre’s Integration with PyTorch CRCR](https://pytorch.org/blog/from-upstream-changes-to-downstream-confidence-inside-torch-spyres-integration-with-pytorch-crcr/) | yes | 3 | Miss | Pass |
| [A Ray\-Focused Guide to PyTorch Conference North America](https://pytorch.org/blog/a-ray-focused-guide-to-pytorch-conference-north-america/) | yes | 1 | Miss | Pass |
| [Tracing Agent Harness Behavior with NVIDIA NeMo Relay](https://developer.nvidia.com/blog/tracing-agent-harness-behavior-with-nvidia-nemo-relay/) | yes | 2 | Pass | Pass |
| [What work can robots do?](https://www.anthropic.com/research/what-work-can-robots-do) | yes | 3 | Miss | Miss |
| [Gemini 4 Argon: our next era of frontier intelligence](https://deepmind.google/blog/gemini-4-argon-our-next-era-of-frontier-intelligence/) | yes | 3 | Miss | Pass |

The old title check accepts 2 of the 7 wanted articles; the tested check accepts 5. All three added titles were wanted: the Gemini announcement (3), technical PyTorch integration writeup (3), and conference guide (1). Both checks exclude the unwanted space-weather article. **Both still miss the wanted TTS evaluation (2) and robotics research (3).** Those are documented follow-ups, not extra words added after seeing this review.

The conference grade makes sense: learning about a useful tool can justify inclusion at importance 1. Together with the earlier rejected march event, it argues against banning all announcements or conference posts. Importance is editorial value; it is not a model-capability claim or a production star rating.

Across the two targeted reviews, all eleven newly admitted titles have positive inclusion feedback. That supports deploying this small admission change, but does not establish overall precision, guarantee final report inclusion, or optimize ranking. Other unreviewed titles may still be unwanted. GPU/framework topics can produce false positives; the existing source bypass and generic keywords remain limitations.

## How the older-date check was made

The [input](relevance-input-2026-09-30.json) contains 24 previously unreviewed September 30 URLs from the October 6 capture. Previously reviewed canonical URLs were excluded before labeling. The eight review links were purposefully chosen as three additions, three titles neither rule accepts, and two accepted by both. This is a different publication date, not a fresh September 30 feed capture or a chronological held-out benchmark. Cross-date story overlap is not proven absent.

The original October 6 collection rejected these entries as stale before reaching relevance. Their original reasons are retained. The old title check was recomputed before this change using the recorded pre-change collector hash. The input separates the actual `captured_at` clock from an `assessment_at` clock at the end of September 30, using the same 72-hour window for this retrospective exercise. This optional assessment clock affects only offline comparison; the production UTC cutoff is unchanged. No historical selections or link checks are invented. Empty link outcomes mean untested access, and the selected list is empty because these entries were absent from the actual October 6 report.

The [feedback](owner-feedback-2026-09-30.json) and [results](relevance-results-2026-09-30.json) are frozen, with source lineage and exact input hashes. The patterns were set before these labels; the older pool and selected review links were visible during preparation, so this remains a diagnostic comparison rather than a clean blind test.

```bash
python3 -m scripts.compare_relevance docs/evaluation/relevance-input-2026-09-30.json docs/evaluation/owner-feedback-2026-09-30.json --output /tmp/september-30-results.json
```

## Production effect and remaining work

New topic matches let an article reach the ordinary ranking, deduplication, story grouping, publisher caps and access checks. They add no direct score points. The existing lab classifier can classify newly eligible lab headlines under its existing rules and award its existing bounded bonus. Neither the added admission rule nor the bonus guarantees selection. No article-length cutoff, automatic publisher admission, tier-list weighting, blanket event exclusion, new dependency or release publication is introduced.

Regression coverage checks that the production matcher equals the frozen alternative on the second-date pool, version/word boundaries reject unrelated suffixes, source names and summaries alone do not admit topics, and old comparisons stay reproducible. Existing freshness, grouping, access, body-text, attribution and rendering tests still apply.

The next gaps within issue #12 are wanted topics still missed (such as TTS and robotics), unwanted content such as the march listing, broader evaluation and ranking comparisons, and publication history. This PR is a focused improvement, not completion of the entire roadmap.
