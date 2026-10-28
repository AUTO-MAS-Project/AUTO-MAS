---
name: mas-ci-checks
description: Use when an AUTO-MAS PR is red in CI, when reproducing a dev-PR gate locally before pushing, when a workflow needs a skip-changelog or changelog-maintenance label, or when editing .github/workflows, .github/actions, scripts/changelog.py or scripts/check_reverts.py. Covers every gate that runs on a PR to dev and the exact local command for each.
---

# MAS CI Checks

## Objective
Turn the dev-PR gates into local commands, and decide "our change is wrong" versus "runner or mirror infra is wrong" before touching code.

## Gate Map (PR with base `dev`)

`format-check` and `check-reverts` are filtered to base `dev`; `check-changelog`, `check-uv-lock` and `ci-package` run on every PR, including `release/*` cherry-pick PRs, where `check-changelog` also adds `--dev-ref origin/dev` to reject `dev`-only commits.

| Workflow | Job name | What actually runs | Local reproduction |
| --- | --- | --- | --- |
| `format-check.yml` | 格式检查 | `uv sync --locked` then `uv run --no-sync ruff format --check .`; in `frontend/`: `yarn lint` (oxlint), `yarn typecheck` (vue-tsc), `yarn format:check` (oxfmt) | see Local Reproduction |
| `check-changelog.yml` | 检查更新日志碎片与版本号 | fetches base, `dev` and all tags, then `python scripts/changelog.py check --pr-base origin/<base> --pr-kind normal` plus `--skip-changelog` / `--maintenance` when the PR carries the matching label | `git fetch origin dev --tags`, then the same command with `--pr-base origin/dev` and the same label flags; omitting a flag the PR has gives a false red |
| `check-uv-lock.yml` | 检查 uv.lock 与依赖清单一致 | `uv lock --check` | same |
| `python-tests.yml` | Ubuntu 与 Windows 全量 Python 回归测试 | installs locked dev dependencies with `uv sync --locked --group dev`, then runs `uv run --no-sync python -m pytest tests -q` on both `ubuntu-latest` and `windows-latest` | `uv sync --locked --group dev`, then `uv run --no-sync python -m pytest tests -q` |
| `check-reverts.yml` | 检查是否删掉了他人近期合入的代码 | blames every deleted line; lines another author merged within 14 days are annotated in Files changed **as a hint only, it never fails**. Skipped entirely for `Release v*` PRs | not needed; the job is informational |
| `label-changelog.yml` | 同步碎片标签 | `python scripts/label_changelog.py`, `continue-on-error: true` | not needed; failure does not judge the PR |
| `ci-package.yml` | 构建未签名 Windows 验证包 | real windows-latest build of frontend + Electron + backend, ~4 minutes; skipped for `**.md` / `docs/**`-only diffs | expensive; only re-run locally when the change touches Electron or packaging |
| `sync-cnb.yml` | sync | mirrors the repo to cnb.cool after push / branch create | `gh run rerun <run-id>`; never a code problem |

`build-app.yml`, `prepare-release.yml`, `absorb-changelog.yml`, `mirrorchyan*.yml`, `weekly-format.yml` run on `main` / `release/*` / release PRs / schedules. They are not PR gates; do not judge a feature PR by them.

## Local Reproduction
1. Python format: `uv sync --locked`, then `uv run --no-sync ruff format --check <files>`; if it fails, `uv run --no-sync ruff format <files>`. **Always go through uv**: the ruff version is pinned by `uv.lock` (`uv run ruff --version`). A system-wide ruff formats differently, so the local run passes while CI stays red.
2. Python tests: `uv sync --locked --group dev`, then `uv run --no-sync python -m pytest tests -q`. This matches the `python-tests.yml` matrix on Ubuntu and Windows; when a failure is platform-specific, reproduce it on the corresponding OS before changing the test.
3. Frontend: `cd frontend && yarn lint && yarn typecheck && yarn format:check`.
4. `yarn typecheck` only runs `vue-tsc -p tsconfig.app.json --noEmit`, so it does **not** cover `frontend/electron/`. For Electron main-process changes (`electron/services`, `electron/ipc`) also run `node node_modules/typescript/bin/tsc -p tsconfig.electron.json --noEmit` from `frontend/`.
5. Changelog fragment: for a user-visible change run `python scripts/changelog.py add <type> <project-key> "<sentence>"`; for genuinely user-invisible work (docs, CI, tests, invisible refactor) label the PR `skip-changelog` with `gh pr edit <n> --add-label skip-changelog`. The workflow also triggers on `labeled` / `unlabeled`, so no extra empty commit is needed. `changelog-maintenance` maps to `--maintenance` and only lets a maintainer reorganize `CHANGELOG.md` directly (e.g. after `python scripts/changelog.py sync`); never put it on a normal feature or fix PR.
6. Dependency changes: `uv lock --check`.
7. Format-only repairs: reformatting rewraps lines, so after `ruff format` confirm with `git diff` that only your own hunk moved.

## Rules
1. Read the log before editing: `gh run view <run-id> --log-failed` gives the exact file and line plus the expected layout. Do not guess the rewrap.
2. Do not force push to repair CI (root `AGENTS.md` forbids force push outright). Append a `style(...)` commit and let the PR be squashed on merge.
3. Every `uses:` / `image:` reference in workflows, composite actions and CNB pipelines stays pinned to a full 40-character commit SHA or `@sha256:` digest; see `mas-skills` Project Rule Areas item 7.
4. A `sync` failure such as `remote: error: cannot lock ref 'refs/heads/<branch>': reference already exists` is mirror infra: rerun the workflow and keep the code untouched.
5. Never turn CI green by deleting tests, weakening a check, or adding `continue-on-error`.

## Anti-Patterns
- Reproducing a format failure with the system ruff or oxfmt instead of the `uv.lock` version.
- Treating the CNB mirror job as a code failure.
- Labeling a user-visible change `skip-changelog` to get past the fragment gate.
- Pushing an empty commit after adding a label.
- Assuming `yarn typecheck` proves Electron main-process types are sound.
