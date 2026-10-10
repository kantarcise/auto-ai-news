# Daily ranking comparisons

This PR advances the ranking evaluation in issue #12. The existing daily workflow will save a candidate capture and compare three orderings on every normal scheduled/manual run after merge. Both alternatives remain experiments: neither changes report selection, stars or publication.

Optional captures also include [best-effort article labels](article-labels.md), with field-specific explanations and technical clues. Feed and selected-stage assessments are shown together, with differences; experimental depth categories stay in JSON only. Selected-body annotations reuse existing retrieval after ranking inputs are frozen; no article body is copied into the capture and no extra requests are made. Labels do not change the three orderings or selection.

## What to review

Open a completed [Daily AI News workflow run](https://github.com/kantarcise/auto-ai-news/actions/workflows/daily-report.yml), download its `ranking-evaluation-<run-id>-<attempt>` artifact, and open `comparison.md`.

The table shows the largest position changes, original article links, attributed sources, current/fixed/adaptive positions, actual current link outcomes, and the current selected link (including a checked alternate when the representative failed). It shows at most 20 disagreements; complete orderings are retained in JSON. A second list contains at most 20 fresh relevance/event rejects as possible review candidates. Those are not assumed to be missed valuable stories. Quiet-day, missing-link and date exclusions remain in the broader capture, not that short list.

The review needed is concrete: should a moved/rejected article be included, how useful is it (1–3), and was the article read or only its headline? No new review batch is required to merge the capture mechanics. Useful independent-date judgments can later determine whether either ordering deserves activation.

## Three methods, same stories

- **Current:** the existing continuous score and current story grouping.
- **Fixed:** current score plus topic cosine similarity using log term frequency and fixed word weights (no daily inverse document frequency).
- **Adaptive:** current score plus the existing corpus-weighted topic similarity proposal.

Fixed and adaptive use identical profiles, context checks, title/summary evidence, frequency caps and the same `min(1, 2 × similarity)` bonus bound. Only the word-weight method differs. Fixed similarity for an unchanged item stays stable when unrelated/syndicated URLs are added; adaptive similarity can change. Eligibility remains stable and shared among all methods.

All orderings are **before publisher caps and access checks**, not three completed selections or a quality benchmark. Group scores use the highest member score, and ties retain the existing story order. Actual link checks are performed only by the existing selection process. Unchecked alternative candidates remain unknown; no new requests are made to simulate alternative reports. The selected metadata records generator selection, not proof that the later release-publication step succeeded.

The comparison replays the saved current score components and both experimental bonuses, then verifies exact score/order agreement before writing output. Group members have capture-local identities so repeated feed URLs with different summaries cannot accidentally substitute another occurrence. The corpus includes every dated, linked, non-quiet entry reaching relevance, including relevance/event rejects; canonical duplicates contribute once to document frequency. Profile eligibility is saved as a feature, not reconstructed from an incomplete excerpt.

## Saved files and text limits

The artifact contains:

- `candidates.json`: existing collection gates, source diagnostics, grouping, actual selections/access results, plus profile configuration and scoring constants. With the explicit excerpt flag it includes fresh-candidate source priority, coverage, publication date, legacy keyword count, interpreted story kind, actual score, proposed bonuses, normalized title terms, document term counts and eligible profiles.
- `comparison.json`: three complete story orderings, disagreement/rejection counts, review rows, actual selection/link metadata, input checksum and generator revision.
- `comparison.md`: the readable review list.

`--evaluation-excerpts` opts into feed-summary excerpts of **at most 1,000 characters per fresh candidate**, plus normalized scoring features. Similarity still examines at most 4,000 characters each of title/summary; saved unordered term counts reproduce that calculation without copying the remaining feed text. The excerpt need not contain all context used for admission/scoring. No article body is stored. These are public-feed-derived excerpts/features and metadata, stored in workflow artifacts rather than release notes or repository commits. Ranking inputs and the initial capture are saved before optional article-body enrichment; separate selected-article label metadata is appended afterward when excerpt capture is enabled. No body text is added.

Without the flag, evaluation capture remains metadata-only and does not export excerpts or normalized document terms. Both fixed/adaptive score summaries can still be recorded, but full replay requires the opt-in inputs. Historical captures and feedback remain untouched.

Artifacts use distinct run/attempt names and a 30-day retention setting, using [GitHub's upload-artifact action](https://github.com/actions/upload-artifact). This is temporary evaluation collection, not permanent report history. Download useful independent captures before expiry. Comparison/upload failures are non-blocking and visible in workflow logs; an available capture is still uploaded if comparison fails. Existing test/generation failures retain their normal behavior. The release creation/editing step is unchanged.

## Run locally without publication

Capture when explicitly evaluating live feeds, to separate files:

```bash
python3 scripts/generate_report.py --output /tmp/ai-news-preview.md --evaluation-output /tmp/candidates.json --evaluation-excerpts
python3 -m scripts.compare_rankings /tmp/candidates.json --output /tmp/comparison.md --json-output /tmp/comparison.json --revision "$(git rev-parse HEAD)"
```

The second command is entirely offline. It rejects input/output collisions, missing replay inputs, invalid term counts, invalid dates, changed member scores, changed group scores and inconsistent orders instead of guessing historical inputs. Revision and snapshot checksum travel with the output. For saved captures, only the second command is needed.

## Verification and remaining evaluation

Offline tests verify unchanged selection/diagnostics/request counts with capture enabled; fixed-weight stability versus adaptive pool dependence; bounded summary excerpts and body exclusion; duplicate/group identity replay; empty/no-disagreement reports; changed-score/order rejection; escaped external text; unknown access; and CLI output/collision behavior. The existing owner-feedback regressions, dates, publisher caps, grouping/fallback and Markdown cases run too. Workflow YAML parses; the action's documented version/inputs were checked. No live run, upload or publication was triggered for this PR.

This provides future independent-date evidence, not a claim that either ranking improves usefulness. Next evaluation should review disagreements, compare wanted-story coverage and graded ordering on complete candidate sets, and inspect publisher/topic concentration and selection after caps/access constraints. Label coverage and access uncertainty must accompany any metric. Admission misses, unconditional publisher bypasses, publication-history repetition and semantic alternatives remain separate work under issue #12/#17.
