"""运行环境预检失败的备忘：更新提交前真建环境没建出来，记一笔。

MaaEnd v2.29.0 打包了 MaaFramework v5.14.0-beta.1 的原生库，binding 被钉成
``maafw==5.14.0b1``，而 PyPI 上没有这个版本——更新事务在 ``post_validate``
里真建运行环境时失败、回滚、继续跑旧版本。没有这份备忘的话，下一次运行前
更新又会下包、解压、建池、撞同一个缺包错误，每天白跑一遍。

备忘与 ``resource-manifest.json`` 同目录（``data/maafw_project_state/<hash>/``），
只由本包和宿主侧的 ``tools/embedded/precheck_gate.py`` 读写。结构::

    {
      "targetVersion": "v2.29.0",
      "requirement": "maafw==5.14.0b1",
      "kind": "binding_unavailable" | "other",
      "failedAt": "<ISO 8601>",
      "reason": "<≤500 字>",
      "attempts": n
    }

``kind`` 决定下次运行前怎么处理：``binding_unavailable`` 轻探一下索引和
GitHub、可得了才重新更新；``other``（磁盘满、解释器坏了……）不探、不自动
重试，等用户手动更新。本模块只用标准库：它在核心包里，不得 import ``app.*``。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .apply import _read_interface_version, project_state_dir_for

PRECHECK_MEMO_NAME = "runtime-precheck.json"
KIND_BINDING_UNAVAILABLE = "binding_unavailable"
KIND_OTHER = "other"
REASON_MAX_CHARS = 500
_MEMO_KEYS = ("targetVersion", "requirement", "kind", "failedAt", "reason", "attempts")

# 只认「索引里没有这个版本」的文本。连不上索引（``Request failed after 3
# retries`` / ``Failed to fetch``）与离线（``was not found in the cache``）都
# 不算：那是网络问题，下次可能就好了，不该按「binding 不存在」去轻探。
# 前三条是 uv 0.11.26 与 pip 的真实 stderr（agent 隔离 venv 仍经 pip 装 maafw）；
# 后几条是运行池 binding 目录（``runtime_pool/binding.py``）自己的文案：索引可达但
# 没有这个版本 / 没有满足范围的版本、没自带 DLL 的项目遇到只有源码 binding、映射不到
# 发布 tag——都是「这个版本拿不到 binding」，与网络无关。
_BINDING_UNAVAILABLE_PATTERNS = (
    re.compile(r"there is no version of maafw==", re.IGNORECASE),
    re.compile(r"maafw was not found in the package registry", re.IGNORECASE),
    re.compile(r"No matching distribution found for maafw==", re.IGNORECASE),
    re.compile(r"索引上没有 maafw"),
    re.compile(r"索引上没有满足"),
    re.compile(r"映射不到 MaaFramework 的发布 tag"),
    re.compile(r"源码打包的 binding 没有 DLL"),
    re.compile(r"binding 来自源码打包"),
)


def precheck_memo_path(
    project_path: Path,
    *,
    operation_root: Path | None = None,
) -> Path:
    return (
        project_state_dir_for(project_path, operation_root=operation_root)
        / PRECHECK_MEMO_NAME
    )


def read_runtime_precheck(
    project_path: Path,
    *,
    operation_root: Path | None = None,
) -> dict[str, Any] | None:
    """读备忘；没有、读不出、结构不对都当没有。"""

    path = precheck_memo_path(project_path, operation_root=operation_root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if not str(value.get("targetVersion") or "").strip():
        return None
    return value


def write_runtime_precheck(
    project_path: Path,
    payload: Mapping[str, Any],
    *,
    operation_root: Path | None = None,
) -> Path:
    """原子写备忘（临时文件 + ``os.replace``），只落 ``_MEMO_KEYS`` 里的键。

    ``attempts`` 缺省为 1：预检那一次本身就是第一次尝试，之后每次运行前
    被备忘挡下来时由读取方加一再写回。
    """

    path = precheck_memo_path(project_path, operation_root=operation_root)
    record: dict[str, Any] = {key: payload.get(key) for key in _MEMO_KEYS}
    record["targetVersion"] = str(record.get("targetVersion") or "").strip()
    record["requirement"] = str(record.get("requirement") or "maafw").strip()
    record["kind"] = (
        KIND_BINDING_UNAVAILABLE
        if record.get("kind") == KIND_BINDING_UNAVAILABLE
        else KIND_OTHER
    )
    record["failedAt"] = str(record.get("failedAt") or _now_iso())
    record["reason"] = str(record.get("reason") or "")[:REASON_MAX_CHARS]
    try:
        record["attempts"] = max(1, int(record.get("attempts") or 1))
    except (TypeError, ValueError):
        record["attempts"] = 1

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def clear_runtime_precheck(
    project_path: Path,
    *,
    operation_root: Path | None = None,
) -> bool:
    """删备忘，返回是否真删了什么。"""

    path = precheck_memo_path(project_path, operation_root=operation_root)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def memo_matches_version(memo: Mapping[str, Any], latest: str) -> bool:
    """备忘是不是记的就是这个目标版本（版本一变备忘就作废）。"""

    recorded = str(memo.get("targetVersion") or "").strip()
    candidate = str(latest or "").strip()
    if not recorded or not candidate:
        return False
    return recorded.lstrip("vV").casefold() == candidate.lstrip("vV").casefold()


def classify_precheck_kind(reason: str) -> str:
    """按失败文本判 ``kind``。"""

    text = str(reason or "")
    if any(pattern.search(text) for pattern in _BINDING_UNAVAILABLE_PATTERNS):
        return KIND_BINDING_UNAVAILABLE
    return KIND_OTHER


def classify_precheck_failure(
    project_path: Path,
    exc: BaseException,
    *,
    requirement: str | None = None,
    target_version: str | None = None,
) -> dict[str, Any]:
    """把一次预检异常整理成备忘条目（不落盘）。

    ``target_version`` 缺省从项目当前的 interface.json 读——预检跑在事务的
    ``post_validating`` 阶段，此时目录里已经是新版本。``requirement`` 由
    调用方解析（它要读项目自带的 DLL，逻辑在 runner 包里），没有就记
    ``"maafw"``（D4：不做 None 短路，requirement 只进备忘字段）。
    """

    reason = str(exc).strip() or type(exc).__name__
    version = str(target_version or "").strip()
    if not version:
        try:
            version = _read_interface_version(Path(project_path)).strip()
        except Exception:  # noqa: BLE001 - 读不到版本不该反过来盖住预检原因
            version = ""
    return {
        "targetVersion": version,
        "requirement": str(requirement or "maafw").strip() or "maafw",
        "kind": classify_precheck_kind(reason),
        "failedAt": _now_iso(),
        "reason": reason[:REASON_MAX_CHARS],
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


__all__ = [
    "KIND_BINDING_UNAVAILABLE",
    "KIND_OTHER",
    "PRECHECK_MEMO_NAME",
    "REASON_MAX_CHARS",
    "classify_precheck_failure",
    "classify_precheck_kind",
    "clear_runtime_precheck",
    "memo_matches_version",
    "precheck_memo_path",
    "read_runtime_precheck",
    "write_runtime_precheck",
]
