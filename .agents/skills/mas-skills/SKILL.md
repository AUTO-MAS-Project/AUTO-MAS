---
name: mas-skills
description: Use when a task needs AUTO-MAS engineering conventions across frontend, UI, code style, validation and failure handling, test design, schema naming, module boundaries, function design, API contracts, data modeling, task scheduling, script adapters (MAA, SRC, MaaEnd, General, ok-script family such as Okww and OkNte, multi-engine HSR), anonymous telemetry, E2E flows, plan schedules, or game community sign-in.
---

# MAS Skills (Router)

Load this hub first, then load **only the minimum sub-skills** needed for the task. Process rules (branching, commits, changelog, PR) live in `AGENTS.md` and <https://doc.auto-mas.top/developer/> — do not duplicate them here.

## Cross-Cutting Red Lines

1. **Branching**: Always branch from latest `origin/dev` (`git fetch` first). Never branch from stale local `dev`.
2. **Release cherry-picks**: Cherry-picks to `release/{version}` MUST be small **pure-backend** fixes (judge by touched files, never commit message). Released apps hot-update backend only; never help cherry-pick or push frontend code to `release/*`.
3. **Generated OpenAPI**: Backend schema changes MUST regenerate `frontend/src/api` via the project generator. NEVER hand-edit generated files.
4. **CI pinning**: Every external GitHub Action `uses:` MUST pin a full 40-char commit SHA (`# <tag>`), and container `image:` MUST pin `@sha256:<digest>`. Only `./.github/actions/...` is exempt.
5. **Changelog**: User-visible changes MUST add one fragment via `python scripts/changelog.py add <type> <project> "<sentence>"` (rules in `AGENTS.md` / `changelog.d/README.md`).
6. **Telemetry**: Any new or changed user-visible workflow, page, lifecycle, or adapter flow MUST load `mas-telemetry` (reuse existing boundary or add collection; prose/style/read-only tasks do not add collection).
7. **Testing & Failure Integrity**: Load `mas-testing` before choosing verification or adding/editing/reviewing tests. NEVER silently swallow errors (`except Exception: pass`), overwrite corrupted config with defaults, or turn failures into success.
8. **Local Preflight**: Before committing or opening a PR, run `uv run --no-sync python scripts/pr_check.py` (pass `--skip-changelog` for docs/tests/CI-only changes) to run matching CI gates locally.

## Sub-Skill Routing Table

| Task involves | Load |
| --- | --- |
| Vue, TS, Vite, Electron renderer, routing, composables, state, styles, frontend tests | `mas-frontend-standards` |
| UI layout, Ant Design Vue, forms, tables, modals, drawers, dark mode, visual polish | `mas-frontend-ui` + `mas-frontend-standards` |
| Writing, fixing, refactoring, or reviewing non-generated code / commit style | `mas-code-standards` |
| Backend layer ownership, imports, module placement | `mas-module-boundary` |
| Function splitting, signatures, side effects, return contracts | `mas-function-design` |
| FastAPI HTTP/WS payloads, error envelopes, client compatibility | `mas-api-contract` |
| `app/models`, `app/config`, stage/commit, transactions, locks, persistence | `mas-data-model` (+ `references/config-framework.md`) |
| Shared schema / config group canonical naming | `mas-schema-naming` |
| Task trees, L1–L4 execution, `TaskBase`, scheduler locks/cancel, queue triggers | `mas-task-scheduler` |
| Script adapters (MAA, SRC, MaaEnd, General, Okww, OkNte, HSR, BetterGI, BAAH, ZzzOd, Whimbox) | `mas-script-specialized-adapter` (+ `references/blackbox-boundary.md`) |
| Script adapter Desktop Session support, saved execution session, or child-session process ownership | `mas-script-specialized-adapter` (+ `references/desktop-session.md`) and `mas-task-scheduler` |
| Plan schedule types, `PlanConfig`, `PLAN_BOOK`, plan tables | `mas-plan-schedule` |
| Game community sign-in (`app/core/community/`, `app/tools/common/community/`; Skland/Miyoushe/Kuro/Taygedo) | `mas-game-community` |
| Observable user workflows, anonymous analytics | `mas-telemetry` |
| Creating/reusing worktrees, Python environments, or duplicate `.venv` cleanup | `mas-worktree` |
| Choosing verification or adding/editing/reviewing tests | `mas-testing` |
| E2E, Playwright, real game/emulator runs, PR verification hand-off | `mas-e2e` |
| User tutorials, Playwright screenshot refresh | `mas-doc-tutorial` (+ `mas-e2e`) |
| Red CI, PR gates, `skip-changelog`, `.github/workflows` | `mas-ci-checks` |

**Combined order** (when multiple apply): `mas-frontend-standards` → `mas-frontend-ui` → `mas-code-standards` → `mas-module-boundary` → `mas-data-model` → `mas-schema-naming` → `mas-function-design` → `mas-api-contract` → `mas-task-scheduler` → `mas-script-specialized-adapter` → `mas-plan-schedule` / `mas-game-community` → `mas-telemetry` → `mas-e2e` → `mas-ci-checks`.

## Output Requirements

1. State which sub-skills were selected and why (keep to the minimum set).
2. Prefer compatibility-first changes on legacy modules unless broad refactoring is requested.
3. For frontend tasks, explicitly note whether `mas-frontend-standards` and `mas-frontend-ui` were loaded; report Vue baseline/final line counts.
4. For observable workflow changes, state the telemetry boundary (reused / extended / intentionally omitted) and report only executed verification.
5. On black-box adapter boundary hits, warn `"This may violate the MAS development norms"` with `file:line` evidence and an alternative (non-blocking).
