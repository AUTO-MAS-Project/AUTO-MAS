"""运行环境预检失败的备忘：更新提交前真建环境没建出来，记一笔。

MaaEnd v2.29.0 打包了 MaaFramework v5.14.0-beta.1 的原生库，binding 被钉成
``maafw==5.14.0b1``，而 PyPI 上没有这个版本——更新事务在 ``post_validate``
里真建运行环境时失败、回滚、继续跑旧版本。没有这份备忘的话，下一次运行前
更新又会下包、解压、建池、撞同一个缺包错误，每天白跑一遍。

备忘按**谱系 + 目标版本**记：``data/mfw/.payloads/<谱系>/precheck-<版本>.json``。
它是整个组共有的——一个成员预检过某版本失败，组里谁也不再为它下包。只由本包和
宿主侧的 ``tools/embedded/precheck_gate.py`` 读写。结构::

    {
      "targetVersion": "v2.29.0",
      "requirement": "maafw==5.14.0b1",
      "kind": "binding_unavailable" | "transient" | "other",
      "failedAt": "<ISO 8601>",
      "reason": "<≤500 字>",
      "attempts": n
    }

``kind`` 决定下次运行前怎么处理：``binding_unavailable`` 轻探一下索引和
GitHub、可得了才重新更新；``transient``（连不上包索引、下载失败、各种超时——
下次多半就好了）下次运行前直接重试；``other``（磁盘满、解释器坏了、依赖确实
装不上……）不探、不自动重试，等用户手动更新。本模块只用标准库：它在核心包里，
不得 import ``app.*``。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .apply import _read_interface_version

PRECHECK_MEMO_PREFIX = "precheck-"
_VERSION_UNSAFE_RE = re.compile(r"[^0-9A-Za-z._+-]+")
KIND_BINDING_UNAVAILABLE = "binding_unavailable"
KIND_TRANSIENT = "transient"
KIND_OTHER = "other"
_KINDS = frozenset({KIND_BINDING_UNAVAILABLE, KIND_TRANSIENT, KIND_OTHER})
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

# 网络与超时：预检时建运行池 / 隔离 venv 要联网装包，碰上一次网络抖动或冷启动慢盘就
# 失败，这类失败下次运行前多半就好了，不该与「磁盘满、依赖确实装不上」一样等手动更新。
# 排在 binding 判断之后：pip 连不上索引时末尾常是「No matching distribution found for
# maafw==…」，那条已归 binding_unavailable、走轻探自愈。前几条是 MAS 自己的文案
# （runtime_pool/binding.py、agent_env/env.py、runtime_pool/installer.py），其余是
# uv / pip / httpx / urllib3 / Windows 套接字的网络报错原文。离线模式（``was not found
# in the cache``）不算：那是用户的设置，重试不会变。
_TRANSIENT_PATTERNS = (
    re.compile(r"所有包索引都连不上"),
    re.compile(r"下载 wheel 失败"),
    re.compile(r"超时"),
    re.compile(r"Request failed after \d+ retr", re.IGNORECASE),
    re.compile(r"Failed to fetch", re.IGNORECASE),
    re.compile(r"error sending request", re.IGNORECASE),
    re.compile(r"tcp connect error", re.IGNORECASE),
    re.compile(r"dns error", re.IGNORECASE),
    re.compile(r"Could not fetch URL", re.IGNORECASE),
    re.compile(r"Max retries exceeded", re.IGNORECASE),
    re.compile(r"(?:Connect|Read)TimeoutError", re.IGNORECASE),
    re.compile(r"\btimed out\b", re.IGNORECASE),
    re.compile(r"NewConnectionError|ConnectionResetError|RemoteDisconnected"),
    re.compile(r"Connection (?:refused|reset|aborted)", re.IGNORECASE),
    re.compile(r"Temporary failure in name resolution", re.IGNORECASE),
    re.compile(r"getaddrinfo failed", re.IGNORECASE),
    re.compile(r"Name or service not known", re.IGNORECASE),
    re.compile(r"No connection could be made", re.IGNORECASE),
    re.compile(r"ProxyError", re.IGNORECASE),
)


def precheck_memo_path(payloads_root: Path, lineage: str, version: str) -> Path:
    """某谱系某目标版本的预检备忘路径（版本号去掉前导 v、非法字符换成 ``_``）。"""

    text = str(version or "").strip().lstrip("vV").casefold()
    safe = _VERSION_UNSAFE_RE.sub("_", text).strip("._-") or "unknown"
    return Path(payloads_root) / str(lineage) / f"{PRECHECK_MEMO_PREFIX}{safe}.json"


def read_runtime_precheck(path: Path) -> dict[str, Any] | None:
    """读备忘；没有、读不出、结构不对都当没有。"""

    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if not str(value.get("targetVersion") or "").strip():
        return None
    return value


def write_runtime_precheck(path: Path, payload: Mapping[str, Any]) -> Path:
    """原子写备忘（临时文件 + ``os.replace``），只落 ``_MEMO_KEYS`` 里的键。

    ``attempts`` 缺省为 1：预检那一次本身就是第一次尝试，之后每次运行前
    被备忘挡下来时由读取方加一再写回。
    """

    path = Path(path)
    record: dict[str, Any] = {key: payload.get(key) for key in _MEMO_KEYS}
    record["targetVersion"] = str(record.get("targetVersion") or "").strip()
    record["requirement"] = str(record.get("requirement") or "maafw").strip()
    record["kind"] = record.get("kind") if record.get("kind") in _KINDS else KIND_OTHER
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


def clear_runtime_precheck(path: Path) -> bool:
    """删备忘，返回是否真删了什么。"""

    try:
        Path(path).unlink()
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
    if any(pattern.search(text) for pattern in _TRANSIENT_PATTERNS):
        return KIND_TRANSIENT
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
    "KIND_TRANSIENT",
    "PRECHECK_MEMO_PREFIX",
    "REASON_MAX_CHARS",
    "classify_precheck_failure",
    "classify_precheck_kind",
    "clear_runtime_precheck",
    "memo_matches_version",
    "precheck_memo_path",
    "read_runtime_precheck",
    "write_runtime_precheck",
]
