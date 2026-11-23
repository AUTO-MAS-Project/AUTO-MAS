"""scripts/pr_check.py 门禁路由与失败指引契约测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "pr_check.py"
SPEC = importlib.util.spec_from_file_location("pr_check", MODULE_PATH)
assert SPEC and SPEC.loader
pr_check = importlib.util.module_from_spec(SPEC)
sys.modules["pr_check"] = pr_check
SPEC.loader.exec_module(pr_check)


def test_plan_gates_docs_only() -> None:
    gates = pr_check.plan_gates(["CONTRIBUTING.md", "docs/task-scheduler.md"])
    ids = [g.id for g in gates]
    assert ids == ["GIT-DIFF", "RUFF-FORMAT"]


def test_plan_gates_backend_and_lock() -> None:
    gates = pr_check.plan_gates(["app/api/setting.py", "pyproject.toml"])
    ids = [g.id for g in gates]
    assert ids == ["GIT-DIFF", "RUFF-FORMAT", "UV-LOCK", "CHANGELOG"]


def test_plan_gates_frontend_vue_and_electron() -> None:
    gates = pr_check.plan_gates(
        [
            "frontend/src/views/setting/TabFunction.vue",
            "frontend/electron/services/analytics.ts",
            "frontend/e2e/settings.pw.ts",
        ],
        skip_changelog=True,
    )
    ids = [g.id for g in gates]
    assert ids == [
        "GIT-DIFF",
        "VUE-SIZE",
        "FRONTEND-LINT",
        "FRONTEND-TYPECHECK",
        "ELECTRON-TYPECHECK",
        "FRONTEND-FORMAT",
        "I18N-AUDIT",
        "E2E-HARNESS",
        "CHANGELOG",
    ]
    changelog_gate = next(g for g in gates if g.id == "CHANGELOG")
    assert "--skip-changelog" in changelog_gate.command


def test_format_failure_contains_actionable_sections() -> None:
    gate = pr_check.Gate(
        id="CHANGELOG",
        title="更新日志碎片检查",
        command=("uv", "run", "python", "scripts/changelog.py", "check"),
        cwd=Path("."),
        forbid="禁止手改 CHANGELOG.md",
        fix="运行 python scripts/changelog.py add",
    )
    rendered = pr_check.format_failure(gate, "missing fragment")
    assert "[FAIL][CHANGELOG]" in rendered
    assert "禁止：禁止手改 CHANGELOG.md" in rendered
    assert "修复：运行 python scripts/changelog.py add" in rendered
    assert "missing fragment" in rendered
