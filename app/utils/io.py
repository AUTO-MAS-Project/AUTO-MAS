#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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


from __future__ import annotations

import json
import json5
import os
import threading
import tomllib
from contextlib import suppress
from pathlib import Path
from typing import Any

import tomli_w
import yaml

from .tools import decode_bytes

# 格式后缀 -> (dump: (dict, encoding)->bytes, load: bytes->dict)
# 若要扩展格式, 直接改此表
_CODECS: dict[str, tuple[Any, Any]] = {
    ".toml": (
        lambda d, encoding: tomli_w.dumps(d, indent=2).encode(encoding),
        lambda data: tomllib.loads(decode_bytes(data)),
    ),
    ".json": (
        lambda d, encoding: json.dumps(d, ensure_ascii=False, indent=2).encode(encoding),
        lambda data: json.loads(decode_bytes(data)),
    ),
    ".json5": (
        lambda d, encoding: json5.dumps(d, indent=2).encode(encoding),
        lambda data: json5.loads(decode_bytes(data)),
    ),
    ".jsonl": (
        lambda d, encoding: "\n".join(json.dumps(i, ensure_ascii=False) for i in d).encode(
            encoding
        )
        + b"\n",
        lambda data: [
            json.loads(d) for d in decode_bytes(data).splitlines() if d.strip()
        ],
    ),
    ".yaml": (
        lambda d, encoding: yaml.safe_dump(d, allow_unicode=True, sort_keys=False).encode(
            encoding
        ),
        lambda data: yaml.safe_load(decode_bytes(data)),
    ),
    ".yml": (
        lambda d, encoding: yaml.safe_dump(d, allow_unicode=True, sort_keys=False).encode(
            encoding
        ),
        lambda data: yaml.safe_load(decode_bytes(data)),
    ),
}

# 进程内串行锁, 避免并发竞争写
_WRITE_LOCK = threading.Lock()


def atomic_write(path: Path, data: bytes) -> None:
    """
    原子写, 写同目录固定名临时文件, fsync 后 replace 覆盖

    Args:
        path: 目标文件路径
        data: 待写入的字节内容
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with _WRITE_LOCK:
        try:
            tmp_path.write_bytes(data)
            # 数据落盘
            with tmp_path.open("rb+") as fh:
                fh.flush()
                os.fsync(fh.fileno())
            # 原子替换
            tmp_path.replace(path)
            # 目录项落盘, 仅在 Linux 下有效
            with suppress(OSError):
                with path.parent.open("rb") as dfh:
                    dfh.flush()
                    os.fsync(dfh.fileno())
        except BaseException:
            # 失败清理残留临时文件
            tmp_path.unlink(missing_ok=True)
            raise


def read_file(path: Path) -> dict[str, Any] | str:
    """
    按后缀读取配置文件

    Args:
        path: 文件路径, 后缀决定是否解析

    Returns:
        dict[str, Any] | str: 已知格式解析后的结构; 未知格式返回原始字符串; 不存在返回空 ``{}``
    """
    if not path.exists():
        return {}
    codec = _CODECS.get(path.suffix.lower())
    if codec is None:
        return decode_bytes(path.read_bytes())
    return codec[1](path.read_bytes())


def write_file(
    path: Path, payload: dict[str, Any] | str, *, encoding: str = "utf-8"
) -> None:
    """
    按后缀原子写入

    - 已知格式: 序列化后写盘
    - 未知格式且传 ``str``: 不序列化, 直接写原字符串
    - 未知格式且传 ``dict`` 等非 str: 抛 ``ValueError``

    Args:
        path: 文件路径, 后缀决定是否序列化
        payload: 已知格式为待写的 ``dict``; 未知格式须为 ``str``
        encoding: 写盘编码, 默认 ``utf-8``
    """
    codec = _CODECS.get(path.suffix.lower())
    if codec is not None:
        atomic_write(path, codec[0](payload, encoding))
        return
    if not isinstance(payload, str):
        raise ValueError(
            f"不支持的配置文件格式 `{path.suffix.lower()}`，且内容非字符串"
        )
    atomic_write(path, payload.encode(encoding))
