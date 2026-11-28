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
    assert ids == ["GIT-DIFF", "RUFF-FORMAT", "RUFF-F821"]


def test_plan_gates_backend_and_lock() -> None:
    gates = pr_check.plan_gates(["app/api/setting.py", "pyproject.toml"])
    ids = [g.id for g in gates]
    # 后端改动必须跑 pytest 全量（BACKEND-TEST），顺序在依赖锁检查之后、碎片检查之前。
    assert ids == [
        "GIT-DIFF",
        "RUFF-FORMAT",
        "RUFF-F821",
        "UV-LOCK",
        "BACKEND-TEST",
        "CHANGELOG",
    ]


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
    # .vue 改动先跑尺寸基线自检（VUE-BASELINE-CHECK）再跑 500 行门禁（VUE-SIZE）；
    # frontend/src 改动要补前端单测（FRONTEND-TEST），排在 e2e 契约自检之前。
    assert ids == [
        "GIT-DIFF",
        "VUE-BASELINE-CHECK",
        "VUE-SIZE",
        "FRONTEND-LINT",
        "FRONTEND-TYPECHECK",
        "ELECTRON-TYPECHECK",
        "FRONTEND-FORMAT",
        "I18N-AUDIT",
        "FRONTEND-TEST",
        "E2E-HARNESS",
        "CHANGELOG",
    ]
    changelog_gate = next(g for g in gates if g.id == "CHANGELOG")
    assert "--skip-changelog" in changelog_gate.command


def test_backend_preflight_reports_missing_plugins(tmp_path: Path) -> None:
    """测试插件没装时，预检要直接指向准备脚本，而不是让人去查业务代码。"""
    requirements = tmp_path / "requirements-plugins.txt"
    requirements.write_text(
        "# 注释行不算\n"
        "auto-mas-src-adapter==0.1.0 --hash=sha256:deadbeef\n"
        "auto-mas-maa-adapter==0.1.4 --hash=sha256:deadbeef\n",
        encoding="utf-8",
    )
    plugins_dir = tmp_path / ".test-plugins"
    plugins_dir.mkdir()

    hints = pr_check.backend_test_preflight(plugins_dir, requirements)

    assert len(hints) == 3
    assert "auto-mas-src-adapter==0.1.0" in hints[0]
    assert "auto-mas-maa-adapter==0.1.4" in hints[0]
    assert "prepare_test_plugins.py" in hints[2]


def test_backend_preflight_accepts_installed_plugins(tmp_path: Path) -> None:
    """清单里的发行包都在（名字里的 - 换成 _）时预检放行。"""
    requirements = tmp_path / "requirements-plugins.txt"
    requirements.write_text(
        "auto-mas-src-adapter==0.1.0 --hash=sha256:deadbeef\n", encoding="utf-8"
    )
    plugins_dir = tmp_path / ".test-plugins"
    (plugins_dir / "auto_mas_src_adapter-0.1.0.dist-info").mkdir(parents=True)

    assert pr_check.backend_test_preflight(plugins_dir, requirements) == []


def test_backend_preflight_rejects_stale_version(tmp_path: Path) -> None:
    """旧版本残留目录不算装好，否则同步 dev 后仍会在收集阶段炸。"""
    requirements = tmp_path / "requirements-plugins.txt"
    requirements.write_text(
        "auto-mas-src-adapter==0.1.0 --hash=sha256:deadbeef\n", encoding="utf-8"
    )
    plugins_dir = tmp_path / ".test-plugins"
    (plugins_dir / "auto_mas_src_adapter-0.0.9.dist-info").mkdir(parents=True)

    hints = pr_check.backend_test_preflight(plugins_dir, requirements)

    assert hints, "版本不符必须拦住"
    assert "auto-mas-src-adapter==0.1.0" in hints[0]


def test_backend_gate_carries_preflight() -> None:
    """BACKEND-TEST 必须挂上前置检查，否则缺插件时又会被报成业务代码失败。"""
    gates = pr_check.plan_gates(["app/api/setting.py"])
    gate = next(g for g in gates if g.id == "BACKEND-TEST")

    assert gate.preflight is not None
    assert "prepare_test_plugins.py" in gate.fix


def test_format_failure_renders_preflight_hints() -> None:
    """前置条件未满足时，失败信息要把待办单列出来。"""
    gate = pr_check.Gate(
        id="BACKEND-TEST",
        title="后端单元测试",
        command=("uv", "run", "pytest", "-q", "tests"),
        cwd=Path("."),
        forbid="禁止只跑关心的用例",
        fix="修复实现后重跑",
    )
    rendered = pr_check.format_failure(gate, "", ["先装测试插件", "再重跑门禁"])

    assert "待办：" in rendered
    assert "    先装测试插件" in rendered
    assert "    再重跑门禁" in rendered


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
