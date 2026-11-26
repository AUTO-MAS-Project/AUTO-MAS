#!/usr/bin/env python3
"""AUTO-MAS 本地开发环境诊断、开发后端清理与可选 VS Code 启动配置生成。

生产端（36163）与开发端（默认 36164）严格隔离；清理仅作用于当前仓库根目录的 main.py。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
PROD_HTTP_PORT = 36163
DEFAULT_DEV_HTTP_PORT = 36164
DEFAULT_VITE_PORT = 5173


def resolve_dev_port(explicit: int | None = None) -> int:
    port = (
        explicit
        if explicit is not None
        else int(os.getenv("AUTO_MAS_HTTP_PORT") or DEFAULT_DEV_HTTP_PORT)
    )
    if not (1 <= port <= 65535):
        raise ValueError(f"端口必须在 1–65535 之间：{port}")
    return port


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _matches_repo_main_py(cmdline: str, repo_root: Path) -> bool:
    target = str((repo_root.resolve() / "main.py")).lower().replace("/", "\\")
    normalized = cmdline.lower().replace("/", "\\")
    return (
        re.search(rf'(?:^|[\s"\']){re.escape(target)}(?:[\s"\']|$)', normalized)
        is not None
    )


def find_repo_dev_backends(repo_root: Path = REPO_ROOT) -> list[tuple[int, str]]:
    if os.name != "nt":
        return []
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'main\\.py' } | "
        "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress"
    )
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    raw = json.loads(proc.stdout)
    items = raw if isinstance(raw, list) else [raw]
    return [
        (item["ProcessId"], item["CommandLine"])
        for item in items
        if _matches_repo_main_py(str(item.get("CommandLine") or ""), repo_root)
    ]


def registered_windows_pool() -> bool:
    """发现当前终端尚未继承的共享池，避免回退成工作树 .venv。"""
    if os.name != "nt":
        return False
    import winreg

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    for hive, location in locations:
        try:
            with winreg.OpenKey(hive, location) as key:
                value, _ = winreg.QueryValueEx(key, "AUTO_MAS_DEV_ENV_ROOT")
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError(f"无法检查 Windows 共享池登记：{error}") from error
        if str(value).strip():
            return True
    return False


def verified_shared_python() -> Path | None:
    """按共享池的同一预检入口解析已验证的解释器，不安装或回退。"""
    if not os.getenv("AUTO_MAS_DEV_ENV_ROOT", "").strip():
        if registered_windows_pool():
            raise ValueError(
                "Windows 已登记 AUTO_MAS_DEV_ENV_ROOT，但当前终端未继承；"
                "请核对用户与系统设置，再在新终端或本次进程中选定共享池。"
            )
        return None
    pwsh = shutil.which("pwsh")
    if not pwsh:
        raise ValueError("共享测试环境需要 PowerShell 7（pwsh）。")
    try:
        result = subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(REPO_ROOT / "scripts/dev-backend.ps1"),
                "Check",
                "-Target",
                "Test",
                "-PythonPathOnly",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as error:
        raise ValueError(f"无法启动共享环境预检：{error}") from error
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(detail or f"共享环境预检退出码为 {result.returncode}。")
    output = result.stdout.strip()
    python = Path(output)
    if not python.is_absolute() or not python.is_file():
        raise ValueError("共享环境预检未返回可用的 Python 解释器路径。")
    return python


def build_vscode_launch_config(
    dev_port: int, *, shared_python: Path | None = None
) -> dict[str, object]:
    port = str(dev_port)
    python_path = (
        str(shared_python)
        if shared_python
        else (
            "${workspaceFolder}/.venv/Scripts/python.exe"
            if os.name == "nt"
            else "${workspaceFolder}/.venv/bin/python"
        )
    )
    configurations = []
    # 源码 Electron 入口可能为独立模式准备 .venv，不能用于承诺只复用共享池的配置。
    if shared_python is None:
        configurations.append(
            {
                "name": "Dev: 全栈启动（Electron + Runtime）",
                "type": "node-terminal",
                "request": "launch",
                "command": "yarn dev",
                "cwd": "${workspaceFolder}/frontend",
                "env": {
                    "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
                    "AUTO_MAS_HTTP_PORT": port,
                },
                "autoAttachChildProcesses": False,
            }
        )
    configurations.append(
        {
            "name": "Dev: 后端断点调试（独立后端）",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/main.py",
            "python": python_path,
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}",
            "env": {
                "AUTO_MAS_ENV": "development",
                "AUTO_MAS_HTTP_PORT": port,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
            },
        }
    )
    return {"version": "0.2.0", "configurations": configurations}


def run_doctor(dev_port: int) -> int:
    print(f"[dev-doctor] 仓库根目录: {REPO_ROOT}")
    shared = True
    try:
        python = verified_shared_python()
    except ValueError as error:
        python_check = ("共享测试 Python", False, str(error))
    else:
        shared = python is not None
        python_check = (
            (f"共享测试 Python：{python}", True, "")
            if shared
            else (
                "Python .venv",
                (REPO_ROOT / ".venv").exists(),
                "独立开发：uv sync --locked --group dev；worktree：先核对共享测试池",
            )
        )
    checks = [
        ("uv", shutil.which("uv") is not None, "安装 uv 或确认其在 PATH 中"),
        ("node", shutil.which("node") is not None, "安装 Node 24+"),
        ("yarn", shutil.which("yarn") is not None, "启用 Corepack / Yarn 4"),
        python_check,
        (
            "frontend/node_modules",
            (FRONTEND_DIR / "node_modules").exists(),
            "cd frontend && yarn install --immutable",
        ),
    ]
    missing = 0
    for name, ok, hint in checks:
        print(f"  [{'OK  ' if ok else 'WARN'}] {name}" + ("" if ok else f" — {hint}"))
        if not ok:
            missing += 1

    print("\n[dev-doctor] 端口隔离状态:")
    if shared:
        print(f"  正式版 {PROD_HTTP_PORT}: 保留，不探测")
    else:
        active = is_port_open(PROD_HTTP_PORT)
        print(
            f"  正式版 {PROD_HTTP_PORT}: {'运行中（与开发端隔离）' if active else '未监听'}"
        )
    print(f"  开发端 {dev_port}: {'已监听' if is_port_open(dev_port) else '空闲'}")
    print(
        f"  Vite   {DEFAULT_VITE_PORT}: {'已监听' if is_port_open(DEFAULT_VITE_PORT) else '空闲'}"
    )

    procs = find_repo_dev_backends()
    print(f"\n[dev-doctor] 当前仓库的开发后端进程 ({len(procs)} 个):")
    for pid, cmdline in procs:
        print(f"  PID {pid}: {cmdline[:120]}")
    if procs:
        print("  清理命令: python scripts/dev_doctor.py --kill-dev")
    return 1 if missing else 0


def kill_repo_dev_backends() -> int:
    procs = find_repo_dev_backends()
    if not procs:
        print("[dev-doctor] 未发现当前仓库的开发后端进程。")
        return 0
    failed = 0
    for pid, _ in procs:
        res = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            print(f"[dev-doctor] 已清理 PID={pid}")
        else:
            print(f"[dev-doctor] 清理 PID={pid} 失败", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def init_vscode_launch(dev_port: int, *, force: bool) -> int:
    if dev_port == PROD_HTTP_PORT:
        print(
            f"[dev-doctor] 开发端口不能使用正式版端口 {PROD_HTTP_PORT}", file=sys.stderr
        )
        return 1
    target = REPO_ROOT / ".vscode" / "launch.json"
    if target.exists() and not force:
        print(f"[dev-doctor] {target} 已存在，未覆盖（追加 --force 覆盖）。")
        return 0
    if not target.resolve().is_relative_to(REPO_ROOT.resolve()):
        print("[dev-doctor] VS Code 配置指向工作树之外，拒绝写入。", file=sys.stderr)
        return 1
    try:
        shared_python = verified_shared_python()
    except ValueError as error:
        print(
            f"[dev-doctor] 共享环境预检失败，未写入启动配置：{error}", file=sys.stderr
        )
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            build_vscode_launch_config(dev_port, shared_python=shared_python),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[dev-doctor] 已生成 {target}（开发端口：{dev_port}）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AUTO-MAS 本地开发环境诊断与辅助工具")
    parser.add_argument(
        "--port", type=int, default=None, help="开发后端端口（默认 36164）"
    )
    parser.add_argument(
        "--kill-dev", action="store_true", help="仅清理当前仓库的 main.py 开发后端"
    )
    parser.add_argument(
        "--init-vscode", action="store_true", help="生成极简 .vscode/launch.json"
    )
    parser.add_argument(
        "--force", action="store_true", help="配合 --init-vscode 覆盖已有文件"
    )
    args = parser.parse_args(argv)
    dev_port = resolve_dev_port(args.port)
    if dev_port == PROD_HTTP_PORT:
        parser.error(f"开发端口不能使用正式版端口 {PROD_HTTP_PORT}")
    if args.kill_dev:
        return kill_repo_dev_backends()
    if args.init_vscode:
        return init_vscode_launch(dev_port, force=args.force)
    return run_doctor(dev_port)


if __name__ == "__main__":
    raise SystemExit(main())
