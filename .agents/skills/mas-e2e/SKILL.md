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

- Use `frontend/e2e/run.mjs` as the only per-run Playwright launcher and `frontend/e2e/real-batch.mjs` as the only multi-adapter launcher; both go through `run.mjs` per target. `run.mjs` creates the isolated data root, starts the backend and Vite, selects the requested grep, and removes the temporary root after the run.
- Use `yarn e2e:check` before adding or changing a flow. Run browser flows from `frontend/`; use `yarn e2e --grep '<regex>'` for a selected tag and `yarn e2e:real --grep '<regex>'` for an author-local real run.
- E2E is a local developer convenience tool, not a CI gate. Select only the flows relevant to the changed user path and run them before or during PR review.

## Command matrix

Run from `frontend/`; the only launchers are `run.mjs` and `real-batch.mjs`. Never call `playwright test` directly.

| Need | Command |
| --- | --- |
| Harness contract + E2E typecheck | `yarn e2e:check` |
| All non-real flows | `yarn e2e` |
| Only the flows for the changed path | `yarn e2e --grep '@queue\|@scheduler'` |
| Watch mode while editing | `yarn e2e:ui` |
| Keep the run root for debugging | `$env:AUTO_MAS_E2E_KEEP_ROOT=1; yarn e2e` |
| HTML report | `yarn e2e:report` |
| One real script/account/game run | `yarn e2e:real` |
| Every enabled adapter, sequentially | `yarn e2e:real:all --list` / `yarn e2e:real:all` / `yarn e2e:real:all --only MaaConfig,SrcConfig` |

Tags: `@smoke @init @queue @scheduler @settings @history @recovery`, plus `@real` for author-local runs. Real commands in a worktree need the developer's main checkout as the seed source (`AUTO_MAS_E2E_TEMPLATE_ROOT`). Batch results land in `test-results/real-batch/<n>-<type>-<account>/`.

## After opening a PR: hand the tools to the developer

Opening or updating a PR is not the end of the task. While it waits for review, do this instead of waiting silently:

1. Name the flows that cover what the PR changed and print them as concrete commands from the matrix above; never just "run the e2e suite".
2. Say what each command produces (screenshots, HTML report, `real-e2e-summary.json`, the kept run root) so the developer can attach evidence or debug.
3. Ask which one to run now, and run any non-real command yourself once the developer agrees.
4. Separate what only the author can run: `@real` needs their emulator, game, and account. Never claim a real result you did not observe, and never treat "the code looks right" as coverage.
5. When the change touches `app/task/**`, a script adapter, scheduling, or the emulator and no `@real` proof is attached yet, say so and name the missing command.

Repeat the offer after a later push when the changed path changed too.

## Add a flow

1. Start from the user action and the smallest observable assertion. Prefer the public UI, MAS HTTP/WebSocket contracts, task terminal status, and public user result.
2. Put a stable cross-feature flow in `frontend/e2e/<scenario>.pw.ts`; put a PR-only regression in the PR branch and remove it after verification unless it is a reusable contract.
3. Tag the flow with `test.describe('@<scope>', ...)`; real game side effects additionally require `@real`. Use `app.goto()` and `app.evidence()` from `fixtures.ts`.
4. Wait for visible state, API responses, WebSocket events, or terminal task status with a timeout. Keep real startup and game delays separate from short injected debounce or retry delays.
5. Attach only selected screenshots and `real-e2e-summary.json` to a PR when useful. Record the commit SHA, dirty state, command, preconditions, result, evidence path, and uncovered branches.

## Real-run contract

The author-local runner accepts a script UUID, enabled user UUID, and configured account name. Everything it needs comes from the developer's own machine — the repository ships no game resources, script installs, or test accounts; the "config" it uses is the developer's real MAS configuration. It copies only the selected public MAS configuration and opaque script data into a temporary root, removes notifications from the copied user, and leaves the source `config/` and `data/` untouched. The runner has an explicit allowlist for every current script config type; an unlisted type fails with an instruction for the script author to add its prerequisites and harness assertion. A script may bind an emulator; when it does, the real flow waits for the MAS emulator operation event and device readiness. A script without a binding skips emulator steps. BetterGI and other supported script lines use the same contract when their installation and configuration are available locally.

The real runner takes a machine-wide atomic lock so two local game runs cannot compete for one installation or emulator. If a forced termination leaves a lock file, confirm no real run is active before removing it manually.

Declare a new script line's local prerequisites in its adapter documentation or PR: installed executable, required config/data directories, whether an emulator is needed, and the public result that proves completion. Extend the seed self-check before adding special copying rules. Keep private upstream formats opaque; MAS owns account selection, scheduling, emulator lifecycle, cleanup, and evidence.

## Evidence and limits

Evidence is proof of the selected commit, account, script, environment, and assertions. A passing run does not prove an entire PR or another script line. A failed run identifies the failed phase only until external state, baseline comparison, and source tracing rule out emulator, account, network, game update, or upstream causes. Never include passwords, cookies, tokens, notification secrets, or unreviewed full reports in shared evidence. The tool never accesses CI credentials, shared game resources, or a maintainer-provided simulator.
