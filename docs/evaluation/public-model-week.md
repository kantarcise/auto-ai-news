# Seven-day public model evaluation

Part of [issue #38](https://github.com/kantarcise/auto-ai-news/issues/38), following the paired runner in PR #42. The owner requested a separately named public evaluation release each day for approximately one week. The ordinary daily workflow, source list, rules default and publication history behavior stay unchanged.

## What runs

`.github/workflows/model-evaluation.yml` schedules at 05:30 UTC (08:30 Europe/Istanbul). The ordinary production report keeps its separate 06:15 UTC slot; read the two attached evaluation reports for the paired comparison. GitHub schedule times are best effort, not guaranteed execution times. Manual dispatch uses the same gate and budgets. Only the repository default branch can run the evaluation; there is no pull-request trigger.

Each active run reads release history and captures all configured feeds with best-effort evidence before relevance decisions. It creates two reports from that single evaluation capture:

- `rules.md`: the existing admission and ranking behavior.
- `content.md`: Cloudflare Clef-flash decisions under `content-shadow-v1`, with baseline ranking and the reviewed conservative tie preference.

The release tag is `evaluation-model-YYYY-MM-DD`; it is a prerelease and never marked latest. Its notes include status, decision labels, evidence completeness, usage and review guidance. `differences.md` lists selected-URL differences. Existing evaluation releases are left unchanged on reruns. Evaluation tags are ignored by production publication history, so recovered stories are not consumed by the experiment.

Compare the two **attached evaluation reports** with each other. The normal daily release fetches feeds at a different time and can have a different pool. This workflow does not change or regenerate that release. The prior local title-versus-content comparison is a development check; the daily trial compares rules against content only.

## Configure and activate after review/merge

1. Create a dedicated Cloudflare API token scoped to Workers AI inference for the intended account. Do not copy a broad local Wrangler OAuth login into GitHub.
2. Store it as the repository Actions secret `CLOUDFLARE_API_TOKEN`. Set the repository variable `CLOUDFLARE_ACCOUNT_ID` to the corresponding account ID. Secret values are never committed or attached to a release.
3. Set repository variable `MODEL_EVALUATION_START_DATE` to the first desired **UTC date**, formatted `YYYY-MM-DD`. It runs on that date and the following six calendar dates. For seven future scheduled runs, choose a date whose 05:30 UTC slot has not passed.
4. To stop early, clear `MODEL_EVALUATION_START_DATE`. Empty means disabled; malformed dates fail before inference. After the seven dates, later scheduled/manual runs skip the experiment automatically. This is seven calendar dates, not seven guaranteed successful reports; failed or missed runs do not silently extend it.

No configuration is enabled by this PR. Creating the Cloudflare token and storing the secret require account-owner setup. The inference secret is supplied only to the model step of the default-branch evaluation job. The publication job has repository contents-write permission and receives only the public Markdown artifact; it never receives the Cloudflare token.

## Bounds, failures and public data

Per run: at most 100 model HTTP attempts, 1,000,000 total serialized input bytes, and 100 supplemental URL checks. A URL check can perform multiple HTTP requests under the existing checker. Existing adapter request/response limits and timeouts apply. The evidence collector attempts at most 20 unique article URLs; other candidates use feed/summary/title fallback, so “content” does not mean every candidate has a full body. Public notes expose provenance, partial/truncated flags and unknown completeness.

These are per-run limits, not a daily account neuron cap or a promise of free operation. Rerunning the workflow makes another bounded set of calls, even if an evaluation release already exists. Review reported token usage and account billing separately; other account workloads share any allowance. There is no cross-run assessment cache in this workflow.

If the candidate pool exceeds the inference budget or the provider/schema/link checks fail, the paired runner produces a whole-report rules fallback. The release explicitly says the model arm is unavailable and partial decisions are unapplied. Do not count that date as a valid model-quality comparison. If capture, export, or the job itself fails, no evaluation release is created; the normal daily workflow runs independently.

Only four Markdown files are uploaded as the public artifact: review notes, rules report, content report and differences. The three report/difference files are attached to the release; review notes become its body. The private runner-temporary capture, raw responses, caches and article text are not uploaded. Article titles and links remain attributed and escaped. The artifact is public repository data, not a private storage mechanism.

## Review over the week

Record preference, useful recoveries, unwanted additions/removals, duplicate stories, publisher/topic variety and reasons per date. Keep AI-topic judgments separate from include/skip decisions. This is an unblinded paired editorial trial, not randomized traffic A/B testing, and no automatic promotion threshold is implemented.

Owner feedback from the first local 13-candidate run: agrees the meetup is AI no/engineering no and an event, agrees the industrial-robotics content is AI-related, and agrees Dwarf Fortress is opinion/discussion. These are label judgments; explicit include/skip preferences were not supplied. The owner favors content over titles/short summaries and is concerned that Simon Willison’s broad feed includes short links and quotations. Keep sources fixed during this trial to isolate the policy change; reassess source breadth separately afterward. The two ttok versions and mixed robotics newsletter remain unresolved editorial cases.

After the trial, decide whether to retain rules, refine the candidate policy, or propose a reversible production change based on the reviewed reports and acceptable reliability/runtime/usage. Local Decider remains a separate optional provider behind the merged assessment contract.
