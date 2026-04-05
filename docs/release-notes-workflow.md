# Release Notes Workflow

Aervyx ships continuously from `main` (production) and `staging`. Rather
than cutting semver releases, we use calendar-versioned entries in
[`CHANGELOG.md`](../CHANGELOG.md) and matching GitHub Releases tagged
`vYYYY.MM.DD`.

## When to Update

Whenever a `staging → main` promotion PR is merged (i.e. production has
changed).

If multiple promotions happen on the same day, combine them under a single
dated entry and update the existing GitHub Release instead of creating a
new one.

## Who Updates It

The developer (or agent) who merges the promotion PR is responsible for
extending `CHANGELOG.md` and cutting/updating the GitHub Release in the
same branch or immediately after.

## Step-by-Step

1. **Merge the promotion PR to `main`.**

2. **Collect the shipped PRs.** From the repo root:

   ```bash
   # PRs merged to staging since the previous promotion
   gh pr list --state merged --base staging --limit 50 \
     --json number,title,mergedAt | jq '.[] | select(.mergedAt >= "YYYY-MM-DD")'
   ```

3. **Update `CHANGELOG.md`.** Add a new section at the top (most recent
   first) under the current date:

   ```markdown
   ## [YYYY.MM.DD]

   ### Added
   - Feature summary (#PR)

   ### Fixed
   - Bug summary (#PR)

   ### Changed
   - Behaviour change summary (#PR)
   ```

   Keep entries **user-facing** — skip refactors/chore PRs unless they
   affect operators.

4. **Commit and push to `staging`** via a feature branch + PR
   (`docs: changelog YYYY.MM.DD`) so the notes get reviewed on staging
   before promoting. The changelog edit itself does not need a matching
   main PR — it'll roll into the next promotion.

5. **Cut the GitHub Release.** Once the changelog PR has merged to
   staging (and the contents are stable), create a release pointing at
   the corresponding `main` commit:

   ```bash
   gh release create vYYYY.MM.DD \
     --title "vYYYY.MM.DD" \
     --notes-file <(sed -n '/^## \[YYYY.MM.DD\]/,/^## \[/p' CHANGELOG.md \
                    | sed '$d') \
     --target <main-commit-sha>
   ```

   Or paste the section body into the web UI at
   <https://github.com/cwallen93117/scoring-software-codex/releases/new>.

6. **Update the same release** (rather than making a new one) if more
   work lands on `main` on the same calendar day.

## Conventions

- **Ordering**: newest at the top. First line under each version is
  `### Added`, then `### Changed`, `### Fixed`, `### Removed`, `### Audits`.
- **PR references**: append `(#N)` to each bullet. This renders as a
  link on GitHub automatically.
- **Mobile-only vs web-only**: call out the surface in prose when it
  matters ("mobile home screen", "dashboard Live Tracking dropdown").
- **Version bumps**: when the Flutter app bumps its `pubspec.yaml`
  version, mention it alongside the relevant entry (`v0.2.7`).

## Automation (future)

When the volume of releases justifies it, wire a GitHub Action on
`push: main` that:

1. Diffs the PRs between the previous `vYYYY.MM.DD` tag and `HEAD`.
2. Opens a draft changelog-update PR with the new section pre-filled.
3. After merge, auto-creates the matching GitHub Release.

For now, the manual flow above is sufficient.
