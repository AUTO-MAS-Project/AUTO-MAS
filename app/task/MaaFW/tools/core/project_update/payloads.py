"""MFW 项目载荷：按「谱系 + 版本 + 内容哈希」登记的不可变项目树，全局一份。

布局（``root`` 由宿主给出，即 ``data/mfw/.payloads``）::

    <root>/<lineage12>/lineage.json          谱系：名称、rid、github、configClass、
                                             每渠道的 latest、privatePaths、damaged
    <root>/<lineage12>/<版本>-<hash8>/        载荷树（不可变：大文件是 blob 的硬链接，小文件拷贝）
    <root>/<lineage12>/<版本>-<hash8>.json    载荷清单 {version, files: {rel: {sha256, size, origin}} …}

每个脚本的视图（``data/mfw/<12hex>``）是一棵完整目录树：清单里的文件从载荷链接 / 拷贝
过去，运行期产物留在视图里私有。视图怎么建、怎么切换是宿主接缝层的事，这里只管载荷。

**写穿防线**：往 staging 写任何文件之前先 ``unlink`` 目标，``os.link`` 失败才退回
``O_EXCL`` 复制（:func:`place_fresh`）——staging 里的文件多数是载荷 / blob 的硬链接，
往已存在的目标里写就等于改载荷。

零宿主耦合：只依赖标准库、``packaging`` 与本包内的模块（worker 导入闭包约束）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from .apply import (
    PackagePlan,
    UpdateApplyError,
    _apply_progress_step,
    _import_origin_orphans,
    _validate_plan_base,
    build_package_plan,
)
from .blob_store import RuntimeBlobStore, _copy_exclusive, place_fresh, sha256_file
from .contracts import (
    VIEW_MARKER_FILE_NAME,
    canonical_json,
    project_fingerprint,
    safe_relative_path,
)
from .projection import (
    ProjectionPlan,
    build_projection_plan,
    is_shared_path,
    materialize_projection,
    read_json_object,
)
from .state import DurableFileLock

logger = logging.getLogger("automas.maafw.project_update.payloads")

SCHEMA_VERSION = 1
LINEAGE_FILE_NAME = "lineage.json"
LINEAGE_LOCK_NAME = ".lineage.lock"
ORIGIN_IMPORT = "import"
ORIGIN_PACKAGE = "package"
# 登记前从 staging 剔掉的运行期目录（预检 / 准备环境会在 staging 上写这些）。
PAYLOAD_STRIP_ROOT_DIRS = frozenset({"debug", "logs", "temp", ".pycache"})

_LINEAGE_KEY_RE = re.compile(r"^[0-9a-f]{12}$")
_PAYLOAD_ID_RE = re.compile(r"^[0-9A-Za-z._+-]{1,80}-[0-9a-f]{8}$")
_VERSION_UNSAFE_RE = re.compile(r"[^0-9A-Za-z._+-]+")


class PayloadError(RuntimeError):
    """载荷操作失败。"""


class PayloadCancelled(PayloadError):
    """构建新载荷期间用户停了任务；staging 由调用方丢弃，没有要回滚的东西。"""


@dataclass
class PayloadTarget:
    """一次更新要落到哪：谱系、触发脚本当前挂的载荷、渠道、staging 与共用库。

    宿主（``tools/embedded``）按视图标记组装，核心更新流程据此从当前载荷 + 更新包
    在 staging 里建新载荷、预检、登记。
    """

    root: Path
    lineage: str
    payload_id: str
    channel: str
    by: str
    staging_root: Path
    blob_store: RuntimeBlobStore
    private_paths: tuple[str, ...] = ()
    lineage_info: Mapping[str, Any] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        value = read_manifest(self.root, self.lineage, self.payload_id)
        if value is None:
            raise PayloadError(f"当前项目版本 {self.payload_id} 的清单不在本机")
        return value

    def directory(self) -> Path:
        return payload_dir(self.root, self.lineage, self.payload_id)


def _clear_readonly_and_retry(func: Callable[[str], Any], path: str, _exc: Any) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def long_path(path: Path | str) -> str:
    """Windows 上转成 ``\\\\?\\`` 扩展路径：搬进 ``.staging`` 的树比原位置深二三十个字符，
    pyc 镜像树这类本来就贴着 MAX_PATH 的深路径在那里删不掉。其它系统原样返回。"""

    text = os.path.abspath(str(path))
    if os.name != "nt" or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def remove_tree(path: Path) -> None:
    if os.path.lexists(path):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(long_path(path), onexc=_clear_readonly_and_retry)
        else:
            path.unlink()


# --------------------------------------------------------------------------
# 谱系
# --------------------------------------------------------------------------


def _field(interface: Any, *names: str) -> str:
    for name in names:
        if isinstance(interface, Mapping):
            value = interface.get(name)
        else:
            value = getattr(interface, name, None)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_github(raw: str) -> str:
    value = raw.strip().removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if value.casefold().startswith(prefix):
            value = value[len(prefix) :]
            break
    parts = value.strip("/").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return ""
    return f"{parts[0]}/{parts[1]}"


def lineage_identity(interface: Any) -> str:
    """谱系身份原文：``mirrorchyan_rid`` > ``github``（owner/repo）> ``name``，大小写不敏感。"""

    rid = _field(interface, "mirrorchyan_rid", "mirrorchyanRid")
    if rid:
        return f"rid:{rid.casefold()}"
    github = _normalize_github(_field(interface, "github"))
    if github:
        return f"github:{github.casefold()}"
    name = _field(interface, "name")
    if name:
        return f"name:{name.casefold()}"
    raise PayloadError(
        "interface 里没有 mirrorchyan_rid / github / name，无法确定项目谱系"
    )


def lineage_key(interface: Any) -> str:
    """谱系键：身份原文 sha256 取 12 位。``interface`` 可以是原始 dict 或模型对象。"""

    return hashlib.sha256(lineage_identity(interface).encode("utf-8")).hexdigest()[:12]


def read_project_interface(project_dir: Path) -> dict[str, Any]:
    for name in ("interface.json", "interface.jsonc"):
        candidate = Path(project_dir) / name
        if candidate.is_file():
            return read_json_object(candidate, "ProjectInterface")
    raise PayloadError(f"项目目录里没有 interface.json：{project_dir}")


def lineage_key_for_project(project_dir: Path) -> str:
    return lineage_key(read_project_interface(project_dir))


def lineage_info_from_interface(interface: Any) -> dict[str, str]:
    return {
        "name": _field(interface, "name"),
        "mirrorchyanRid": _field(interface, "mirrorchyan_rid", "mirrorchyanRid"),
        "github": _field(interface, "github"),
    }


def _check_lineage_key(key: str) -> str:
    if not _LINEAGE_KEY_RE.fullmatch(str(key or "")):
        raise PayloadError(f"谱系键不合法：{key!r}")
    return key


def _check_payload_id(payload_id: str) -> str:
    if not _PAYLOAD_ID_RE.fullmatch(str(payload_id or "")):
        raise PayloadError(f"载荷 id 不合法：{payload_id!r}")
    return payload_id


def lineage_dir(root: Path, key: str) -> Path:
    return Path(root) / _check_lineage_key(key)


def payload_dir(root: Path, key: str, payload_id: str) -> Path:
    return lineage_dir(root, key) / _check_payload_id(payload_id)


def manifest_path(root: Path, key: str, payload_id: str) -> Path:
    return lineage_dir(root, key) / f"{_check_payload_id(payload_id)}.json"


def payload_ref(key: str, payload_id: str) -> str:
    """回收引用集里的键：``<lineage>/<payload id>``。"""

    return f"{key}/{payload_id}"


def _empty_lineage(key: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "lineage": key,
        "name": "",
        "mirrorchyanRid": "",
        "github": "",
        "configClass": "",
        "latest": {},
        "privatePaths": [],
        "damaged": [],
        "knownSources": [],
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def read_lineage(root: Path, key: str) -> dict[str, Any]:
    data = _empty_lineage(key)
    stored = _read_json(lineage_dir(root, key) / LINEAGE_FILE_NAME)
    if stored:
        data.update(stored)
    if not isinstance(data.get("latest"), dict):
        data["latest"] = {}
    for list_key in ("privatePaths", "damaged", "knownSources"):
        if not isinstance(data.get(list_key), list):
            data[list_key] = []
    data["lineage"] = key
    return data


def write_lineage(root: Path, key: str, data: Mapping[str, Any]) -> None:
    write_json_atomic(lineage_dir(root, key) / LINEAGE_FILE_NAME, dict(data))


@contextmanager
def lineage_lock(
    root: Path, key: str, *, timeout: float | None = None
) -> Iterator[None]:
    """``lineage.json`` 读改写的跨进程锁（短锁；与更新流程的谱系锁不是同一把）。"""

    directory = lineage_dir(root, key)
    directory.mkdir(parents=True, exist_ok=True)
    with DurableFileLock(directory / LINEAGE_LOCK_NAME, timeout=timeout):
        yield


def version_newer(candidate: str, current: str) -> bool:
    """``candidate`` 是否比 ``current`` 新；与更新器 ``_is_remote_newer`` 同一口径。"""

    remote = str(candidate or "").strip()
    local = str(current or "").strip()
    if not remote:
        return False
    if not local:
        return True
    try:
        return Version(remote.lstrip("vV")) > Version(local.lstrip("vV"))
    except InvalidVersion:
        return remote != local


# --------------------------------------------------------------------------
# 清单
# --------------------------------------------------------------------------


def manifest_files(manifest: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """清单里的 ``files``，统一成 ``{rel: {sha256, size, origin}}``。"""

    raw = (manifest or {}).get("files")
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, Mapping):
        return result
    for rel, entry in raw.items():
        if isinstance(entry, Mapping):
            result[str(rel)] = {
                "sha256": str(entry.get("sha256") or ""),
                "size": int(entry.get("size") or 0),
                "origin": str(entry.get("origin") or ORIGIN_IMPORT),
            }
        else:
            result[str(rel)] = {
                "sha256": str(entry or ""),
                "size": 0,
                "origin": ORIGIN_IMPORT,
            }
    return result


def read_manifest(root: Path, key: str, payload_id: str) -> dict[str, Any] | None:
    return _read_json(manifest_path(root, key, payload_id))


def latest(root: Path, key: str, channel: str) -> dict[str, Any] | None:
    entry = read_lineage(root, key)["latest"].get(str(channel or ""))
    return dict(entry) if isinstance(entry, Mapping) and entry.get("id") else None


def list_ids(root: Path, key: str) -> list[str]:
    """谱系下完整登记的载荷（目录与清单都在）。"""

    directory = lineage_dir(root, key)
    if not directory.is_dir():
        return []
    ids = []
    for entry in directory.iterdir():
        if entry.is_dir() and _PAYLOAD_ID_RE.fullmatch(entry.name):
            if (directory / f"{entry.name}.json").is_file():
                ids.append(entry.name)
    return sorted(ids)


def list_lineages(root: Path) -> list[str]:
    base = Path(root)
    if not base.is_dir():
        return []
    return sorted(
        entry.name
        for entry in base.iterdir()
        if entry.is_dir() and _LINEAGE_KEY_RE.fullmatch(entry.name)
    )


def mark_damaged(root: Path, key: str, payload_id: str) -> None:
    _check_payload_id(payload_id)
    with lineage_lock(root, key):
        data = read_lineage(root, key)
        if payload_id not in data["damaged"]:
            data["damaged"].append(payload_id)
            write_lineage(root, key, data)


def add_private_path(root: Path, key: str, relative: str) -> None:
    rel = safe_relative_path(relative)
    with lineage_lock(root, key):
        data = read_lineage(root, key)
        if rel.casefold() not in {
            str(item).casefold() for item in data["privatePaths"]
        }:
            data["privatePaths"].append(rel)
            write_lineage(root, key, data)


def private_paths(root: Path, key: str) -> list[str]:
    return [str(item) for item in read_lineage(root, key)["privatePaths"]]


def _normalize_source(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        return ""
    return os.path.normcase(os.path.normpath(os.path.abspath(text)))


def add_known_source(root: Path, key: str, source: str) -> None:
    """记下「这个谱系的项目曾从 ``source`` 目录导入 / 采纳」（``lineage.json.knownSources``）。

    与载荷清单的 ``source.ref`` 不同：更新得来的载荷没有导入目录，但脚本配置里仍记着
    ``Info.Path``——视图丢了要靠它反查谱系重建，整谱系回收也要靠它认出「脚本还在」。
    """

    normalized = _normalize_source(source)
    if not normalized:
        return
    with lineage_lock(root, key):
        data = read_lineage(root, key)
        known = [str(item) for item in data.get("knownSources") or []]
        if normalized not in known:
            known.append(normalized)
            data["knownSources"] = known
            write_lineage(root, key, data)


def lineage_by_known_source(root: Path, source: str) -> str | None:
    """``source`` 目录属于哪个谱系（查各谱系的 ``knownSources``）；没有返回 None。"""

    normalized = _normalize_source(source)
    if not normalized:
        return None
    for key in list_lineages(root):
        known = read_lineage(root, key).get("knownSources") or []
        if normalized in {str(item) for item in known}:
            return key
    return None


# --------------------------------------------------------------------------
# 构建（产物都在 staging；登记前不碰任何载荷与视图）
# --------------------------------------------------------------------------


@dataclass
class SourceBuild:
    plan: ProjectionPlan
    shared_files: int
    shared_bytes: int


def build_from_source(
    source_dir: Path,
    staging: Path,
    *,
    blob_store: RuntimeBlobStore | None = None,
    private: Iterable[str] = (),
    progress: Callable[[int, int], None] | None = None,
    plan: ProjectionPlan | None = None,
) -> SourceBuild:
    """来源目录 → staging 里的投影树（即 ``import_embedded_project`` 的投影部分）。

    产物文件的 ``origin`` 全部是 ``import``（登记时的默认值）。调用方已经为了算谱系
    建过投影计划时可以传 ``plan``，省一次整树扫描。
    """

    if plan is None:
        plan = build_projection_plan(Path(source_dir))
    shared = materialize_projection(
        plan,
        staging,
        progress=progress,
        blob_store=blob_store,
        private_paths=private,
    )
    return SourceBuild(
        plan=plan,
        shared_files=int(shared["sharedFiles"]),
        shared_bytes=int(shared["sharedBytes"]),
    )


@dataclass
class PackageBuild:
    plan: PackagePlan
    stale: set[str]
    origins: dict[str, str]
    applied_files: int = 0


def clone_payload_into(payload_root: Path, files: Iterable[str], staging: Path) -> None:
    """把载荷里的 ``files`` 摆进 staging：多链接的（blob）挂硬链接，其余复制。"""

    for rel in files:
        source = payload_root / rel
        place_fresh(source, staging / rel, link=source.stat().st_nlink > 1)


def build_from_package(
    old_manifest: Mapping[str, Any],
    old_payload_dir: Path,
    package_root: Path,
    extract_dir: Path,
    staging: Path,
    *,
    blob_store: RuntimeBlobStore | None = None,
    private: Iterable[str] = (),
    send_log: Callable[[str], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    expected_package_type: str | None = None,
    target_version: str | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> PackageBuild:
    """旧载荷 + 更新包 → staging 里的新载荷树（§3.1 第 4 步）。

    - 全量包：stale = 旧载荷里 ``origin=package`` 且不在包内的 ∪ ``origin=import``、位于
      新 interface 声明的资源目录内、且不在包内的；资源目录之外的 ``import`` 文件带进新载荷。
    - 差量包：以旧载荷清单为基线校验（载荷不可变，清单记的指纹就是它当前的指纹），
      stale = 包声明的删除表。
    包内条目一律 ``origin=package``。失败时调用方直接丢掉 staging。

    ``on_event(stage, payload)`` 按更新进度的阶段词发：``plan_validated``（计划校验完）→
    ``staged``（旧载荷已复制成新版本骨架）→ ``applying``（逐文件套包，带
    ``appliedFiles`` / ``totalFiles``）。``cancelled()`` 为真时在两步之间抛
    :class:`PayloadCancelled`，staging 由调用方丢弃。
    """

    def emit(stage: str, **payload: Any) -> None:
        if on_event is not None:
            try:
                on_event(stage, payload)
            except Exception:  # noqa: BLE001 - 进度只是旁观
                pass

    def check_cancel() -> None:
        if cancelled is not None and cancelled():
            raise PayloadCancelled("update cancelled")

    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    staging = staging.resolve()
    old_root = Path(old_payload_dir).resolve()
    old_files = manifest_files(old_manifest)
    private_list = tuple(private)
    compat_manifest = {
        "files": {rel: entry["sha256"] for rel, entry in old_files.items()},
        "projectFingerprint": str(old_manifest.get("fingerprint") or ""),
    }
    # 计划只读旧载荷（投影白名单的叠加视图、差量基线版本），不碰 staging。
    try:
        plan = build_package_plan(
            package_root,
            extract_dir,
            old_root,
            old_manifest=compat_manifest,
            expected_package_type=expected_package_type,  # type: ignore[arg-type]
            target_version=target_version,
            projection=True,
            send_log=send_log,
        )
        _validate_plan_base(
            old_root,
            plan,
            compat_manifest,
            str(old_manifest.get("fingerprint") or "").strip().lower(),
        )
    except UpdateApplyError as exc:
        raise PayloadError(str(exc)) from exc

    if plan.package_type == "full":
        stale = {
            rel
            for rel, entry in old_files.items()
            if entry["origin"] == ORIGIN_PACKAGE and rel not in plan.files
        }
        import_files = {
            rel for rel, entry in old_files.items() if entry["origin"] != ORIGIN_PACKAGE
        }
        stale |= _import_origin_orphans(old_root, plan) & import_files
    else:
        # 删除表里可能是目录（``deleted_dir``）：目录下的旧文件一起清。
        deleted = [item.rstrip("/") for item in plan.deleted if item]
        stale = {
            rel
            for rel in old_files
            if any(rel == item or rel.startswith(f"{item}/") for item in deleted)
        }
    emit("plan_validated", packageType=plan.package_type)
    check_cancel()

    clone_payload_into(
        old_root, (rel for rel in old_files if rel not in stale), staging
    )
    emit("staged")
    check_cancel()

    total = len(plan.files)
    applied = 0
    step = _apply_progress_step(total)
    next_report = step
    emit("applying", appliedFiles=0, totalFiles=total)
    for rel, source in plan.files.items():
        target = staging / rel
        size = source.stat().st_size
        if blob_store is not None and is_shared_path(rel, size, private_list):
            blob_store.place(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(target):
                os.unlink(target)
            try:
                os.replace(source, target)
            except OSError:
                _copy_exclusive(source, target)
        applied += 1
        if progress is not None:
            progress(applied, total)
        if applied >= next_report or applied == total:
            next_report = applied + step
            emit("applying", appliedFiles=applied, totalFiles=total)
            check_cancel()

    origins = {
        rel: entry["origin"] for rel, entry in old_files.items() if rel not in stale
    }
    for rel in plan.files:
        origins[rel] = ORIGIN_PACKAGE
    return PackageBuild(plan=plan, stale=stale, origins=origins, applied_files=applied)


@dataclass
class FinalizeResult:
    hashes: dict[str, str] = field(default_factory=dict)
    ingested_files: int = 0
    ingested_bytes: int = 0


def _iter_files(root: Path) -> Iterator[tuple[str, Path]]:
    def _error(exc: OSError) -> None:
        raise PayloadError(f"读不了目录：{exc.filename}: {exc}") from exc

    for current, dir_names, file_names in os.walk(root, onerror=_error):
        dir_names.sort()
        base = Path(current)
        # 相对路径每个目录只算一次、文件名直接拼：以前每个文件一次 relative_to，
        # MaaFgo 这类上万文件的载荷登记时是个大头。os.walk 给的 current 就是 root 拼出来的，
        # 与 relative_to(root).as_posix() 结果相同。
        rel_dir = os.path.relpath(current, root).replace(os.sep, "/")
        prefix = "" if rel_dir == "." else f"{rel_dir}/"
        for name in sorted(file_names):
            path = base / name
            if path.is_symlink():
                raise PayloadError(f"载荷里不允许符号链接：{path}")
            yield f"{prefix}{name}", path


def finalize(
    staging: Path,
    *,
    blob_store: RuntimeBlobStore | None = None,
    private: Iterable[str] = (),
) -> FinalizeResult:
    """登记前的收尾：剔掉运行期目录与视图标记，把还私有的共用候选就地入库。"""

    staging = Path(staging)
    for entry in list(staging.iterdir()):
        if entry.is_dir() and entry.name.casefold() in PAYLOAD_STRIP_ROOT_DIRS:
            remove_tree(entry)
    marker = staging / VIEW_MARKER_FILE_NAME
    if os.path.lexists(marker):
        marker.unlink()

    result = FinalizeResult()
    if blob_store is None:
        return result
    private_list = tuple(private)
    for rel, path in _iter_files(staging):
        info = path.stat()
        if info.st_nlink != 1 or not is_shared_path(rel, info.st_size, private_list):
            continue
        placed = blob_store.ingest_in_place(path)
        if placed.digest:
            result.hashes[rel] = placed.digest
        if placed.action == "linked":
            result.ingested_files += 1
            result.ingested_bytes += placed.size
    return result


# --------------------------------------------------------------------------
# 登记
# --------------------------------------------------------------------------


@dataclass
class RegisterResult:
    payload_id: str
    latest_id: str
    created: bool
    advanced: bool
    manifest: dict[str, Any]
    # latest 指的载荷在不在本机；不在时调用方先切到这次登记的那份。
    latest_available: bool = True

    @property
    def target_id(self) -> str:
        """视图该切到的载荷：组的 latest；它丢了就先用这次登记的。"""

        return self.latest_id if self.latest_available else self.payload_id


def _safe_version(version: str) -> str:
    text = _VERSION_UNSAFE_RE.sub("_", str(version or "").strip()).strip("._-")
    return text[:64] or "0"


def content_id(version: str, files: Mapping[str, Mapping[str, Any]]) -> str:
    """载荷 id：只由 version 与 ``files{rel: (sha256, size)}`` 决定。"""

    canonical = canonical_json(
        {
            "version": str(version or ""),
            "files": {
                rel: {"sha256": entry["sha256"], "size": int(entry["size"])}
                for rel, entry in files.items()
            },
        }
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
    return f"{_safe_version(version)}-{digest}"


def _now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def register(
    root: Path,
    staging: Path,
    *,
    lineage: str,
    channel: str,
    source: Mapping[str, Any],
    by: str,
    version: str | None = None,
    lineage_info: Mapping[str, Any] | None = None,
    known_hashes: Mapping[str, str] | None = None,
    origins: Mapping[str, str] | None = None,
    bundled: Mapping[str, Any] | None = None,
) -> RegisterResult:
    """把 staging 登记成载荷并推进 ``latest[channel]``。

    - 同 id 已存在：丢弃 staging、既有目录不动，只把清单里的 ``origin`` 合并（``package``
      胜过 ``import``）。
    - ``latest[channel]`` **只在版本严格更高时前进**；版本相同而 id 不同时保留既有 id
      （新建的这份不登记为 latest，等启动期回收）。返回的 ``latest_id`` 就是调用方该把
      视图切到的那个。``latest`` 指向的目录丢了才无条件换成这份。
    """

    staging = Path(staging)
    channel = str(channel or "").strip()
    if not channel:
        raise PayloadError("登记载荷需要渠道")
    if version is None:
        version = str(read_project_interface(staging).get("version") or "")
    default_origin = (
        ORIGIN_PACKAGE if str(source.get("kind") or "") == "update" else ORIGIN_IMPORT
    )
    hashes = dict(known_hashes or {})
    files: dict[str, dict[str, Any]] = {}
    for rel, path in _iter_files(staging):
        digest = hashes.get(rel) or sha256_file(path)
        files[rel] = {
            "sha256": digest,
            "size": path.stat().st_size,
            "origin": str((origins or {}).get(rel) or default_origin),
        }
    payload_id = content_id(version, files)
    fingerprint = project_fingerprint(staging)
    if fingerprint is None:
        raise PayloadError(f"算不出载荷指纹：{staging}")
    manifest: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "id": payload_id,
        "lineage": lineage,
        "version": version,
        "channel": channel,
        "source": dict(source),
        "builtAt": _now_text(),
        "fingerprint": fingerprint,
        "bundledMaaFW": str((bundled or {}).get("maafw") or ""),
        "bundledPython": str((bundled or {}).get("python") or ""),
        "files": files,
    }

    target = payload_dir(root, lineage, payload_id)
    manifest_file = manifest_path(root, lineage, payload_id)
    with lineage_lock(root, lineage):
        existing = _read_json(manifest_file) if target.is_dir() else None
        if existing is not None:
            created = False
            merged = dict(existing)
            merged_files = manifest_files(existing)
            changed = False
            for rel, entry in files.items():
                current = merged_files.get(rel)
                if (
                    current is not None
                    and entry["origin"] == ORIGIN_PACKAGE
                    and current["origin"] != ORIGIN_PACKAGE
                ):
                    current["origin"] = ORIGIN_PACKAGE
                    changed = True
            if (
                str(source.get("kind") or "") == "update"
                and str((existing.get("source") or {}).get("kind") or "") != "update"
            ):
                # 同一份内容这次有更新器清单背书：来源升成 update（下次更新可要差量包）。
                # 与 origin 合并同一口径，结果不取决于谁先登记。
                merged["source"] = dict(source)
                changed = True
            if changed:
                merged["files"] = merged_files
                write_json_atomic(manifest_file, merged)
            manifest = merged
            remove_tree(staging)
        else:
            created = True
            if target.exists():
                # 目录在、清单没了：不可信的半成品，换掉。
                remove_tree(target)
            write_json_atomic(manifest_file, manifest)
            try:
                os.rename(staging, target)
            except OSError:
                try:
                    manifest_file.unlink()
                except OSError:
                    pass
                raise

        data = read_lineage(root, lineage)
        for info_key, info_value in (lineage_info or {}).items():
            if str(info_value or "").strip():
                data[info_key] = str(info_value)
        current_latest = data["latest"].get(channel)
        if not isinstance(current_latest, Mapping) or not current_latest.get("id"):
            advanced = True
        else:
            current_version = str(current_latest.get("version") or "")
            if (lineage_dir(root, lineage) / str(current_latest["id"])).is_dir():
                advanced = version_newer(version, current_version)
            else:
                # latest 指的目录丢了：只有新登记的不比它旧才顶上去，否则组会后退；
                # 保留原 latest，缺失的载荷由自愈 / 迁移处理。
                advanced = not version_newer(current_version, version)
                if not advanced:
                    logger.warning(
                        "谱系 %s 渠道 %s 的 latest 载荷 %s 不在本机，新登记的 %s 更旧，"
                        "保留原 latest",
                        lineage,
                        channel,
                        current_latest["id"],
                        payload_id,
                    )
        if advanced:
            data["latest"][channel] = {
                "id": payload_id,
                "version": version,
                "source": dict(source),
                "by": by,
                "at": _now_text(),
            }
        elif (
            isinstance(current_latest, Mapping)
            and str(current_latest.get("id") or "") == payload_id
            and str(manifest.get("source", {}).get("kind") or "") == "update"
        ):
            # 同一份内容的来源刚升成 update：latest 记的来源跟着清单走。
            data["latest"][channel] = {
                **dict(current_latest),
                "source": dict(manifest["source"]),
            }
        write_lineage(root, lineage, data)
        latest_id = str(data["latest"][channel]["id"])
        latest_available = (lineage_dir(root, lineage) / latest_id).is_dir()
    return RegisterResult(
        payload_id=payload_id,
        latest_id=latest_id,
        created=created,
        advanced=bool(advanced),
        manifest=manifest,
        latest_available=latest_available,
    )


def _same_version_rank(
    candidate: str, manifests: Mapping[str, Mapping[str, Any]]
) -> tuple[int, int, int, int]:
    """同版本多份载荷里挑谁当 latest 的排序键（越大越好；最后按 id 字典序兜底）。

    1. ``source.kind=update``（有更新器清单背书）优先；
    2. 文件集合是其它几份的超集的优先（超过几份就记几分）；
    3. 文件数多、总字节大的优先。
    与登记顺序无关——迁移时登记顺序就是脚本列表顺序，用户拖一下就会变。
    """

    manifest = manifests[candidate]
    files = manifest_files(manifest)
    keys = {rel.casefold() for rel in files}
    supersets = 0
    for other, other_manifest in manifests.items():
        if other == candidate:
            continue
        other_keys = {rel.casefold() for rel in manifest_files(other_manifest)}
        if other_keys < keys:
            supersets += 1
    is_update = int(str((manifest.get("source") or {}).get("kind") or "") == "update")
    total = sum(int(entry.get("size") or 0) for entry in files.values())
    return (is_update, supersets, len(files), total)


def settle_same_version_latest(root: Path, key: str, channel: str) -> str | None:
    """``latest[channel]`` 所在版本有多份载荷时，按 :func:`_same_version_rank` 确定地挑一份。

    迁移先把全部副本登记完再调它（登记是「同版本保留先来的」，先来的可能是残缺的那份），
    然后才统一切换。返回换成的 id；没变返回 None。损坏（``damaged``）或目录不在的不参选。
    """

    with lineage_lock(root, key):
        data = read_lineage(root, key)
        entry = data["latest"].get(channel)
        if not isinstance(entry, Mapping) or not entry.get("id"):
            return None
        version = str(entry.get("version") or "").strip().lstrip("vV")
        if not version:
            return None
        damaged = {str(item) for item in data.get("damaged") or []}
        manifests: dict[str, dict[str, Any]] = {}
        for payload_id in list_ids(root, key):
            if payload_id in damaged or not payload_dir(root, key, payload_id).is_dir():
                continue
            manifest = read_manifest(root, key, payload_id)
            if manifest is None:
                continue
            if str(manifest.get("version") or "").strip().lstrip("vV") != version:
                continue
            manifests[payload_id] = manifest
        if len(manifests) < 2:
            return None
        chosen = sorted(
            manifests,
            key=lambda pid: (_same_version_rank(pid, manifests), _reverse_text(pid)),
            reverse=True,
        )[0]
        if chosen == str(entry["id"]):
            return None
        data["latest"][channel] = {
            **dict(entry),
            "id": chosen,
            "version": str(manifests[chosen].get("version") or entry.get("version")),
            "source": dict(manifests[chosen].get("source") or {}),
            "at": _now_text(),
        }
        write_lineage(root, key, data)
        return chosen


def _reverse_text(text: str) -> tuple[int, ...]:
    """让 ``sorted(..., reverse=True)`` 在排序键打平时按 id **升序**取第一个。"""

    return tuple(-ord(char) for char in text)


# --------------------------------------------------------------------------
# 回收判定（删除由宿主做）
# --------------------------------------------------------------------------


def collect_unreferenced(
    root: Path,
    referenced: set[str],
    started_at: float,
    *,
    live_lineages: set[str] | None = None,
) -> list[Path]:
    """列出可以删的载荷目录与清单文件（以及整个谱系目录）。

    ``referenced`` 由宿主按引用集算：所有视图标记的 ``payload`` ∪ 未完成 journal 的
    ``to``，元素写 ``<lineage>/<id>``（:func:`payload_ref`）或裸 id。

    ``live_lineages``：还有视图（或未完成 journal）的谱系。给了的话，不在其中的谱系
    整个目录（全部载荷、``lineage.json``、预检备忘）都可回收；``latest[*]`` 只在谱系仍
    有视图时才算引用——没有脚本再用的项目不该因为「它是最新版」永远占着盘。不给则
    沿用旧口径：每个谱系的 ``latest[*]`` 都算引用。

    mtime 不早于 ``started_at`` 的（本进程起来之后才建 / 才登记过的）一律不收。
    """

    candidates: list[Path] = []
    for key in list_lineages(root):
        directory = lineage_dir(root, key)
        if live_lineages is not None and key not in live_lineages:
            # 只看谱系里的内容：锁文件每次加锁都会写 owner 信息（回收自己在锁内复核时也会），
            # 目录本身的修改时间随锁文件的创建变化；新登记的清单 / 载荷目录 / lineage.json
            # 自己就带着新的修改时间。
            try:
                newest = max(
                    [
                        entry.stat().st_mtime
                        for entry in directory.iterdir()
                        if entry.name != LINEAGE_LOCK_NAME
                    ]
                    or [0.0]
                )
            except (OSError, ValueError):
                continue
            if newest < started_at:
                candidates.append(directory)
            continue
        keep = set(referenced)
        for entry in read_lineage(root, key)["latest"].values():
            if isinstance(entry, Mapping) and entry.get("id"):
                keep.add(str(entry["id"]))
        names: set[str] = set()
        for entry in directory.iterdir():
            name = entry.name
            if entry.is_dir() and _PAYLOAD_ID_RE.fullmatch(name):
                names.add(name)
            elif entry.is_file() and name.endswith(".json"):
                stem = name[: -len(".json")]
                if _PAYLOAD_ID_RE.fullmatch(stem):
                    names.add(stem)
        for payload_id in sorted(names):
            if payload_id in keep or payload_ref(key, payload_id) in keep:
                continue
            paths = [directory / payload_id, directory / f"{payload_id}.json"]
            try:
                newest = max(
                    path.stat().st_mtime for path in paths if os.path.lexists(path)
                )
            except (OSError, ValueError):
                continue
            if newest >= started_at:
                continue
            candidates.extend(path for path in paths if os.path.lexists(path))
    return candidates


__all__ = [
    "LINEAGE_FILE_NAME",
    "ORIGIN_IMPORT",
    "ORIGIN_PACKAGE",
    "PAYLOAD_STRIP_ROOT_DIRS",
    "FinalizeResult",
    "PackageBuild",
    "PayloadError",
    "RegisterResult",
    "SourceBuild",
    "add_private_path",
    "build_from_package",
    "build_from_source",
    "clone_payload_into",
    "collect_unreferenced",
    "content_id",
    "finalize",
    "latest",
    "lineage_dir",
    "lineage_identity",
    "lineage_info_from_interface",
    "lineage_key",
    "lineage_key_for_project",
    "lineage_lock",
    "list_ids",
    "list_lineages",
    "manifest_files",
    "manifest_path",
    "mark_damaged",
    "add_known_source",
    "lineage_by_known_source",
    "settle_same_version_latest",
    "payload_dir",
    "payload_ref",
    "place_fresh",
    "private_paths",
    "read_lineage",
    "read_manifest",
    "read_project_interface",
    "register",
    "remove_tree",
    "version_newer",
    "write_json_atomic",
    "write_lineage",
]
