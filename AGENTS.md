# Contributor guidance

## Project purpose and layout

auto-ai-news aggregates public AI news feeds and publishes a dated GitHub Release each day.
The generator uses the Python standard library; it does not call an LLM.

- `scripts/generate_report.py`: feed parsing, relevance filtering, ranking, URL checks, and Markdown rendering.
- `config/sources.json`: source URLs, priorities, and disabled-source explanations.
- `tests/fixtures/`: offline RSS, Atom, and HTML examples.
- `tests/test_generate_report.py`: deterministic unit tests.
- `.github/workflows/daily-report.yml`: daily and manual generation and release publication.
- `README.md`: stable project documentation, not generated news.

## Working agreements

- Prefer small, focused changes that follow the existing standard-library design.
- Ask for confirmation before adding production dependencies.
- Treat feed titles, summaries, source names, and URLs as external input. Escape text for its output context and keep article links intact.
- Keep the ranking heuristic and reading-time limitations transparent. Ratings are not editorial quality judgments.
- Preserve source attribution, disclosure, canonical URL deduplication, and skipped-source reporting.
- Use timezone-aware UTC dates for report generation and publication.
- Add offline regression tests for behavior changes; mock network requests rather than fetching live feeds in tests.
- Keep credentials and generated reports out of commits. Do not overwrite README.md when trying the generator.
- Do not edit historical releases or trigger publication unless the user requests it.

## Verification

Run from the repository root:

```bash
python3 -m unittest discover -s tests
ruff check scripts tests
ruff format --check scripts tests
```

Use Ruff to lint and format Python. It is a development tool, not a runtime dependency.
Inspect representative generated Markdown, including long titles, special characters,
missing dates, empty reports, and skipped sources.

To run against live feeds explicitly, choose a separate output file:

```bash
python3 scripts/generate_report.py --output /tmp/daily-ai-news.md
```

Before declaring completion, confirm that the change solves the stated problem and
summarize what changed, why, and how it was verified. State any network or publication
checks that could not be completed.
