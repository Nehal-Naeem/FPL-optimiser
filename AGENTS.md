# Project agent guidance

## Documentation maintenance

- Update the root README.md in the same change whenever user-facing functionality,
  recommendation/scoring/optimisation logic, APIs, configuration, data flow or
  infrastructure changes. If an internal-only change does not affect the README,
  leave it unchanged.
- Treat README.md as the current product/architecture overview. Explain actual
  behaviour, inputs, objectives, constraints and material limitations; distinguish
  relative viability, historical measurements and experimental projected points.
- Ground documentation in the code and relevant deployment configuration. Do not
  describe implemented-but-undeployed work as live production. Verify deployment
  claims against recorded or read-only cloud evidence, and identify uncertainty.
- Keep detailed projection mathematics and operational procedures in their
  existing guides; update those guides when their subject changes and link them
  from the README. Store image tags, execution IDs, dated test counts and rollout
  incidents in dated deployment records rather than the main overview.
- Preserve explicit production/development dataset separation and use safe local
  wrappers in documented examples. Do not include credentials, tokens or backup
  data in documentation or source control.
- For documentation-only changes, check relative links, examples, consistency and
  `git diff --check`. Do not deploy, change cloud resources or run ingestion merely
  to validate documentation.

This is a maintenance instruction for contributors and coding agents, not a
background documentation-update service. It does not authorise deployments or
other infrastructure changes beyond the user's task.

## Git practices

- Start with `git status --short`, the current branch and relevant diffs. This
  workspace may contain substantial uncommitted work from earlier tasks. Preserve
  it; do not revert, overwrite or include unrelated changes in your work.
- Prefer short-lived, descriptive branches such as `feat/five-week-planner`,
  `fix/history-deduplication` or `docs/recommendation-methodology` for work intended
  for review. Do not switch branches over a dirty working tree or move existing
  changes into a worktree without checking that they are preserved. Avoid direct
  commits to `main` unless that workflow is explicitly requested.
- Keep changes and commits focused on one coherent purpose. Include the relevant
  code, meaningful tests and documentation together. Separate unrelated refactors
  from ingestion, modelling, optimiser or deployment changes.
- Stage explicit paths or reviewed hunks rather than using `git add .` or
  `git add -A` in a shared, dirty workspace. Review `git diff --cached` and
  `git diff --cached --check` before committing; confirm only intended files and
  changes are staged. Preserve any files the user already staged.
- Never add credentials, service-account keys, OAuth tokens, `.env` files,
  production exports, deployment backups or local database snapshots. Keep virtual
  environments, `node_modules`, build output, dbt packages/targets, caches and test
  artifacts out of commits. Check ignore rules before adding generated files;
  `.gitignore` does not protect secrets that are already tracked. Preserve existing
  intentional seed/history fixtures and review new fixtures for necessity and size.
- Commit dependency manifests and their lockfiles together when dependencies
  change, including the frontend and dbt lockfiles or pinned Python requirements
  as applicable. Do not regenerate locks or upgrade packages for unrelated work.
- Run validation appropriate to the change using the README and subsystem guides.
  Explain the behaviour changed and validation performed in commit/PR descriptions.
  Use concise, descriptive commit subjects, for example
  `fix(dbt): prevent duplicate player-fixture records`. Documentation-only changes
  do not require cloud builds, ingestion or the full application suite.
- Before integrating remote changes, inspect the branch/divergence and protect
  local work. Do not automatically stash user changes, rewrite shared history,
  force-push, reset hard, clean untracked files or discard conflict sides. Resolve
  conflicts by understanding both changes and rerun affected checks; seek explicit
  authorisation before destructive Git operations.
- The user has given standing authorisation to commit and push completed
  incremental features after relevant validation passes. Include their tests and
  documentation, use the current task branch and `origin`, and report the commit
  and pushed branch. Do not ask for the same authorisation again. Leave unrelated
  or unfinished work out of feature commits; report blockers or failed checks
  instead of pushing an incomplete feature as finished.
- Standing commit/push authorisation does not authorise merging branches, tagging
  releases, rewriting history or bypassing protected-branch requirements. Do not
  change remotes, global Git configuration or authentication settings as incidental
  cleanup. Do not bypass hooks or required checks.
- Keep Git operations separate from production operations. A commit, push or merge
  does not authorise BigQuery writes, IAM changes, job execution or deployment.
  For authorised deployments, use immutable image identifiers and record the code
  revision and whether the working tree was dirty alongside deployment evidence.
  Never claim that a commit is deployed without verifying the deployed workload.
