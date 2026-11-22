# Clairic preview on daily report articles

The standalone preview takes a daily report and an evidence snapshot. Pick up to five new articles from the report, then ask Clairic for a model name, hardware name, and one useful numeric detail. Every article gets the same three fields. The Markdown preview shows each proposed detail with nearby text so a reviewer can check context.

## Live review on November 22, 2026

I picked five engineering or model stories from the [November 21 release](https://github.com/kantarcise/auto-ai-news/releases/tag/daily-2026-11-21) before making any Clairic calls. Selection came from that published report. The evidence was recaptured locally from feeds and pages using the report's usual evidence collector, so it may differ from what the original run saw. The preview sends at most the first 8,000 UTF-8 bytes per article and leaves title-only evidence out.

| Article | What the preview surfaced | Editorial assessment | Input tokens | Passes | API time |
| --- | --- | --- | ---: | ---: | ---: |
| AMD FlashInfer | MI300X and FP8 prefill | Both appear in the text. Highlighting one GPU loses the fact that the release supports several. FP8 prefill is a feature rather than a measured result. | 1,320 | 13 | 1.07 s |
| AMD world model and NPCs | Radeon AI PRO R9700 | Useful hardware result. The supporting text specifies 32 GB, which the separate detail field missed. | 8,491 | 13 | 1.69 s |
| Inkling 2 Mini | One-million-token context | Useful and supported by the captured text. The preview missed the model name. | 11,253 | 9 | 1.88 s |
| AMD Nitro-P | MI300X and 10.26 samples/s for 512px generation at batch size 32 | Useful with its workload and configuration intact. The preview missed the model name. | 1,057 | 43 | 1.40 s |
| Google Duplex | No source-backed field displayed | A blank result is reasonable for the optional details display. This run cannot tell whether a field was absent, omitted by the API, or dropped by the literal-match check. | 8,678 | 10 | 1.67 s |

Example display for Nitro-P

> AMD Instinct MI300X · 10.26 samples/s at 512px with batch size 32, as reported by AMD.

The table paraphrases the review results. The local preview contains the literal matches and supporting text. A literal match verifies wording, while the editorial check still needs to verify scope and relevance.

All five calls returned usage, totaling **30,799 input tokens and 88 passes**, about **280 neurons** at the launch rate or **672 neurons** at the December 1 standard rate. These are estimates based on API-reported tokens, not a billing reconciliation. The script stops sending requests once known usage reaches 30,000 tokens or a request leaves usage unknown. It checks after each response, so the last call can exceed that threshold. Source bytes and call count are capped independently. [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)

I would keep reports as they are while testing a larger, preselected set for missing names and lost benchmark qualifiers. A future display could start with numeric details that retain their workload and comparison context. One small curated sample is insufficient to estimate reliable coverage or daily cost.

## Run locally

Use a report with a publication receipt and a snapshot produced by the report generator with either `--evaluation-defer-article-content` or `--evaluation-article-content`. The former captures page evidence for the requested articles during the preview. The latter reuses the saved evidence. Use temporary files for the snapshot and the preview, which can contain source text.

With `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` set in your environment:

```bash
python3 -m scripts.preview_clairic \
  --report /tmp/daily-release.md \
  --snapshot /tmp/candidates.json \
  --article https://rocm.blogs.amd.com/artificial-intelligence/nitro-p/README.html \
  --output /tmp/clairic-preview.md
```

Repeat `--article` for additional articles. The preview keeps that order and requires a new output path. Missing evidence and API failures appear in the preview along with reported usage. No publishing workflow invokes this command.
