# Local decision models: a bounded roadmap

Research date: October 11, 2026. This is a plan, not a benchmark result or a production change. Models have not been downloaded or run on the owner's RTX 3090.

Goal: use article meaning to recover useful AI engineering stories and improve ordering, while preserving useful model releases, tutorials and substantive customer stories. Publisher reputation is useful context, not an automatic inclusion or rejection rule.

This is optional follow-up work under [#35](https://github.com/kantarcise/auto-ai-news/issues/35). It does not add requirements to finishing #12.

## Shortlist and hardware expectations

| Model | Published size and license | RTX 3090 assessment | Role |
| --- | --- | --- | --- |
| [Mapika Decider-4B](https://huggingface.co/Mapika/decider-4b) | 4.2B parameters; 8.4 GB BF16 weights; Apache 2.0 | Plausible comfortable starting point, allowing memory for inference; not yet measured | Establish a local baseline |
| [Cloudflare Clef-flash](https://huggingface.co/Cloudflare/clef-flash) | 9B parameters; BF16; Apache 2.0 | Roughly 18 GB for weights by parameter arithmetic, before runtime overhead; potentially feasible with short text and one article at a time, but not confirmed | Preferred Cloudflare candidate |
| [Cloudflare Clef](https://huggingface.co/Cloudflare/clef) | 27B parameters; BF16; Apache 2.0 | Roughly 54 GB for weights alone; does not fit entirely in 24 GB at BF16 | Optional hosted quality reference, only if smaller models are insufficient |
| [Cloudflare Clef-omni](https://huggingface.co/Cloudflare/clef-omni) | 30B-A3B mixture-of-experts backbone with media encoders; Apache 2.0; card reports about 64 GB GPU memory for BF16 backbone | Not a straightforward single-3090 BF16 target; 3B active parameters does not mean only 3B weights need storage | Exclude from this text-only experiment |

Memory arithmetic is an estimate, not a measured fit. Runtime buffers, article length, batching and the decision head require extra memory. Quantization or CPU offloading may make larger models possible, but verifying their decision-head support and accuracy is outside the first experiment.

Cloudflare's model cards use a custom joint decision head. Generic chat examples in hosting widgets are not sufficient evidence that a chat server preserves it. Use the documented reference implementation or a runtime that explicitly supports the decision head and `/v1/systemone`.

The [SGLang Clef cookbook](https://docs.sglang.io/cookbook/autoregressive/Cloudflare/clef) documents H200/B200/B300 setups, not RTX 3090 support. It also documents runtime-specific context and confidence behavior. Record runtime identity and do not compare confidence values as if they were interchangeable calibrated probabilities.

Decider's current card documents version-specific regressions and overconfidence on some difficult questions. Pin the exact model revision and inference package version; do not treat the newest revision or a high confidence value as proof of suitability.

## 1. Get one local decision working

- The owner confirmed the RTX 3090 is in a separate Linux machine. Confirm available GPU memory, system RAM, disk space and access method next. The current checkout is on macOS; access to the Linux machine has not been established.
- Create an isolated experimental environment on that machine. Model packages belong there, not in the daily generator's runtime dependencies. Confirm before adding any production dependency.
- Start with Decider-4B, then attempt Clef-flash using the documented decision implementation. Pin weights, code and package versions. Use text only, one article per request and a bounded input length initially.
- Check one known technical article, one relevant announcement and one unrelated article. Record memory use, latency, errors and truncation. This is a smoke check, not accuracy evidence.
- Stop expanding the runtime effort if Clef-flash cannot fit or is incompatible. Keep Decider as the local candidate; consider hosted Clef-flash as a separate comparison rather than turning this into a quantization project.

Deliverable: reproducible setup notes and successful structured local answers on the 3090, with actual measurements.

## 2. Compare on saved articles

Reuse saved candidates and the owner's existing feedback. No new rating batch is required to begin. Ask separate questions:

- Is AI or its computing infrastructure a substantive subject of the article?
- Does the text contain concrete engineering explanations, mechanisms, implementation details or measurements?
- What kind of article is it: technical explanation, research/model release, substantive case study, announcement/event, opinion/discussion, or mainly promotion? Allow mixed or insufficient evidence.

Do not equate promotion with automatic rejection: the owner has liked informative customer stories. Do not equate a forum with automatic rejection either. These answers are evidence for a policy, not final owner importance scores.

Compare current rules, Decider-4B and Clef-flash on identical saved text. If only a title is available, mark that explicitly; keep title-only and fuller-text results separate. Unrated candidates remain unknown, not unwanted. Include candidates rejected by the current filter so recovery can actually be measured.

Record wanted misses, unwanted inclusions, disagreements, technical-story ordering, runtime errors, latency and peak GPU memory. Preserve raw answers, model/runtime versions, question wording, input hashes and truncation. Uncertainty or a model failure keeps the current behavior during the experiment.

Use some reviewed examples to develop the questions and keep the rest untouched for the final comparison, grouping duplicate stories together. Because the feedback set is small and already familiar, state the limits honestly; later chronological examples provide stronger confirmation. Do not claim generic benchmarks establish news quality.

Deliverable: a comparison PR with concrete before/after articles and an honest recommendation. Ship no algorithm change if there is no useful improvement.

## 3. Observe daily decisions before enabling them

If the saved comparison is promising, run the candidate alongside the existing rules and save its proposed decisions without changing published selection. Compare the same available text and report missing content explicitly. Set the observation window and success criteria in the comparison PR before starting.

Success requires fewer wanted misses or better placement of high-importance engineering stories without observed unacceptable unwanted inclusions. Report the underlying small counts rather than hiding them behind percentages. Agree numerical thresholds based on the available sample before enabling a policy.

Deliverable: observed daily differences and a focused enablement decision; this is not a commitment to keep collecting reviews indefinitely.

## 4. Choose daily operation only after demonstrated benefit

Two routes share the same article questions and normalized result format, but need different transport/authentication adapters:

- **Local:** run the job on the 3090 machine, for example using a self-hosted runner. The machine must be available for scheduled runs. GitHub-hosted jobs cannot access that machine's localhost directly. A public inference endpoint is not required for the initial local workflow.
- **Cloudflare hosted:** call Workers AI from the existing GitHub job. Use the owner's Cloudflare account ID and a suitable API token stored as a secret. Domain ownership alone does not provide inference credentials; no new domain or public Worker is needed for a direct REST call.

Cloudflare currently lists Clef-flash at **$0.038 per million input tokens**, with no output-token charge. For illustration, 500 articles/day at 2,000 total input tokens/article over 30 days is 30 million input tokens, or **$1.14 in model usage** before retries, extra passes or any other service costs. Actual billing eligibility and account configuration have not been checked. Source: [Workers AI Clef-flash documentation](https://developers.cloudflare.com/workers-ai/models/clef-flash/).

Local downloads do not need a Jev account or Cloudflare inference token. The initial model runtime and HTTP adapter can remain separate from the standard-library generator. Production integration must retain timeouts, bounded requests, existing attribution/deduplication and an explicit fallback to the current rules if the model is unavailable.

Deliverable: a small production PR only after the comparison justifies it, with an explicit local-versus-hosted decision. No training, audio/video processing, model tournament or unconditional publisher bypass is included in this roadmap.
