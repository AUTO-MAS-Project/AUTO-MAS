---
name: mas-e2e
description: >-
  Design, add, review, or run AUTO-MAS end-to-end flows that exercise the
  public MAS scheduling path, including isolated browser checks and author-local
  real script, account, emulator, and game runs with evidence.
---

# MAS E2E

Use this skill when a change needs an end-to-end proof of a user path, a PR-specific one-off flow, or a local real run through MAS scheduling.

## Entry point

- Use `frontend/e2e/run.mjs` as the only Playwright launcher. It creates the isolated data root, starts the backend and Vite, selects the requested grep, and removes the temporary root after the run.
- Use `yarn e2e:check` before adding or changing a flow. Run browser flows from `frontend/`; use `yarn e2e --grep '<regex>'` for a selected tag and `yarn e2e:real --grep '<regex>'` for an author-local real run.
- E2E is a local developer convenience tool, not a CI gate. Select only the flows relevant to the changed user path and run them before or during PR review.

## Add a flow

1. Start from the user action and the smallest observable assertion. Prefer the public UI, MAS HTTP/WebSocket contracts, task terminal status, and public user result.
2. Put a stable cross-feature flow in `frontend/e2e/<scenario>.pw.ts`; put a PR-only regression in the PR branch and remove it after verification unless it is a reusable contract.
3. Tag the flow with `test.describe('@<scope>', ...)`; real game side effects additionally require `@real`. Use `app.goto()` and `app.evidence()` from `fixtures.ts`.
4. Wait for visible state, API responses, WebSocket events, or terminal task status with a timeout. Keep real startup and game delays separate from short injected debounce or retry delays.
5. Attach only selected screenshots and `real-e2e-summary.json` to a PR when useful. Record the commit SHA, dirty state, command, preconditions, result, evidence path, and uncovered branches.

## Real-run contract

The author-local runner accepts a script UUID, enabled user UUID, and configured account name. It copies only the selected public MAS configuration and opaque script data into a temporary root, removes notifications from the copied user, and leaves the source `config/` and `data/` untouched. The runner has an explicit allowlist for every current script config type; an unlisted type fails with an instruction for the script author to add its prerequisites and harness assertion. A script may bind an emulator; when it does, the real flow waits for the MAS emulator operation event and device readiness. A script without a binding skips emulator steps. BetterGI and other supported script lines use the same contract when their installation and configuration are available locally.

The real runner takes a machine-wide atomic lock so two local game runs cannot compete for one installation or emulator. If a forced termination leaves a lock file, confirm no real run is active before removing it manually.

Declare a new script line's local prerequisites in its adapter documentation or PR: installed executable, required config/data directories, whether an emulator is needed, and the public result that proves completion. Extend the seed self-check before adding special copying rules. Keep private upstream formats opaque; MAS owns account selection, scheduling, emulator lifecycle, cleanup, and evidence.

## Evidence and limits

Evidence is proof of the selected commit, account, script, environment, and assertions. A passing run does not prove an entire PR or another script line. A failed run identifies the failed phase only until external state, baseline comparison, and source tracing rule out emulator, account, network, game update, or upstream causes. Never include passwords, cookies, tokens, notification secrets, or unreviewed full reports in shared evidence. The tool never accesses CI credentials, shared game resources, or a maintainer-provided simulator.
