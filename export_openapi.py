#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
导出 OpenAPI schema 到文件，不启动 HTTP 服务器。
用于前端代码生成：npm run openapi
"""

import json
import os
import sys
import types
from pathlib import Path

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 先解析输出路径（必须在 chdir 之前，否则相对路径会基于错误的目录）
if __name__ == "__main__":
    _output_path = (
        Path(sys.argv[1]).resolve() if len(sys.argv) > 1
        else current_dir / "frontend" / "openapi.json"
    )
else:
    _output_path = current_dir / "frontend" / "openapi.json"

# 确保工作目录为项目根目录（Config 初始化依赖 Path.cwd() 是 git 仓库根目录）
os.chdir(current_dir)

try:
    import pyautogui  # noqa: F401
except ModuleNotFoundError:
    stub = types.ModuleType("pyautogui")
    stub.KEYBOARD_KEYS = []
    sys.modules["pyautogui"] = stub


def export_schema(output_path: Path) -> None:
    # 必须在函数内部导入，否则触发循环导入（同 main.py 的设计）
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.api import (
        core_router,
        info_router,
        scripts_router,
        plan_router,
        emulator_router,
        queue_router,
        dispatch_router,
        history_router,
        tools_router,
        plugins_router,
        setting_router,
        update_router,
        ocr_router,
        ws_debug_router,
    )

    @asynccontextmanager
    async def dummy_lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="AUTO-MAS",
        description="API for managing automation scripts, plans, and tasks",
        version="1.0.0",
        lifespan=dummy_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(core_router)
    app.include_router(info_router)
    app.include_router(scripts_router)
    app.include_router(plan_router)
    app.include_router(emulator_router)
    app.include_router(queue_router)
    app.include_router(dispatch_router)
    app.include_router(history_router)
    app.include_router(tools_router)
    app.include_router(plugins_router)
    app.include_router(setting_router)
    app.include_router(update_router)
    app.include_router(ocr_router)
    app.include_router(ws_debug_router)

    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OpenAPI schema 已导出到: {output_path}")


if __name__ == "__main__":
    export_schema(_output_path)
