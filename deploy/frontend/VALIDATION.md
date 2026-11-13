# Frontend validation

Validated locally on November 12, 2026 (New York time; November 13 UTC).

- 25 Python tests passed, covering exhaustive optimizer comparisons, coupled
  transfers, sale-aware budget boundaries, score/money/transfer tie-breaking,
  strict replacement filtering, unscored players, availability policy, invalid
  squads, infeasibility, timeout status, import errors, cache behavior, and
  dataset-version conflicts.
- Eight Playwright browser tests passed in installed Chrome, across desktop and
  iPhone-sized viewports. These exercise the real backend optimizer with
  deterministic test-only data: import, editing, replacement application,
  transfer and ideal optimization, infeasibility, upstream errors, and recovery
  after a dataset-version conflict. The tested mobile flow has no horizontal
  document overflow.
- TypeScript checking and Vite production build passed. `npm install` reported
  zero known npm vulnerabilities for the installed dependency tree.
- The updated dbt project parsed successfully using local dbt
  `2.0.0-alpha.5`. New data tests were not deployed or executed in BigQuery.
  The existing cloud dbt runtime remains `1.10.15`; test arguments use the
  `arguments` syntax supported by that version.
- Live production API smoke test, using existing local Application Default
  Credentials: `/api/players` returned 672 catalog players, 389 scored, and
  fresh metadata. A £100m ideal squad returned `OPTIMAL`, 15 players, total
  viability `11.692731120858015`, and £10.2m remaining. Public team import using
  the repository's example ID returned 15 players; transfer mode with a one-move
  cap returned `OPTIMAL` with one transfer.
- Python bytecode compilation and `git diff --check` passed.

Local Python tests ran on the available Python 3.9.6 interpreter in an isolated
`.venv-web`; new environments and the container target Python 3.12. The local
interpreter emits Python support and LibreSSL warnings. Docker is not installed
in this environment, so the container image was not built or run. No service,
IAM grant, dataset, or scheduled pipeline was changed.

Visual inspection through the computer-use tool could not run because OS
computer-use permissions were not granted. Automated desktop/mobile browser
checks completed successfully; this does not substitute for a manual design
review.

## Fixture strips and UI copy update

- 30 backend tests passed, including upcoming-match filtering, stable ordering,
  duplicate prevention, double gameweeks, undated matches, venue-specific
  difficulty, fixture-aware versioning, and fixture serialization in player,
  replacement, and optimizer responses.
- Ten desktop/mobile browser tests passed. Fixture coverage includes all three
  player views, keyboard focus, click/tap interaction, Escape and outside-click
  dismissal, TBC dates, empty schedules, and mobile overflow checks.
- TypeScript checking, Vite production build, and `git diff --check` passed.
- The restarted local API returned HTTP 200 through the frontend proxy. All 672
  live catalog players included upcoming fixtures, including unscored players;
  each list contained at most five unique fixture IDs. Fixture freshness metadata
  was populated from the raw fixture table.
- Promotional headings, slogans, sidebar copy, and the footer tagline were
  removed. Neutral functional copy and the compact page heading are in place.
- Browser tests now use ports 8002 and 5174, allowing them to run independently
  of the user's app on ports 8000 and 5173. No cloud deployment was performed.

## Fixture toggles and hidden player statistics

- Eighteen desktop/mobile browser tests passed with two workers. The suite
  covers first/second-click fixture toggling, switching and reopening fixtures,
  keyboard and actual touch activation, and dismissal without a focus race.
- Player-name tests confirm mouse single-click leaves statistics hidden,
  double-click toggles them, Enter/Space works, and touch taps toggle them.
  Tests cover squad cards, both replacement-player views, optimizer results,
  independent expanded panels, edit/fixture/replacement controls, and mobile
  overflow with panels expanded.
- Form and points-per-gameweek percentiles use the existing API/BigQuery fields.
  Tests verify one-decimal percentage formatting, zero percentile, missing
  values, and retention of the squad-card score breakdown. No production
  backend, dbt model, API contract, or scoring formula changed.
- TypeScript checking, the Vite production build, and `git diff --check` passed.
  The existing frontend at port 5173 returned HTTP 200; no restart was needed.
- An initial five-worker run stalled during one Chrome worker startup. It was
  interrupted, its test servers were stopped, and the entire suite passed after
  limiting browser workers to two.

## Discreet player popovers

- Twenty-one desktop/mobile browser tests passed; one desktop-only hover test
  was intentionally skipped in the mobile project. The full suite completed in
  9.5 seconds using two workers.
- Coverage includes hover previews and movement into the popover, click-to-pin,
  second-click closing, Escape/outside-click dismissal, one open player at a
  time, keyboard focus and restoration, and actual mobile touch toggles.
- Tests verify card bounds are unchanged when opening statistics or expanding
  the secondary score breakdown. Replacement popovers are portalled to the body
  outside scrolling containers; scrolling dismisses them. A 320px-wide viewport
  test checks popup bounds, overflow, scrolling, and removal of its anchor.
- Existing percentile values, unavailable-value formatting, fixture toggles,
  editing, replacements, and both optimizer modes remain covered. Double-click
  handlers and instructions were removed from the production UI.
- TypeScript checking, the Vite production build, and `git diff --check` passed.
  No backend, API, dbt model, or scoring changes were required.

## Player info icon alignment

- Replaced the font-rendered circled letter with a fixed-size inline SVG and
  aligned it beside the player-name label using a four-pixel flex gap.
- Scoped replacement metadata span rules so nested player-name controls no
  longer inherit block layout, top margins, or smaller metadata font sizes.
- Twenty-three desktop/mobile browser tests passed; the mobile-only exclusion
  of the desktop hover test remains intentional. New checks verify 12px square
  icons, vertical alignment, spacing, metadata-style isolation, wrapped names,
  and continued popover activation in recommended-player rows.
- The broader suite exposed a delayed scroll event dismissing a newly opened
  mobile popover. Scroll dismissal now checks that the anchor actually moved;
  the full suite passed after this correction.
- TypeScript checking, production build, and `git diff --check` passed. The
  existing frontend on port 5173 returned HTTP 200.
