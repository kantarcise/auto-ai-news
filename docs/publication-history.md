# Publication history

Daily automation reads publication records from existing GitHub Release notes before collecting feeds. It excludes URLs recorded on earlier UTC report dates, using the same canonical URL rule as within-report deduplication (including removal of tracking parameters). Exclusions show the earlier date in Selection exclusions. The evaluation snapshot retains each rejected candidate and its previous report date; excluded candidates do not influence experimental ranking inputs.

This is the first part of item 4 in issue #12. It prevents repeated links; it does not finish substantive-update detection or the evaluation baseline in item 3.

## Persistence and publication

Each new report includes a hidden, versioned JSON receipt in its release notes. The receipt records canonical URLs for the selected headlines and alternate links actually shown, plus the UTC report date. It contains no article bodies or credentials. The report and receipt become persistent in the same release create/edit operation. Merely generating a report, running a comparison, or failing to publish cannot change history. No state commits, caches, expiring artifacts or extra asset uploads are required.

The history reader uses the GitHub CLI's paginated release API, reads all pages, and accepts only published, non-prerelease `daily-YYYY-MM-DD` releases dated no later than today. It does not edit releases. A failed API request or malformed receipt stops automation rather than silently publishing without repeat checks. Releases created before this version have no receipt and are counted explicitly in the report; their links are not guessed from Markdown or retroactively recorded. Repeat prevention starts with the first successful publication using this version.

Runs are serialized by the workflow's publication concurrency group. Same-day records are excluded from the rejection set so reruns can keep that day's stories. The new receipt preserves the union of links published earlier that day and links shown by the rerun, so a later edit cannot make an already published URL disappear from tomorrow's history. The release tag uses the captured history date. If UTC midnight passes between history capture and generation, generation stops; rerun to capture history for the new day.

## Limits

- New URLs remain eligible, including new model versions and separate follow-up analysis. Title similarity alone does not suppress them across days.
- Changed content at an already published URL is still excluded. Detecting a substantive update at the same URL needs separate evidence and policy work; do not call item 4 complete yet.
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

Regression tests cover complete pagination, ignoring drafts/prereleases/future/non-daily releases, old releases without receipts, malformed records, failed API reads, tracking-parameter duplicates, rejection before link checks, preserved comparison inputs, same-day eligibility, receipt union across edits, alternate attribution and HTML comment escaping. Existing Markdown tests cover special characters, long titles, missing dates, skipped sources and empty reports. Live release publication is intentionally not exercised by these tests.
