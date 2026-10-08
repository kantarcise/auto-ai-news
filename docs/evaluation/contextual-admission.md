# Context checks for ambiguous words and model names

Follow-up to PR #27, addressing issues #28 and #29 within issue #12. The final admission path now checks ambiguous keywords instead of allowing the old fallback to undo a topic rejection. The experimental ranking bonus remains shadow-only.

## Behavior

A headline containing agent, model, transformer, diffusion, embedding, neural, generative, prompt, eval/evals or flux needs recognizable AI/technical context in the headline or bounded feed summary. Clear AI phrases and existing engineering topic matches still qualify. Examples of context include language models, neural networks, self-attention/cross-attention mechanisms and inference, model distillation, reward hacking, recommender systems and deployment/package tooling. This is an explicit lexical rule, not semantic understanding.

Configured family names are handled by family interpretation alone; the generic keyword fallback cannot independently re-admit rejected Claude/Gemini/Llama interpretations. Ambiguous family names include Claude, Gemini, Llama, Mistral, Flux and the previous Seed/Nova/Muse/Inkling entries. They require a whole attached/separate version, recognizable context, an adjacent model marker, or a configured named variant such as Claude Opus or Mistral Large. Future numeric versions and configured new families remain supported. Named variants are editorial configuration entries, not a dynamically verified list of models.

Explicit non-model phrases such as Claude Monet and Gemini horoscope/zodiac remain literal even if the article also mentions AI. An AI article about Monet can qualify as AI coverage without acquiring a model-family flag. Lab announcement classification uses the same interpreted flag instead of a separate unqualified brand-name match.

Title and summary context are bounded separately to 4,000 characters. A summary can resolve an ambiguous headline keyword/name; it cannot admit an unrelated headline without a title signal. Eligibility remains independent of corpus frequency. Dates, quiet-day handling, original links, escaping, grouping, access checks and publisher caps remain in place.

## Evidence and possible missed stories

The [October 6 comparison](context-results-2026-10-06.json) and [September 30 comparison](context-results-2026-09-30.json) compare the revised rule with the saved PR #27 outcomes on exactly the same frozen candidate pools. The original captures, feedback and PR #27 results remain unchanged. Each comparison records all admission changes, the configuration and input hashes.

| Frozen pool | Wanted admitted before → after | Unwanted admitted before → after | Total admitted before → after |
| --- | --- | --- | --- |
| October 6 | 11 → 11 | 0 → 0 | 27 → 26 |
| September 30 retrospective assessment | 7 → 7 | 0 → 0 | 17 → 17 |

All 18 reviewed wanted stories stay eligible; both reviewed unwanted stories stay excluded. These labels helped develop the rules, so this is regression/development evidence rather than a held-out quality test.

One unreviewed headline is newly excluded: **“The Agent Said It Was Done. The Database Disagreed.”** It may be useful AI engineering. The title-only frozen record has neither an explicit AI phrase nor enough supporting context under the new rule. It is an unresolved potential recall loss, not an inferred negative owner preference. A live feed summary with language-model/AI context could recover it. No previously excluded frozen story is newly admitted. The prior uncertain “California crashes robot fight club” match remains eligible.

Paired synthetic regressions reject insurance agents, fashion models, electrical transformers, horoscopes, Monet exhibitions, llama farms, Mistral weather, flux capacitors, perfume diffusion and neural anatomy. They preserve clear AI/engineering examples, valid Claude/Gemini releases, future versions, named variants, summary context, model distillation, reward hacking, recommender deployment and technical workshops. These are synthetic counterexamples, not observed feed failures or an overall precision estimate.

Reproduce without network access:

```bash
python3 -m scripts.compare_contextual_admission docs/evaluation/relevance-input-2026-10-06.json docs/evaluation/owner-feedback-2026-10-06.json docs/evaluation/editorial-results-2026-10-06.json --output /tmp/context-october-6.json
python3 -m scripts.compare_contextual_admission docs/evaluation/relevance-input-2026-09-30.json docs/evaluation/owner-feedback-2026-09-30.json docs/evaluation/editorial-results-2026-09-30.json --output /tmp/context-september-30.json
```

The September 30 pool retains its actual October 6 capture timestamp and retrospective assessment clock. Frozen summaries are unavailable; the comparison is title-only, preserves owner-review uncertainty, and invents no network outcomes or historical rankings.

## Remaining limits

Latent Space and smol.ai still have unconditional relevance admission apart from the existing quiet-day/event rules; their unrelated headlines can pass. Original keyword counts still contribute to ranking. Context rules can mistake tangential technical references for useful coverage and can miss terse headlines; configured variants and ordinary family names still have possible ambiguities. No claim is made that every admission path is context-checked or that ranking quality improved. Broader unseen-date evaluation remains under issue #12.

Offline tests cover final admission and complete collection, paired positives/negatives, family tokenization and lab classification, bounded summaries, stable eligibility, publisher-cap and freshness behavior, shadow-only ranking, comparison provenance and the frozen owner feedback. No production dependency, live feed/article check, workflow dispatch or publication is introduced.

## PR review fixes

The [review of commit 25e666a](https://github.com/kantarcise/auto-ai-news/pull/30#issuecomment-6067667753) identified two valid problems. Family-specific version formats now recognize FLUX.1 and MiniMax-M2, including future numbers, without treating malformed suffixes or formats belonging to another family as valid. The [BFL announcement](https://bfl.ai/blog/24-11-21-tools) confirms the real “Introducing FLUX.1 Tools” headline; this is historical title evidence, not a fresh eligible article or a recommendation to use its tools. Offline tests check both examples through lab collection and classification.

Bare attention no longer supplies technical context. Self-attention, cross-attention and attention mechanism phrases can supply it; ordinary customer/exhibition attention cannot, whether in titles or summaries. Paired negative and positive cases pass through final admission and the complete collection flow. The same frozen comparison counts and the one unreviewed potential miss above remain unchanged.
