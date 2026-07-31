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

"""统一 TOML 读写（2 空格缩进、原子写）。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import tomli_w


def read_toml(path: Path) -> dict[str, Any]:
    """解析 TOML 文件；不存在则返回空 dict。"""
    if not path.exists():
        return {}
    with path.open("rb") as fp:
        return tomllib.load(fp)


def write_toml(path: Path, payload: dict[str, Any]) -> None:
    """原子写入 TOML（先写 ``.tmp`` 再 replace）；缩进 2 空格。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(tomli_w.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


__all__ = ["read_toml", "write_toml"]
