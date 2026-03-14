# Repository Guidelines

## Project Structure & Module Organization
- `main.py`: backend entrypoint (FastAPI + WebSocket).
- `app/`: backend source.
  - `api/` route handlers (`/api/scripts`, `/api/dispatch`, `/api/history`, etc.).
  - `core/` runtime managers (`Config`, `TaskManager`, timers, startup).
  - `task/` script executors by type (`MAA`, `general`, `maaend`).
  - `models/` Pydantic schemas and config models.
  - `services/` notification, system, update services.
  - `utils/` logging, websocket client manager, process helpers.
- `frontend/`: Electron + Vue + TypeScript app.
- `dev/`: lightweight local test pages (for example `dev/maaend-monitor.html`).
- `config/`, `data/`, `history/`, `debug/`: runtime/configuration artifacts.

## Build, Test, and Development Commands
- Backend (project-local conda env preferred):
  - `.\.conda\python.exe main.py` — run backend on port `36163`.
  - `.\.conda\python.exe -m py_compile app\task\maaend\*.py` — quick syntax check.
- Frontend (run in `frontend/`):
  - `yarn dev` — Vite + Electron dev mode.
  - `yarn dev:fullstack` — start backend + frontend together.
  - `yarn lint` / `yarn lint:fix` — ESLint checks/fixes.
  - `yarn format` — Prettier formatting.
  - `yarn build` — production build.

## Coding Style & Naming Conventions
- Python: 4-space indentation, type hints where practical, async-first for IO paths.
- Keep API response shape consistent with `OutBase` and existing schema models.
- Reuse existing modules before introducing new abstractions; follow same status/message wording patterns across script types.
- Frontend: TypeScript + Vue 3 composition style, ESLint + Prettier as source of truth.

## Testing Guidelines
- No large automated test suite is currently enforced in this repo.
- Minimum expectation for backend changes:
  - syntax check (`py_compile`);
  - endpoint smoke check against modified routes;
  - WebSocket/dispatch/history behavior validation when touching task execution.
- For MaaEnd-related work, use `dev/maaend-monitor.html` for I01-I08 acceptance flow.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history:
  - `feat(scope): ...`
  - `refactor(scope): ...`
  - examples: `feat(maaend-runtime): ...`, `refactor(maaend-manager): ...`.
- PRs should include:
  - concise problem/solution summary,
  - affected modules/endpoints,
  - manual verification steps,
  - screenshots or logs for UI/behavior changes,
  - linked issue/milestone when applicable.

## Security & Configuration Tips
- Do not commit secrets, local tokens, or machine-specific paths.
- Treat `config/` and runtime data as environment-specific; prefer minimal, reversible config changes.
