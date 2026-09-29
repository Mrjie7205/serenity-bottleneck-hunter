# Changelog

## v0.2.0 — 2026-09-29

Core tools, reproducible examples and documentation. The seven-step research workflow, nine archetypes, timing thresholds, valuation scoring and existing Codex/Claude entry points remain in place. Cockpit and leader-lens extensions are not included in this release.

### Reliability

- Make report rendering and staged-file validation work in a standalone clone, including paths with spaces or Chinese characters.
- Normalize US and Shanghai/Shenzhen tickers only at provider boundaries. Preserve Hong Kong suffixes.
- Use explicit provider adjustment data: AKShare qfq, Yahoo auto-adjusted prices, or EODHD adjusted-close factors. Do not infer corporate actions from large returns.
- Reject invalid price bars, expose sample/adjustment warnings, return full six-month range endpoints, and preserve missing values rather than inventing quotes.
- Replace the hard-coded A-share earnings forecast year with next calendar year's EPS column. Do not substitute a different year's estimate when absent.
- Preserve a scan's actual stage label in reports. Correct recorded currencies and include report date/theme metadata.
- Validate staged Git blobs, including Unicode paths; associate company names with report structure, retain unresolved-identity warnings and reject confirmed mismatches.
- Fail explicitly for invalid requested scan files; add `--tracking` and `--strict` report validation.
- Install opt-in repository hooks without overwriting existing hooks or custom hook configurations.
- Invalidate old price caches across the adjustment-policy change; reuse new scoring cache only within the same day.

### Example and packaging

- Add a complete offline report definition, two previously public historical snapshots, an empty tracking template and provenance.
- `python scripts/run_demo.py` generates and strictly validates a report without network calls or changes to the public historical registry.
- Default reports use the bundled template and contain no dead local-Cockpit links. A `cockpit_url` can be supplied explicitly by users who have their own viewer.
- Add Python dependencies, A-share instructions, automated checks and reproducible ZIP / `.skill` archives with checksums.

### Upgrade notes

Existing relative SPEC paths now resolve from the skill root. Absolute paths remain supported. Scripts no longer depend on a sibling private repository. Prefer a separate `tracking_file` for personal research; the existing `tracking/forward_picks.csv` remains the default for backwards compatibility.

Source labels now distinguish adjusted providers. A-share EODHD fallback produces a quality warning. Provider availability, certificate problems and data coverage are not guaranteed; no certificate verification is disabled. Source-adjusted histories can change calculated indicators compared with v0.1 raw histories even though the calculation thresholds are unchanged.

The 418 public historical records and older scan/scorecard assets are preserved as dated archives. No new private research collection is published. The bundled report is an historical software demonstration, not current market data or a new recommendation. No full live-data refresh accompanies this release.

## v0.1.0 — 2026-07-06

Initial public release, including Codex installation instructions and UI metadata.
