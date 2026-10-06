# October 6: test a broader article check

This is the next offline comparison for [issue #12](https://github.com/kantarcise/auto-ai-news/issues/12). It tests whether extra topic words find articles the owner wanted but the title filter missed. The daily report is unchanged.

## Inputs and what the test does

- The saved capture clock is **2026-10-06 17:57:42.282185 UTC**; the original 72-hour window is unchanged.
- The [input file](relevance-input-2026-10-06.json) contains **all 45 parsed entries inside that window**, chosen by date only. It is a metadata-only subset of the full local capture (5,317 occurrences; 5,302 linked URLs). The full capture hash is recorded for provenance; raw feeds and article text are absent.
- [Owner feedback](owner-feedback-2026-10-06.json) contains the original eight reviews, PyTorch clarification, and four follow-up reviews: eleven includes and one exclusion, with importance grades. PyTorch hardware enablement and the four follow-up articles have owner-confirmed article-inspection evidence. The NVIDIA includes reflect unambiguous approval in response to the inclusion review; the other decisions were explicit yes/no responses. Other inspection levels stay unspecified; feedback is not silently promoted into the scored-review format.
- The current check uses the **saved collection outcomes**, including the existing Latent Space/smol.ai bypass. It is not recalculated with today’s mutable source configuration or keyword list.
- The proposed check keeps previously admitted titles and adds three kinds of title matches: versioned model names (such as Qwen3.8), framework/GPU terms (PyTorch, GPU/GPUs, CUDA, ROCm), and the phrase vector search. Quiet-day exclusions remain excluded. Terms use word boundaries to avoid matching unrelated strings such as GPUish or Qwen3.8foo.

The test stops at the title filter. It does **not** rerank, group or deduplicate new matches, apply publisher limits, or check their links. Passing this check does not mean an article would appear in the report.

## Results

| Count | Current check | Proposed check |
| --- | --- | --- |
| Titles passing the check | 19 | 27 |
| Passing articles the owner wanted (11 reviewed) | 3 | 11 |
| Passing articles the owner did not want (1 reviewed) | 1 | 1 |
| Passing articles without a decided owner preference | 15 | 15 |

The eight added matches are shown below. Four were wanted articles from the original review. **The owner then read and approved the four remaining additions**, with grades 3, 3, 1 and 3. All eight additions now have positive inclusion feedback. Fifteen other admitted titles still lack a decided owner preference; they are not counted as bad articles.

| Added article | Owner decision | Importance |
| --- | --- | --- |
| [AICR v1\.0: Open, stable, and verifiable GPU cluster configuration](https://developer.nvidia.com/blog/aicr-v1-0-open-stable-and-verifiable-gpu-cluster-configuration/) | yes | 3 |
| [Control How Your GPU Shares Work with Green Contexts](https://developer.nvidia.com/blog/control-how-your-gpu-shares-work-with-green-contexts/) | yes | 3 |
| [Evolution of the PyTorch Media Processing Landscape](https://pytorch.org/blog/evolution-of-the-pytorch-media-processing-landscape/) | yes | 1 |
| [PyTorch Hardware Enablement: Updates from the Accelerator Integration Working Group](https://pytorch.org/blog/pytorch-hardware-enablement-updates-from-the-acceleration-integration-working-group/) | yes | 3 |
| [Completing the GPU Performance Picture: Understanding TAF Alongside Peak FLOPs and MAF](https://rocm.blogs.amd.com/artificial-intelligence/taf-blog/README.html) | yes | 3 |
| [ROCm 10\.1: Breaking the Data\-Movement Bottleneck](https://rocm.blogs.amd.com/ecosystems-and-partners/rocm-10.1-blog/README.html) | yes | 3 |
| [Qwen3\.8 27B addition in words](https://simonwillison.net/2026/Oct/4/qwen38-addition-in-words/) | yes | 2 |
| [NEAREST BY Join: Scaling Vector Search in Databricks Runtime](https://www.databricks.com/blog/nearest-join-scaling-vector-search-databricks-runtime) | yes | 2 |

Both checks still admit the **March to Stop Building AI** event announcement, which the owner marked no/0. Broader topic matching does not solve that unwanted inclusion. Its event format needs a separate test with positive and negative examples rather than banning all announcements.

The Atlassian/OpenAI partnership passes both title checks, but its saved article request returned **HTTP 403**. That is still an access problem, not a relevance recovery. The four recovered wanted articles were not link-checked in the original run; the original link-check outcomes remain unknown. Owner inspection is recorded separately from those historical checks. The current report had 16 selected representatives, not 19: title admission and final selection are different steps.

## What the follow-up reviews value

The owner valued GPU-cluster lifecycle maintenance, explanations of concurrent GPU workloads, CI/native-dependency maintenance, and clear introductions to data-movement limits. The PyTorch media update received importance 1; both NVIDIA additions and the ROCm update received importance 3. Useful vendor engineering is welcome; these grades are article judgments, not blanket publisher approval. Interest in trying Green Contexts on an RTX 3090 is recorded as a future experiment idea, not a verified compatibility claim or part of this PR.

## Limits and next decision

The added terms were chosen after seeing the initial eight owner reviews, before the four follow-up reviews. Recovering these four examples therefore shows that the rule does what we designed it to do; it does **not** show that it generalizes. The first eight-item sample and four rule-selected follow-up reviews all come from one date; this is not a random or held-out benchmark. Five included articles have clarified inspection provenance. The four follow-up approvals provide useful evidence about these additions, but cannot establish performance on new dates or unreviewed articles. No report-wide precision, recall, importance accuracy, or improvement percentage is claimed.

GPU/framework words can appear in material with little AI or practical value. All four follow-up additions were welcomed here, but this small sample does not test enough unwanted engineering articles to rule out that problem. The rule also retains source-based admission and generic keyword false positives, may miss more model brands and relevant articles without these words, and cannot recover posts missing from failed or unconfigured sources. Rankings, stars, access results, grouping and report counts cannot be replayed from this metadata alone.

Next: capture additional dates and review positive/negative examples without using their outcomes to tune the rule first. Keep shared stories in one evaluation split. Confirm remaining inspection evidence before moving these preferences into scored quality labels. Compare on that separate batch before proposing a production change. No dependency, model, workflow, release or production-filter change is included here.

## Reproduce with no network

From the repository root:

```bash
python3 -m scripts.compare_relevance docs/evaluation/relevance-input-2026-10-06.json docs/evaluation/owner-feedback-2026-10-06.json --output /tmp/relevance-results.json
```

[Saved machine-readable results](relevance-results-2026-10-06.json) contain each decision and hashes of both input files. The tool checks capture clock/source identity, candidate IDs, exact URLs/titles and preference values. It never fetches feeds or articles. A missing link outcome means not checked. Unknown preferences and inspection levels remain unknown. This separate preference comparison does not relax the scored evaluator’s evidence rules.

The input subset was made by keeping rows with a publication date between the original clock minus 72 hours and the clock, inclusive, and retaining the saved selected representatives, link outcomes and non-freshness diagnostics. Every current linked entry was retained; none was picked based on feedback. The full source hash links the two artifacts, but the full capture is local and not committed. This file cannot stand in for the complete archive pool or a broader/multi-day benchmark.
