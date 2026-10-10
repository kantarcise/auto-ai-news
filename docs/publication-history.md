# Publication history

Daily automation reads publication records from existing GitHub Release notes before collecting feeds. It keeps URLs recorded on earlier UTC report dates out of the new-article list, using the same canonical URL rule as within-report deduplication (including removal of tracking parameters). An expandable “Previously included — catch up” section below New articles shows each repeat once per canonical URL, retaining an original feed link, source attribution and a link to the earlier report date. The header counts new stories and their sources, not catch-up entries. Catch-up links are not checked again today; the section states that limit. The evaluation snapshot retains each repeat candidate and its previous report date, with a separate `previously_included` metadata list; repeat candidates do not influence experimental ranking inputs or count as new selections.

This is the first part of item 4 in issue #12. It prevents repeated links in the new-article list; it does not finish substantive-update detection or the evaluation baseline in item 3.

## Persistence and publication

Each new report includes a hidden, versioned JSON receipt in its release notes. The receipt records canonical URLs for the selected new headlines and their alternate links actually shown, plus the UTC report date. It contains no article bodies or credentials. The report and receipt become persistent in the same release create/edit operation. Merely generating a report, running a comparison, or failing to publish cannot change history. No state commits, caches, expiring artifacts or extra asset uploads are required.

The history reader uses the GitHub CLI's paginated release API, reads all pages, and accepts only published, non-prerelease `daily-YYYY-MM-DD` releases dated no later than today. It does not edit releases. A failed API request or malformed receipt stops automation rather than silently publishing without repeat checks. Releases created before this version have no receipt and are counted explicitly in the report; their links are not guessed from Markdown or retroactively recorded. Repeat prevention starts with the first successful publication using this version.

Runs are serialized by the workflow's publication concurrency group. Same-day records are excluded from the rejection set so reruns can keep that day's stories. The new receipt preserves the union of links published earlier that day and new article links shown by the rerun, so a later edit cannot make an already published URL disappear from tomorrow's history. The release tag uses the captured history date. If UTC midnight passes between history capture and generation, generation stops; rerun to capture history for the new day.

Catch-up entries do not enter today's receipt again, so they keep their earlier inclusion date rather than becoming a newly selected article each day. The section covers only articles still found in the current feeds and within the configured coverage window (72 hours by default), not all articles from every previous report. Even a report with no new stories can provide catch-up links. For a longer absence, a separate expandable “Previous daily reports” section lists up to 14 actual earlier published daily reports, newest first, followed by a link to the full report history. These links include legacy reports without receipts and are independent of the article coverage window. Current-day reports, drafts, prereleases and future-dated tags are excluded; missing days do not produce guessed links. Report dates are UTC. The section remains available when there are no new or catch-up articles.

## Limits

- New URLs remain eligible, including new model versions and separate follow-up analysis. Title similarity alone does not suppress them across days.
- Changed content at an already published URL still goes to catch-up rather than the new-article list. Detecting a substantive update at the same URL needs separate evidence and policy work; do not call item 4 complete yet.
- Deleting a release or removing its receipt removes that part of the record. Receipts describe links published through this workflow; they are not an independent archive or a content authenticity check.
- Reading every release page is simple and complete for this repository, but grows with release history. No history pruning or release deletion is included.
- Short and empty reports remain valid. Previously published articles never fill unused slots.

## Local use

Local generation keeps its previous behavior unless given history explicitly. To use the same checks without publishing:

```bash
python3 -m scripts.publication_history --output /tmp/publication-history.json
python3 scripts/generate_report.py \
  --publication-history /tmp/publication-history.json \
  --output /tmp/daily-ai-news.md
```

The first command needs authenticated GitHub CLI access from this repository. The second reads the history file without modifying it. Its hidden receipt is only a proposed publication record until those notes are actually published. No command here publishes anything.

## Offline evidence

Regression tests cover complete pagination, ignoring drafts/prereleases/future/non-daily releases, old releases without receipts, malformed records, failed API reads, tracking-parameter duplicates, rejection before link checks, preserved comparison inputs, same-day eligibility, receipt union across edits, alternate attribution and HTML comment escaping. Catch-up tests cover clickable article/report links, original URLs and source attribution, canonical deduplication, stale/undated exclusions, long escaped titles, empty/catch-up-only reports, unchanged link-check counts and receipts that do not refresh repeat dates. Previous-report tests cover legacy links beyond 72 hours, newest-first ordering, canonical date validation, duplicate date removal, a 14-link limit, current/future/draft/prerelease exclusion, empty history and full-history navigation. Existing Markdown tests cover special characters, long titles, missing dates, skipped sources and empty reports. Live release publication is intentionally not exercised by these tests.
