#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""Hook 管理 API。

提供 hook 元数据读取能力，用于前端脚本配置页面展示。

注意：此处读取元数据默认采用 AST 静态解析，不执行 hook 代码。
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi import APIRouter, Body

from app.models.schema import HookMetaIn, HookMetaItem, HookMetaOut

router = APIRouter(prefix="/api/hooks", tags=["Hook管理"])


def _read_hook_meta_static(file_path: str) -> HookMetaItem:
    p = Path(file_path)
    item = HookMetaItem(path=str(p))

    if not p.exists() or not p.is_file():
        item.status = "warning"
        item.warning = "文件不存在或不是文件"
        return item

    try:
        source = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 兼容一些使用本地编码的脚本
        try:
            source = p.read_text(encoding="gbk")
        except Exception as e:
            item.status = "warning"
            item.warning = f"读取失败: {type(e).__name__}: {e}"
            return item
    except Exception as e:
        item.status = "warning"
        item.warning = f"读取失败: {type(e).__name__}: {e}"
        return item

    try:
        tree = ast.parse(source, filename=str(p))
    except SyntaxError as e:
        item.status = "warning"
        item.warning = f"语法错误: {e.msg} (line {e.lineno})"
        return item
    except Exception as e:
        item.status = "warning"
        item.warning = f"解析失败: {type(e).__name__}: {e}"
        return item

    # 约定：HOOK_META = {"name": "...", "description": "..."}
    hook_meta_value = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "HOOK_META":
                    hook_meta_value = node.value
                    break

    if hook_meta_value is None:
        item.status = "warning"
        item.warning = "未找到 HOOK_META（需定义为字面量 dict）"
        return item

    try:
        meta = ast.literal_eval(hook_meta_value)
    except Exception as e:
        item.status = "warning"
        item.warning = f"HOOK_META 不是可静态求值的字面量: {type(e).__name__}: {e}"
        return item

    if not isinstance(meta, dict):
        item.status = "warning"
        item.warning = "HOOK_META 必须是 dict"
        return item

    name = meta.get("name")
    description = meta.get("description")

    if isinstance(name, str):
        item.name = name
    if isinstance(description, str):
        item.description = description

    if item.name is None or item.description is None:
        item.status = "warning"
        item.warning = "HOOK_META 需要包含字符串字段: name, description"

    return item


@router.post(
    "/meta",
    summary="读取 Hook 元数据（静态解析）",
    response_model=HookMetaOut,
    status_code=200,
)
async def get_hook_meta(payload: HookMetaIn = Body(...)) -> HookMetaOut:
    try:
        items = [_read_hook_meta_static(p) for p in payload.hookPaths]
    except Exception as e:
        return HookMetaOut(code=500, status="error", message=f"{type(e).__name__}: {e}")

    return HookMetaOut(data=items)
