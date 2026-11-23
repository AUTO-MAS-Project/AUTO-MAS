---
name: mas-ci-checks
description: Use when an AUTO-MAS PR is red in CI, when diagnosing a dev-PR gate failure, when a workflow needs a skip-changelog or changelog-maintenance label, or when editing .github/workflows, .github/actions, scripts/changelog.py or scripts/check_reverts.py.
---

# MAS CI Checks

## Objective
Diagnose red PR gates from CI logs, separate code issues from runner/mirror infra noise, and reproduce locally via `scripts/pr_check.py`.

## Gate Map (PR with base `dev`)

`format-check` and `check-reverts` run on base `dev`; `check-changelog`, `check-uv-lock` and `ci-package` run on every PR, including `release/*` cherry-pick PRs (where `check-changelog` adds `--dev-ref origin/dev` to reject `dev`-only commits).

| Workflow | Job name | What actually runs | Local reproduction |
| --- | --- | --- | --- |
| `format-check.yml` | 格式检查 | `ruff format --check .` + frontend `lint` / `typecheck` / `format:check` / `audit:i18n` / Vue 500-line check | `uv run --no-sync python scripts/pr_check.py` |
| `check-changelog.yml` | 检查更新日志碎片与版本号 | `scripts/changelog.py check --pr-base origin/<base> --pr-kind normal` (+ `--skip-changelog` / `--maintenance` by label) | `pr_check.py`（加 `--skip-changelog` 对应标签；先 `git fetch origin dev --tags`） |
| `check-uv-lock.yml` | 检查 uv.lock 与依赖清单一致 | `uv lock --check` | `pr_check.py` |
| `python-tests.yml` | Ubuntu 与 Windows 全量回归 | `uv run --no-sync python -m pytest tests -q` on Ubuntu + Windows | `uv sync --locked --group dev && uv run --no-sync python -m pytest tests -q` |
| `check-reverts.yml` | 误删近期代码提示 | Annotates deleted lines merged by others within 14 days (**hint only, never fails**) | Not needed |
| `label-changelog.yml` | 同步碎片标签 | `scripts/label_changelog.py` (`continue-on-error: true`) | Not needed |
| `ci-package.yml` | 构建未签名 Windows 验证包 | Full frontend + Electron + backend build (~4 min; skipped on `**.md` / `docs/**`-only diffs) | Only run locally when touching Electron/packaging |
| `sync-cnb.yml` | sync | Mirrors repo to cnb.cool | `gh run rerun <run-id>`; never a code problem |

`build-app.yml`, `prepare-release.yml`, `absorb-changelog.yml`, `mirrorchyan*.yml`, `weekly-format.yml` are release/scheduled jobs, not PR gates.

## Local Preflight

1. **Routine static gates**: run `uv run --no-sync python scripts/pr_check.py` (add `--skip-changelog` for docs/tests/CI-only PRs, `--all` to run every local gate). It auto-selects matching CI gates (including `ruff` via `uv.lock`, Electron `tsc`, `i18n`, Vue baseline, and `changelog.py`) and prints exact fix commands on failure.
2. **Full Python tests**: `uv run --no-sync python -m pytest tests -q`. Reproduce platform-specific failures on the matching OS before changing tests.
3. **Changelog labels**:
   - User-visible change: `uv run --no-sync python scripts/changelog.py add <type> <project-key> "<sentence>"`.
   - Truly user-invisible work: `gh pr edit <n> --add-label skip-changelog` (triggers workflow automatically; no empty commit needed).
   - `changelog-maintenance` (`--maintenance`) is maintainer-only for direct `CHANGELOG.md` reorganization; never put it on a normal PR.

## Rules

1. **Read the log first**: `gh run view <run-id> --log-failed` gives the exact file, line, and expected layout. Do not guess.
2. **No force push**: append a `style(...)` / `fix(...)` commit and let the PR squash on merge.
3. **Pin every external reference**: `uses:` uses a 40-char commit SHA with `# <tag>`, `image:` uses `@sha256:` across `.github/` and `.cnb.yml`.
4. **Mirror infra != code failure**: `sync-cnb` errors (e.g. `cannot lock ref`) only need `gh run rerun`.
5. **Never weaken gates**: do not delete tests, relax checks, or add `continue-on-error` to turn CI green.

## Anti-Patterns

- Running system `ruff` / `oxfmt` instead of `uv run --no-sync` / project Yarn 4.
- Treating `sync-cnb` mirror failures as code regressions.
- Abusing `skip-changelog` on user-visible changes, or pushing an empty commit after adding a label.
- Assuming `yarn typecheck` covers `frontend/electron/` (use `pr_check.py` or `tsc -p tsconfig.electron.json --noEmit`).
