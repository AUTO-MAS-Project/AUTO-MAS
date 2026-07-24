"""离线导出当前源码的 OpenAPI schema，不启动 AUTO-MAS 运行时。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI

repository_root = Path(__file__).resolve().parent.parent
if str(repository_root) not in sys.path:
    sys.path.insert(0, str(repository_root))

from app.api.registration import register_application_routers


def build_openapi_schema() -> dict:
    """只装配路由并返回当前源码的 OpenAPI schema。"""
    previous_working_directory = Path.cwd()
    try:
        os.chdir(repository_root)
        app = FastAPI(
            title="AUTO-MAS",
            description="API for managing automation scripts, plans, and tasks",
            version="1.0.0",
        )
        register_application_routers(app)
        return app.openapi()
    finally:
        os.chdir(previous_working_directory)


def parse_args() -> argparse.Namespace:
    """解析导出目标。"""
    parser = argparse.ArgumentParser(description="离线导出 AUTO-MAS OpenAPI schema")
    parser.add_argument("--output", required=True, type=Path, help="schema JSON 输出路径")
    return parser.parse_args()


def main() -> int:
    """生成 schema JSON。"""
    args = parse_args()
    output_path = args.output.resolve()
    if output_path.exists() and output_path.is_dir():
        raise IsADirectoryError(f"OpenAPI 输出路径不能是目录: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_openapi_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[export_openapi_schema] 已导出: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
