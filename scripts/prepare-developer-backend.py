"""生成复用发行环境的开发入口，可选复制测试配置和数据。"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path


def prepare(source: Path, base: Path, *, copy_data: bool = False) -> Path:
    """检查已有发行环境，并生成环境变量启动入口。"""
    source, base = source.resolve(), base.resolve()
    if source == base or source.is_relative_to(base / "repo"):
        raise ValueError("开发源码必须与日常后端目录分开。")
    for name in ("main.py", "pyproject.toml", "uv.lock"):
        if not (source / name).is_file():
            raise ValueError(f"源码不完整：缺少 {name}")
    if not (base / "AUTO-MAS.exe").is_file():
        raise ValueError("没有找到发行版 AUTO-MAS.exe")
    venv = base / "runtime/environment/venv"
    if (
        not (venv / "pyvenv.cfg").is_file()
        or not (venv / "Scripts/python.exe").is_file()
    ):
        raise ValueError("请先完成这份发行版的初始化。")
    if copy_data:
        for name in ("config", "data"):
            if (source / name).exists():
                raise ValueError(f"开发目录已有 {name}，不会覆盖。")
    if copy_data:
        for name in ("config", "data"):
            origin, target = base / name, source / name
            if not origin.exists():
                continue

            # SQLite 主文件及活动日志不直接复制，由备份接口生成一致的数据库副本。
            def ignore_databases(folder: str, names: list[str]) -> set[str]:
                return {
                    name
                    for name in names
                    if (Path(folder) / name).is_file()
                    and (
                        Path(name).suffix.lower() in {".db", ".sqlite", ".sqlite3"}
                        or name.lower().endswith(("-wal", "-shm", "-journal"))
                    )
                }

            shutil.copytree(origin, target, ignore=ignore_databases)
            for database in origin.rglob("*"):
                if database.is_file() and database.suffix.lower() in {
                    ".db",
                    ".sqlite",
                    ".sqlite3",
                }:
                    destination = target / database.relative_to(origin)
                    with (
                        closing(
                            sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
                        ) as src,
                        closing(sqlite3.connect(destination)) as dst,
                    ):
                        src.backup(dst)

    # PowerShell 单引号字符串以两个单引号转义，不拼接执行 shell 命令。
    def quoted(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    launcher = source / "developer-backend.ps1"
    launcher.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"$env:AUTO_MAS_BACKEND_REPO = {quoted(source)}\n"
        f"& {quoted(base / 'AUTO-MAS.exe')}\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"source": str(source), "launcher": str(launcher)}, ensure_ascii=False
        )
    )
    return launcher


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--copy-data", action="store_true")
    args = parser.parse_args()
    prepare(args.source, args.base, copy_data=args.copy_data)
