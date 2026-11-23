#!/usr/bin/env python3
"""AUTO-MAS 本地 PR 一键预检脚本。

按当前分支相对目标分支（默认 origin/dev）及工作区的改动路径，自动串联对应 CI 门禁，
并在失败时输出统一的「违反规则 / 禁止绕过 / 精确修复命令」三段式指引。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"

FRONTEND_CODE_SUFFIXES = (".ts", ".tsx", ".vue", ".js", ".mjs", ".cjs", ".css")
CHANGELOG_TRIGGER_PREFIXES = ("app/", "frontend/src/", "frontend/electron/")
CHANGELOG_TRIGGER_FILES = ("main.py", "CHANGELOG.md", "res/version.json")


@dataclass(frozen=True)
class Gate:
    """单个本地预检门禁定义。"""

    id: str
    title: str
    command: tuple[str, ...]
    cwd: Path
    forbid: str
    fix: str


def _normalize_path(raw: str) -> str:
    return raw.strip().replace("\\", "/")


def collect_changed_files(base_ref: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """收集相对 base_ref 的已提交改动、工作区改动与未跟踪文件。"""
    files: set[str] = set()
    commands = (
        ("git", "diff", "--name-only", f"{base_ref}...HEAD"),
        ("git", "diff", "--name-only"),
        ("git", "diff", "--name-only", "--cached"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    )
    for cmd in commands:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            norm = _normalize_path(line)
            if norm:
                files.add(norm)
    return sorted(files)


def _any_match(files: list[str], predicate) -> bool:
    return any(predicate(path) for path in files)


def plan_gates(
    changed_files: list[str],
    *,
    base_ref: str = "origin/dev",
    run_all: bool = False,
    skip_changelog: bool = False,
    repo_root: Path = REPO_ROOT,
) -> list[Gate]:
    """根据改动文件列表规划需要执行的最小必要门禁集合。"""
    frontend_dir = repo_root / "frontend"
    gates: list[Gate] = [
        Gate(
            id="GIT-DIFF",
            title="Git 空白与冲突标记检查",
            command=("git", "diff", "--check"),
            cwd=repo_root,
            forbid="禁止带着冲突标记或异常尾随空白提交 PR。",
            fix="清理报错行中的尾随空白或冲突标记后重跑。",
        ),
    ]

    need_ruff = run_all or _any_match(
        changed_files,
        lambda p: p.endswith((".py", ".md")),
    )
    if need_ruff:
        gates.append(
            Gate(
                id="RUFF-FORMAT",
                title="Python 与 Markdown 代码块格式检查（uv.lock 锁定版本）",
                command=("uv", "run", "--no-sync", "ruff", "format", "--check", "."),
                cwd=repo_root,
                forbid="禁止使用系统全局 ruff（版本须与 uv.lock 一致），禁止顺手格式化无关文件。",
                fix="运行 uv run --no-sync ruff format <改动文件> 后重跑。",
            )
        )

    need_uv_lock = run_all or _any_match(
        changed_files,
        lambda p: p in ("pyproject.toml", "uv.lock", "requirements.txt"),
    )
    if need_uv_lock:
        gates.append(
            Gate(
                id="UV-LOCK",
                title="uv.lock 与依赖清单一致性检查",
                command=("uv", "lock", "--check"),
                cwd=repo_root,
                forbid="禁止手改 uv.lock，禁止只改 pyproject.toml 不更新锁文件。",
                fix="运行 uv lock 并同步更新 requirements.txt 后一并提交。",
            )
        )

    need_vue_size = run_all or _any_match(
        changed_files,
        lambda p: p.startswith("frontend/") and p.endswith(".vue"),
    )
    if need_vue_size:
        gates.append(
            Gate(
                id="VUE-SIZE",
                title="Vue 组件 500 行尺寸门禁",
                command=("node", "scripts/audit-baseline.mjs", "--check", base_ref),
                cwd=frontend_dir,
                forbid="禁止删空行、压缩排版或整段塞进空壳 composable 凑行数；超 500 行新增行为须先拆分职责。",
                fix="按 .agents/skills/mas-frontend-standards/SKILL.md 拆分受影响组件后再校验。",
            )
        )

    need_fe_code = run_all or _any_match(
        changed_files,
        lambda p: p.startswith("frontend/") and p.endswith(FRONTEND_CODE_SUFFIXES),
    )
    if need_fe_code:
        gates.append(
            Gate(
                id="FRONTEND-LINT",
                title="前端 Oxlint 静态检查",
                command=("yarn", "lint"),
                cwd=frontend_dir,
                forbid="禁止滥用 disable 注释掩盖真实问题，禁止全仓跑 lint:fix 污染无关 diff。",
                fix="在 frontend/ 下仅修复改动文件的 lint 诊断后重跑 yarn lint。",
            )
        )

    need_fe_typecheck = run_all or _any_match(
        changed_files,
        lambda p: p.startswith("frontend/src/") or p.startswith("frontend/tsconfig"),
    )
    if need_fe_typecheck:
        gates.append(
            Gate(
                id="FRONTEND-TYPECHECK",
                title="前端 Vue 渲染层类型检查",
                command=("yarn", "typecheck"),
                cwd=frontend_dir,
                forbid="禁止用 as any / @ts-ignore 掩盖类型错误，禁止手改 frontend/src/api/。",
                fix="修复类型错误（后端改了 schema 先跑 yarn openapi），再在 frontend/ 下重跑 yarn typecheck。",
            )
        )

    need_electron_tc = run_all or _any_match(
        changed_files,
        lambda p: p.startswith("frontend/electron/"),
    )
    if need_electron_tc:
        gates.append(
            Gate(
                id="ELECTRON-TYPECHECK",
                title="Electron 主进程 / preload 类型检查",
                command=(
                    "node",
                    "node_modules/typescript/bin/tsc",
                    "-p",
                    "tsconfig.electron.json",
                    "--noEmit",
                ),
                cwd=frontend_dir,
                forbid="yarn typecheck 不覆盖 frontend/electron/，禁止跳过主进程类型检查。",
                fix="修复 frontend/electron/ 类型诊断后在 frontend/ 下重跑上述 tsc 命令。",
            )
        )

    need_fe_format = run_all or _any_match(
        changed_files,
        lambda p: p.startswith("frontend/"),
    )
    if need_fe_format:
        gates.append(
            Gate(
                id="FRONTEND-FORMAT",
                title="前端 Oxfmt 格式检查",
                command=("yarn", "format:check"),
                cwd=frontend_dir,
                forbid="禁止提交未格式化代码，也不要把无关文件的格式改动带进本 PR。",
                fix="在 frontend/ 下运行 yarn format 后仅保留本次改动文件的格式调整。",
            )
        )

    need_i18n = run_all or _any_match(
        changed_files,
        lambda p: p.startswith(("frontend/src/", "res/i18n/")),
    )
    if need_i18n:
        gates.append(
            Gate(
                id="I18N-AUDIT",
                title="多语言词表完整性检查",
                command=("yarn", "audit:i18n", "--check"),
                cwd=frontend_dir,
                forbid="禁止只改中文漏翻 en-US/ja-JP，也禁止翻译驱动逻辑的中文字面量（如 '运行'）。",
                fix="同步补齐三语词条后，在 frontend/ 下重跑 yarn audit:i18n --check。",
            )
        )

    need_e2e_harness = run_all or _any_match(
        changed_files,
        lambda p: p.startswith("frontend/e2e/"),
    )
    if need_e2e_harness:
        gates.append(
            Gate(
                id="E2E-HARNESS",
                title="E2E 基础设施契约自检",
                command=("node", "--test", "e2e/harness.check.mjs"),
                cwd=frontend_dir,
                forbid="禁止绕过 frontend/e2e/run.mjs 或破坏数据根隔离与真实运行锁。",
                fix="按失败输出修复 frontend/e2e/ 契约后在 frontend/ 下重跑 yarn e2e:check。",
            )
        )

    need_changelog = run_all or _any_match(
        changed_files,
        lambda p: (
            p.startswith(CHANGELOG_TRIGGER_PREFIXES)
            or p.startswith("changelog.d/")
            or p in CHANGELOG_TRIGGER_FILES
        ),
    )
    if need_changelog:
        cmd = [
            "uv",
            "run",
            "--no-sync",
            "python",
            "scripts/changelog.py",
            "check",
            "--pr-base",
            base_ref,
            "--pr-kind",
            "normal",
        ]
        if skip_changelog:
            cmd.append("--skip-changelog")
        gates.append(
            Gate(
                id="CHANGELOG",
                title="更新日志碎片与版本号检查",
                command=tuple(cmd),
                cwd=repo_root,
                forbid="普通 PR 禁止手改 CHANGELOG.md、res/version.json 或版本号；用户可见改动禁止滥用 skip-changelog。",
                fix='用户可见改动运行 uv run --no-sync python scripts/changelog.py add <分类> <项目键> "<不超过50字>"；纯文档/测试/CI 给 PR 打 skip-changelog 标签并加 --skip-changelog 重跑。',
            )
        )

    return gates


def format_failure(gate: Gate, output: str) -> str:
    """格式化面向人类新手与 AI 的三段式失败提示。"""
    tail = "\n".join(output.strip().splitlines()[-20:])
    lines = [
        f"[FAIL][{gate.id}] {gate.title}",
        f"  命令：{' '.join(gate.command)}",
        f"  禁止：{gate.forbid}",
        f"  修复：{gate.fix}",
    ]
    if tail:
        lines.append("  输出摘要：")
        for line in tail.splitlines():
            lines.append(f"    {line}")
    return "\n".join(lines)


def run_gates(gates: list[Gate], *, dry_run: bool = False) -> int:
    """依次执行门禁并返回退出码（0 表示全通过）。"""
    if dry_run:
        print(f"将执行 {len(gates)} 项本地预检门禁（dry-run）：")
        for gate in gates:
            print(f"  - [{gate.id}] {gate.title}: {' '.join(gate.command)}")
        return 0

    failures: list[str] = []
    for gate in gates:
        print(f"==> [{gate.id}] {gate.title} ...", flush=True)
        resolved = shutil.which(gate.command[0])
        if resolved is None:
            failures.append(
                format_failure(
                    gate,
                    f"未找到可执行命令 '{gate.command[0]}'，请确认对应工具链已安装并加入 PATH。",
                )
            )
            print(f"    FAIL [{gate.id}] (missing executable: {gate.command[0]})")
            continue
        proc = subprocess.run(
            (resolved, *gate.command[1:]),
            cwd=gate.cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode == 0:
            print(f"    PASS [{gate.id}]")
            continue
        combined = "\n".join(
            part for part in (proc.stdout, proc.stderr) if part.strip()
        )
        failures.append(format_failure(gate, combined))
        print(f"    FAIL [{gate.id}] (exit={proc.returncode})")

    if failures:
        print("\n" + "=" * 60)
        print(f"本地预检未通过：{len(failures)}/{len(gates)} 项失败\n")
        print("\n\n".join(failures))
        return 1

    print(f"\n本地预检全部通过：{len(gates)}/{len(gates)} 项 PASS。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AUTO-MAS 本地 PR 一键预检：按改动路径自动运行对应 CI 门禁。"
    )
    parser.add_argument(
        "--base",
        default="origin/dev",
        help="对比基线分支（默认 origin/dev）",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="run_all",
        help="忽略 diff 过滤，执行全部本地门禁",
    )
    parser.add_argument(
        "--skip-changelog",
        action="store_true",
        help="纯文档/测试/CI 改动时跳过更新日志碎片要求",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅列出将要执行的门禁，不实际运行",
    )
    args = parser.parse_args(argv)

    changed = [] if args.run_all else collect_changed_files(args.base)
    if not args.run_all:
        print(f"检测到 {len(changed)} 个改动文件（基线：{args.base}）。")

    gates = plan_gates(
        changed,
        base_ref=args.base,
        run_all=args.run_all,
        skip_changelog=args.skip_changelog,
    )
    return run_gates(gates, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
