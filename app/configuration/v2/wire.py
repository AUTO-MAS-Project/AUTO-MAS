"""Wire 文档：JSON / TOML / ``model_dump`` 同一逻辑形状。

- Collection Wire：``{ "order": [{uid, type}, …], "data": { "<uuid>": <EntryWire>, … } }``
- Entry Wire：各 Group 字段名顶层嵌套 dict

落盘 TOML 与 JSON 同形（§3.9）。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import tomli_w
from pydantic import BaseModel, ConfigDict

type WireScalar = str | int | float | bool
"""Wire 叶子标量。"""

type WireValue = WireScalar | None | dict[str, Any] | list[Any]
"""Wire 单值；嵌套 dict/list 用 ``Any``，便于 ``to_dict`` 多层下标。"""

type WireDict = dict[str, Any]
"""Wire 顶层或 Entry 级 dict。"""


@dataclass
class ExportContext:
    """``_export_wire`` 导出上下文：控制解密与是否携带响应式字段。"""

    if_decrypt: bool = False
    """False → 密文；True → 明文。"""

    include_reactive: bool = False
    """是否携带响应式字段（virtual / trigger）。"""

    include_staged: bool = False
    """是否读取当前 owner transaction 的 effective workspace。"""


class CollectionOrderItem(BaseModel):
    """Collection 索引项：``{ uid, type }``。"""

    model_config = ConfigDict(extra="forbid")

    uid: UUID
    type: str  # Entry 子类名，如 "ExampleQueue"


def read_wire_toml(path: Path) -> WireDict:
    """解析 TOML → 与 ``model_validate`` 兼容的 Wire dict。"""
    if not path.exists():
        return {}
    with path.open("rb") as fp:
        return cast(WireDict, tomllib.load(fp))


def write_wire_toml(
    path: Path,
    payload: WireDict,
    *,
    backup: bool = True,
    fsync: bool = True,
) -> None:
    """Durably replace a TOML file or raise without hiding the failure.

    Serialization is completed before touching the target. The temporary file
    lives in the target directory, is flushed (and optionally fsynced), then
    atomically replaces the target. A backup created by this call is removed
    only after success; on failure it is retained even when restoration works.
    """
    path = Path(path)
    serialized = serialize_wire_toml(payload)
    restored = cast(WireDict, tomllib.loads(serialized))
    mismatch = _first_wire_mismatch(payload, restored)
    if mismatch is not None:
        raise ValueError(
            "TOML serialization would lose or change configuration data at "
            f"{mismatch}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)

    backup_path = path.with_name(f"{path.name}.bak")
    owns_backup = False
    if backup and path.exists() and not backup_path.exists():
        shutil.copy2(path, backup_path)
        owns_backup = True

    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            suffix=".tmp",
            prefix=f"{path.name}.",
            dir=str(path.parent),
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.flush()
                if fsync:
                    os.fsync(stream.fileno())
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        os.replace(temp_path, path)
        temp_path = None
    except BaseException as write_error:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                # Preserve the original write error. A stale same-directory
                # temporary is safer than masking the durability failure.
                pass

        restore_error: Exception | None = None
        if owns_backup and backup_path.exists():
            try:
                shutil.copy2(backup_path, path)
            except Exception as exc:  # keep the only recovery copy
                restore_error = exc
        if restore_error is not None:
            raise RuntimeError(
                f"atomic TOML write failed and backup restoration failed; "
                f"backup retained at {backup_path}"
            ) from write_error
        raise
    else:
        if owns_backup:
            backup_path.unlink(missing_ok=True)


def serialize_wire_toml(payload: WireDict) -> str:
    """Serialize exactly as :func:`write_wire_toml` without touching disk."""
    return tomli_w.dumps(cast(dict[str, object], _tomlable(payload)))


def _tomlable(value: WireValue) -> object:
    """将 Wire dict 归一为 TOML 可写形态（去 None、UUID/Path → str）。"""
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if v is None:
                continue
            key = str(k) if isinstance(k, UUID) else k
            out[key] = _tomlable(v)
        return out
    if isinstance(value, list):
        return [_tomlable(v) for v in value if v is not None]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return value


def _first_wire_mismatch(
    expected: object,
    actual: object,
    *,
    path: str = "$",
) -> str | None:
    """Return the first lossy TOML round-trip path without exposing values."""
    if isinstance(expected, (UUID, Path)):
        expected = str(expected)

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return path
        normalized = {
            str(key) if isinstance(key, UUID) else key: value
            for key, value in expected.items()
        }
        if set(normalized) != set(actual):
            differing = sorted(
                str(key) for key in set(normalized).symmetric_difference(actual)
            )
            return f"{path}.{differing[0]}" if differing else path
        for key, value in normalized.items():
            mismatch = _first_wire_mismatch(
                value,
                actual[key],
                path=f"{path}.{key}",
            )
            if mismatch is not None:
                return mismatch
        return None

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return path
        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual, strict=True)
        ):
            mismatch = _first_wire_mismatch(
                expected_item,
                actual_item,
                path=f"{path}[{index}]",
            )
            if mismatch is not None:
                return mismatch
        return None

    # bool is a subclass of int, so equality alone cannot prove type fidelity.
    if type(expected) is not type(actual) or expected != actual:
        return path
    return None
