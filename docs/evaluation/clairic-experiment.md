# Clairic extraction pilot

Clairic matched **14 of 15 expected values** on five short, frozen inputs on November 22, 2026. The pilot asks whether article links would be easier to scan with a model name, a hardware name, and a numeric detail readers can verify. See [issue #48](https://github.com/kantarcise/auto-ai-news/issues/48).

Each [saved input](clairic-sample.json) contains a short excerpt or a labeled paraphrase of a real source. The reviewer chose the target metric, context, and unit per article before running the model. The API gets the metric instruction, while the local runner keeps the expected answer for scoring. A match is exact text, numeric equality, or an expected null. The unit and metric context in the table come from the reviewer and are part of the question, so this run does not measure automatic metric or unit selection.

| Source | Model returned | Hardware returned | Numeric result in its requested context | Matches | Input tokens | Reported passes | Request time |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| [AMD GLM serving](https://rocm.blogs.amd.com/artificial-intelligence/glm53flash-mi300x-vllm/README.html) | GLM-5.3-Flash | MI300X | 192 GB per GPU | 3/3 | 505 | 11 | 0.678 s |
| [AMD Qwen quantization](https://rocm.blogs.amd.com/artificial-intelligence/quark-qwen-ple/README.html) | Qwen3.8-Flash-Next | Ryzen AI Halo | ~80 GB reduced checkpoint | 3/3 | 456 | 12 | 1.007 s |
| [PyTorch Helion](https://pytorch.org/blog/fast-by-default-compile-time-heuristics-for-helion-kernels/) | — | H100 | 1.27× vs. handwritten vLLM CUDA/C++ reduction operators | 3/3 | 768 | 6 | 0.821 s |
| [Cloudflare Clef](https://developers.cloudflare.com/workers-ai/models/clef/) | “Cloudflare's 27B multimodal decision model” (expected Clef) | — | 65,536 context tokens | 2/3 | 678 | 14 | 1.022 s |
| [llama.cpp v1](https://huggingface.co/blog/ggml-org/llama-cpp-v1) | — | — | — | 3/3 | 1,094 | 4 | 0.643 s |

Dashes are returned nulls. All five expected nulls matched. The source slices for the four numeric answers were `192`, `80`, `1.27`, and `65,536`. The Qwen excerpt marks the value as approximate, which the bare numeric answer loses. The AMD GLM hardware name matched, but Clairic supplied no span for it. The Clef naming miss had a valid span that pointed to a description, illustrating that a source span helps review the answer but cannot establish that it satisfies the question.

Five requests took about **4.17 seconds** combined. Cloudflare's API reported **3,501 input tokens and 47 passes**. The usage field already accounts for passes, so the cost estimate uses the reported token total directly. At the published rate that is **about 32 neurons during the promotion** and **76 neurons at the December 1 standard rate** for the same number of billed tokens. The account analytics query had no matching records when checked, so the neuron figures are estimates. Both rates draw on the shared 10,000-neuron daily free allowance. [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)

## Reproduce

With `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` already set in your environment, run from the repository root:

```bash
python3 -m scripts.evaluate_clairic --run
```

The script sends up to five text-only requests with an 8 KB aggregate request-body limit and prints one JSON record per completed case. Where the API supplies usable offsets, each record includes the corresponding source slice for review. Pass counts and latency are observations from the preview service and can vary.

The excerpts are deliberately short and the metric prompts were tailored by hand. The next comparison should use previously unseen article text as captured by the report generator, with one common extraction schema and examples where the same units describe different things. That would show whether the facts are useful enough to display and give a more realistic budget. The five-case pilot alone supports a follow-up evaluation.
