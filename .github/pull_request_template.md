## Summary

<!-- What does this change, and why? One or two sentences a reviewer can read first. -->

## Issues

<!-- "Refs #123" for partial work. Use "Closes #123" only when that issue's own checklist is fully met. -->

## Type of change

- [ ] Bug fix
- [ ] New feature or screen
- [ ] Planner or training-science change
- [ ] API change (new or changed endpoint, response model)
- [ ] Data layout or migration
- [ ] Docs, tests or tooling only

## Planner output

<!-- Skip if the planner is untouched. -->
- [ ] Plans for riders who do not use this feature are **unchanged** (the characterization golden, `tests/characterize_planner.py`, is unchanged or the change is explained below).
- [ ] If existing plan output changes, say exactly who is affected and how:

## Training science

<!-- Skip if there are no physiology, load or pacing numbers. -->
- [ ] Every number comes from a named, published method, cited in the code and in `docs/SCIENCE.md` (or the feature's doc), with a stated confidence.
- [ ] Anything I could not source is left out, or labelled as a heuristic or "verify".

## How I tested it

- [ ] Python: `python -m pytest tests/<files>` for what I touched (full gate: `tools/gate.sh`)
- [ ] Web: `cd web && pnpm typecheck && pnpm lint && pnpm test && pnpm build`
- [ ] Browser: a Playwright test for a new screen, appended to `web/e2e/smoke.spec.ts`
- [ ] A test that failed before the fix (bug fixes)
- [ ] New or changed endpoints have a response model; I regenerated `tests/api_contract.json` (`python tools/dump_openapi.py > tests/api_contract.json`) and `web/src/api/schema.d.ts` (`bash tools/gen-api-types.sh`)
- [ ] Tests that save state through the API (targets, thresholds, profile files) clean it up afterwards

## Housekeeping

- [ ] Commits are signed off (`git commit -s`, see `.github/CONTRIBUTING.md`)
- [ ] New source files carry the license header
- [ ] `CHANGELOG.md` has a line under *Unreleased* (user-visible changes)
- [ ] Docs updated where behaviour changed (`docs/ROADMAP.md` known gaps, `docs/DATA.md` for stored data)
- [ ] No secrets, API keys, tokens or personal data in the diff, tests or fixtures
- [ ] No content copied from sources we cannot redistribute (see "What We Reject" in `.github/CONTRIBUTING.md`)

## Screenshots

<!-- For UI changes: light and dark, and a phone width if the layout changed. -->

## Not verified

<!-- Be plain about what was not run or not checked (live services, real devices, real riders' data). -->
