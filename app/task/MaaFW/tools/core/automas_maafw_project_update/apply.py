"""更新包的安全解压与落地计划（纯函数）。

项目更新不再原地改项目目录：新版本在 staging 里从当前载荷 + 更新包建成、预检、登记成
新的不可变载荷，视图再整棵切过去（``payloads.py`` / 宿主 ``embedded_project``）。这里只
留下那条流程要用的纯函数：解压与大小闸门、包类型 / 条目 / 删除表的枚举
（:func:`build_package_plan`，三张表都经投影白名单过滤）、差量基线校验、全量包对
``origin=import`` 文件的资源目录孤儿判定。原地事务、备份、回滚与中断恢复已整套退役。
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import (
    ArtifactType,
    is_within,
    safe_relative_path,
)
from .state import DEFAULT_OPERATION_ROOT

ZIP_MAX_ENTRIES = 100_000
ZIP_MAX_EXPANDED_BYTES = 8 * 1024 * 1024 * 1024
# 逐文件覆盖进度最密每这么多个文件报一次（大项目数千文件，不能每个都报）。
APPLY_PROGRESS_MAX_STEP_FILES = 50

logger = logging.getLogger("automas.maafw.project_update.apply")
PROJECT_STATE_DIR_NAME = "maafw_project_state"


def _resolve_project_state_dir(project_path: Path, operation_root: Path) -> Path:
    """纯路径推导：不碰文件系统，供创建路径与只读探测共用。"""

    normalized = str(project_path.resolve(strict=False)).casefold()
    project_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    state_root = (
        operation_root.resolve(strict=False).parent / PROJECT_STATE_DIR_NAME
    ).resolve(strict=False)
    return state_root / project_key


def project_state_dir_for(
    project_path: Path,
    *,
    operation_root: Path | None = None,
) -> Path:
    """这个视图路径的状态目录（切换时被覆盖的本地改动留档在它的 ``local-modified/``），
    纯路径推导：不碰文件系统、不建目录，要建目录的调用方自己 ``mkdir``。
    """

    return _resolve_project_state_dir(
        Path(project_path), operation_root or DEFAULT_OPERATION_ROOT
    )


class UpdateApplyError(RuntimeError):
    """Raised when a local update plan cannot be safely committed."""

    def __init__(self, message: str, *, unsafe_to_continue: bool = False) -> None:
        super().__init__(message)
        self.unsafe_to_continue = unsafe_to_continue


class UpdatePostValidateRejected(UpdateApplyError):
    """``post_validate`` 回调（在 staging 上的运行环境预检）拒绝了这次更新。

    新版本只在 staging 里，丢掉就是；项目视图一个字节没动，仍可运行。``reason``
    是回调给出的原因原文（异常文本），调用方据此区分「预检没过」与其它失败。
    """

    def __init__(self, reason: str) -> None:
        text = str(reason or "").strip() or "MaaFW post-validation rejected the update"
        super().__init__(text)
        self.reason = text


class UpdateProjectLockBusy(UpdateApplyError):
    """在限定时间内没拿到谱系更新锁：同项目的另一次更新 / 预检正持有它。"""


@dataclass(frozen=True)
class PackagePlan:
    package_type: ArtifactType
    package_root: Path
    files: dict[str, Path]
    hashes: dict[str, str]
    deleted: tuple[str, ...]
    base_version: str | None = None
    base_fingerprint: str | None = None
    target_version: str | None = None
    # 内嵌副本里按内容与其它副本共用的文件（``files`` 的子集）：运行时目录与模型类大文件。
    shared: frozenset[str] = frozenset()


def build_package_plan(
    package_root: Path,
    extract_dir: Path,
    project_path: Path,
    *,
    old_manifest: Mapping[str, Any] | None = None,
    expected_package_type: ArtifactType | None = None,
    from_version: str | None = None,
    target_version: str | None = None,
    projection: bool = False,
    send_log: Callable[[str], None] | None = None,
) -> PackagePlan:
    changes_path = _find_changes_file(package_root, extract_dir)
    changes = _load_json(changes_path) if changes_path else {}
    declared_type = (
        str(
            changes.get("packageType")
            or changes.get("type")
            or changes.get("kind")
            or ""
        )
        .strip()
        .lower()
    )
    package_type: ArtifactType = "delta" if changes_path else "full"
    if declared_type in {"full", "delta"}:
        package_type = declared_type  # type: ignore[assignment]
    if expected_package_type and package_type != expected_package_type:
        raise UpdateApplyError(
            f"update package type mismatch: expected {expected_package_type}, got {package_type}"
        )

    base_version = _first_text(
        changes, "baseVersion", "fromVersion", "from", "sourceVersion"
    )
    base_fingerprint = _first_text(
        changes,
        "baseFingerprint",
        "baseHash",
        "projectFingerprint",
        "sourceFingerprint",
    )
    declared_target = _first_text(changes, "targetVersion", "version", "toVersion")
    payload_root = _resolve_payload_root(
        package_root, changes_path, changes, extract_dir
    )
    files: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for source in payload_root.rglob("*"):
        if source.is_dir():
            continue
        if source.is_symlink():
            raise UpdateApplyError(f"update package contains symlink: {source}")
        if source.name == "changes.json":
            continue
        relative = safe_relative_path(source.relative_to(payload_root).as_posix())
        files[relative] = source

    raw_file_metadata = changes.get("files")
    if isinstance(raw_file_metadata, Mapping):
        for raw_path, raw_meta in raw_file_metadata.items():
            relative = safe_relative_path(str(raw_path))
            source = payload_root / relative
            if source.is_file():
                files[relative] = source
            if isinstance(raw_meta, Mapping):
                digest = (
                    str(raw_meta.get("sha256") or raw_meta.get("hash") or "")
                    .strip()
                    .lower()
                )
            else:
                digest = str(raw_meta or "").strip().lower()
            if digest:
                hashes[relative] = digest.removeprefix("sha256:")
    deleted = tuple(_deleted_paths(changes))
    for relative in deleted:
        safe_relative_path(relative)
    if package_type == "full" and not _has_interface_file(package_root):
        raise UpdateApplyError("full update package must contain interface.json")
    shared: frozenset[str] = frozenset()
    if projection:
        # 内嵌副本：只按 interface 白名单落盘。这是唯一的枚举口，三张表一起过滤，
        # 下游的清单、孤儿清理、回滚看到的就都是瘦树。
        files, hashes, deleted, shared = _project_package_entries(
            payload_root, project_path, files, hashes, deleted, send_log
        )
    return PackagePlan(
        package_type=package_type,
        package_root=package_root,
        files=files,
        hashes=hashes,
        deleted=deleted,
        base_version=base_version,
        base_fingerprint=base_fingerprint,
        target_version=declared_target or target_version,
        shared=shared,
    )


def _project_package_entries(
    payload_root: Path,
    project_path: Path,
    files: dict[str, Path],
    hashes: dict[str, str],
    deleted: tuple[str, ...],
    send_log: Callable[[str], None] | None,
) -> tuple[dict[str, Path], dict[str, str], tuple[str, ...], frozenset[str]]:
    from .projection import (
        ProjectionError,
        filter_package_entries,
        package_projection_rules,
    )

    try:
        rules = package_projection_rules(payload_root, project_path)
    except ProjectionError as exc:
        raise UpdateApplyError(f"projection rules unavailable: {exc}") from exc
    kept_files, dropped_files = filter_package_entries(rules, files)
    kept_deleted, _dropped_deleted = filter_package_entries(rules, deleted)
    if send_log is not None:
        dropped_count = len(dropped_files)
        if dropped_count:
            send_log(f"内嵌投影：包内 {dropped_count} 个条目不在白名单内，未落盘")
        for warning in rules.warnings:
            send_log(f"内嵌投影：{warning}")
    return (
        {
            relative: source
            for relative, source in files.items()
            if relative in kept_files
        },
        {
            relative: digest
            for relative, digest in hashes.items()
            if relative in kept_files
        },
        tuple(relative for relative in deleted if relative in kept_deleted),
        frozenset(
            relative
            for relative in kept_files
            if rules.is_shared_file(Path(relative), _file_size(files[relative]))
        ),
    )


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _validate_plan_base(
    project_path: Path,
    plan: PackagePlan,
    old_manifest: Mapping[str, Any],
    current_fingerprint: str,
) -> None:
    if plan.package_type != "delta":
        return
    recorded = str(plan.base_fingerprint or "").strip().lower()
    manifest_fingerprint = (
        str(old_manifest.get("projectFingerprint") or "").strip().lower()
    )
    if recorded:
        if recorded != current_fingerprint:
            raise UpdateApplyError("delta baseFingerprint does not match project")
    elif manifest_fingerprint:
        if manifest_fingerprint != current_fingerprint:
            raise UpdateApplyError("delta base manifest does not match project")
    else:
        raise UpdateApplyError(
            "legacy delta has no trusted base fingerprint; full package required"
        )
    if plan.base_version:
        current_version = _read_interface_version(project_path)
        if current_version and plan.base_version.strip().lstrip(
            "vV"
        ) != current_version.strip().lstrip("vV"):
            raise UpdateApplyError(
                f"delta baseVersion does not match project: {plan.base_version} != {current_version}"
            )
    for relative, expected in plan.hashes.items():
        source = plan.files.get(relative)
        if source is None or _sha256_file(source) != expected:
            raise UpdateApplyError(f"delta file hash mismatch: {relative}")


def _package_resource_directories(plan: PackagePlan) -> set[str]:
    """新版 interface.json 声明的资源包目录，项目相对 posix 路径。

    实测四个发行包写的都是 ``./resource`` / ``./resource_pack/base`` 这样的相对
    路径；``{PROJECT_DIR}`` 前缀在规格里存在但没见项目用过，这里一并去掉。
    """

    source = plan.files.get("interface.json")
    if source is None or not source.is_file():
        return set()
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return set()
    entries = data.get("resource")
    if not isinstance(entries, list):
        return set()

    directories: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        raw = entry.get("path")
        for candidate in raw if isinstance(raw, list) else [raw]:
            if not isinstance(candidate, str):
                continue
            text = candidate.strip().replace("\\", "/").replace("{PROJECT_DIR}", "")
            while text.startswith("./"):
                text = text[2:]
            text = text.strip("/")
            if not text:
                continue
            try:
                directories.add(safe_relative_path(text))
            except UpdateApplyError:
                continue
    return directories


def _import_origin_orphans(project_path: Path, plan: PackagePlan) -> set[str]:
    """全量包对「导入来的文件」应当清掉的旧版残留（调用方再与 ``origin=import`` 取交集）。

    载荷清单逐文件记来源：``origin=package`` 的是更新包铺的，下一版不在包里就删，
    精确；``origin=import`` 的是用户选的那棵解压目录带来的，分不清哪些是旧版本装的、
    哪些是用户自己放的。不处理的话全量包对它们退化成纯覆盖：新版删掉或挪走的文件会
    原地留下。实测
    MaaYYs v3.10.2 → v3.15.5 把 ``resource_pack/base/pipeline/kun28.json`` 挪进了
    ``战斗/`` 子目录，旧的那份留在原地，两份都定义顶层节点 ``困28``，MaaFramework
    直接拒收整个资源包（``key already exists``），项目从此每次运行都失败。

    **扫描范围只有新版 interface.json 声明的资源包目录。** 这条边界是拿真实包在
    测试床上试出来的：一开始按「包自己铺的顶层目录」扫，结果 v3.15.5 的包里带了
    ``preset/``（两个自带预设），而 MXU 也把**用户自建的预设**写在同一个目录，用户
    预设于是被当成残留删掉。``tasks/``、``assets/`` 同理都可能混着用户内容。资源包
    目录不一样：它是 MaaFramework 直接加载的纯内容，也正是节点重名会炸掉整个项目
    的地方——修的就是这个，扫这里就够。

    另外跳过我们自己铺进项目的东西（``.auto_mas`` 前缀）与字节码（由解释器重写，
    见 :func:`_is_bytecode_artifact`）。

    残留风险说清楚：无法区分「旧版本装的」和「用户自己塞进资源目录的」，因此用户手放
    在资源目录里的覆写也会被清掉。这与全量包语义一致（它就是要把项目换成新版本）；
    清理发生在新载荷的 staging 里，旧载荷与视图不受影响。更新过一次之后这些文件都
    成了 ``origin=package``，后续更新走回精确口径。
    """

    orphans: set[str] = set()
    for relative_dir in sorted(_package_resource_directories(plan)):
        prefix = f"{relative_dir}/"
        if not any(name.startswith(prefix) for name in plan.files):
            # 包里没往这个资源目录铺任何文件：声明与实际对不上，不能拿它当
            # 「这个目录本该是空的」的依据。
            continue
        directory = _project_target(project_path, relative_dir)
        if directory.is_symlink() or not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative = safe_relative_path(path.relative_to(project_path).as_posix())
            if relative in plan.files or _is_bytecode_artifact(relative):
                continue
            if any(part.startswith(".auto_mas") for part in relative.split("/")):
                continue
            orphans.add(relative)
    return orphans


def _is_bytecode_artifact(relative: str) -> bool:
    """相对路径是否为 Python 字节码产物。

    这类文件由解释器在**导入时**自行写出/重写：全量包里自带的 .pyc 一旦解压到
    新路径，首次 import 就会因源码 mtime 与嵌入路径变化被重写。它们不构成
    「受管文件被本地改写」，既不登记进清单，也不进本地改动的留档。
    """

    normalized = relative.replace("\\", "/")
    return normalized.endswith(".pyc") or "__pycache__/" in f"{normalized}/"


def _find_package_root(extract_dir: Path) -> Path:
    candidates = [
        extract_dir,
        *[item for item in extract_dir.iterdir() if item.is_dir()],
    ]
    for candidate in candidates:
        if _has_interface_file(candidate) or (candidate / "changes.json").is_file():
            return candidate
    for interface in extract_dir.rglob("interface.json*"):
        if interface.name in {"interface.json", "interface.jsonc"}:
            return interface.parent
    for changes in extract_dir.rglob("changes.json"):
        return changes.parent
    raise UpdateApplyError(
        "update package does not contain interface.json or changes.json"
    )


def _zip_expanded_size(package_path: Path) -> int:
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            members = archive.infolist()
            if len(members) > ZIP_MAX_ENTRIES:
                raise UpdateApplyError(
                    f"update package contains too many entries: {len(members)}"
                )
            expanded = sum(max(0, int(item.file_size)) for item in members)
    except zipfile.BadZipFile as exc:
        raise UpdateApplyError("update package is not a valid zip file") from exc
    if expanded > ZIP_MAX_EXPANDED_BYTES:
        raise UpdateApplyError("update package expanded size exceeds limit")
    return expanded


def _check_disk_space(
    state_dir: Path,
    project_path: Path,
    *,
    state_required: int,
    project_required: int,
) -> None:
    reserve = 1024 * 1024
    try:
        state_free = shutil.disk_usage(state_dir).free
        project_free = shutil.disk_usage(project_path).free
    except OSError as exc:
        raise UpdateApplyError(
            "INSUFFICIENT_DISK: cannot determine free space"
        ) from exc
    if state_free < max(0, state_required) + reserve:
        raise UpdateApplyError(
            f"INSUFFICIENT_DISK: update staging needs {state_required} bytes, "
            f"state volume has {state_free} bytes free"
        )
    if project_free < max(0, project_required) + reserve:
        raise UpdateApplyError(
            f"INSUFFICIENT_DISK: project commit needs {project_required} bytes, "
            f"project volume has {project_free} bytes free"
        )


def _safe_extract_zip(package_path: Path, extract_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            members = archive.infolist()
            if len(members) > ZIP_MAX_ENTRIES:
                raise UpdateApplyError(
                    f"update package contains too many entries: {len(members)}"
                )
            expanded = sum(max(0, int(item.file_size)) for item in members)
            if expanded > ZIP_MAX_EXPANDED_BYTES:
                raise UpdateApplyError("update package expanded size exceeds limit")
            for member in members:
                target = (extract_dir / member.filename).resolve()
                if not is_within(target, extract_dir):
                    raise UpdateApplyError(
                        f"update package contains unsafe path: {member.filename}"
                    )
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise UpdateApplyError(
                        f"update package contains symlink: {member.filename}"
                    )
            archive.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise UpdateApplyError("update package is not a valid zip file") from exc


def _resolve_payload_root(
    package_root: Path,
    changes_path: Path | None,
    changes: Mapping[str, Any],
    extract_dir: Path,
) -> Path:
    if changes_path is not None:
        raw_files = changes.get("payload") or changes.get("root")
        if isinstance(raw_files, str) and raw_files.strip():
            candidate = (changes_path.parent / raw_files).resolve()
            if not is_within(candidate, extract_dir) or not candidate.is_dir():
                raise UpdateApplyError("changes.json payload path is unsafe")
            return candidate
    for name in ("payload", "files"):
        candidate = package_root / name
        if candidate.is_dir():
            return candidate
    return package_root


def _find_changes_file(package_root: Path, extract_dir: Path) -> Path | None:
    direct = package_root / "changes.json"
    if direct.is_file():
        return direct
    direct = extract_dir / "changes.json"
    return direct if direct.is_file() else None


def _deleted_paths(changes: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for key in (
        "delete",
        "deleted",
        "deleted_dir",
        "remove",
        "removed",
        "unlink",
        "unlinks",
    ):
        value = changes.get(key)
        if isinstance(value, list):
            result.extend(str(item) for item in value if isinstance(item, str))
        elif isinstance(value, Mapping):
            result.extend(str(item) for item in value if isinstance(item, str))
    return result


def _load_manifest(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    files = value.get("files")
    if isinstance(files, list):
        value["files"] = {str(item): "" for item in files if isinstance(item, str)}
    elif not isinstance(files, Mapping):
        value["files"] = {}
    return value


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateApplyError(f"cannot parse update metadata: {path.name}") from exc
    if not isinstance(value, dict):
        raise UpdateApplyError(f"update metadata must be an object: {path.name}")
    return value


def _first_text(value: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        raw = str(value.get(key) or "").strip()
        if raw:
            return raw
    return None


def _has_interface_file(path: Path) -> bool:
    return (path / "interface.json").is_file() or (path / "interface.jsonc").is_file()


def _read_interface_version(project_path: Path, *, strict: bool = False) -> str:
    for name in ("interface.json", "interface.jsonc"):
        path = project_path / name
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            try:
                import json5

                value = json5.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                if strict:
                    raise UpdateApplyError(
                        "updated MaaFW interface is not valid JSON/JSONC"
                    ) from exc
                return ""
        if not isinstance(value, Mapping):
            if strict:
                raise UpdateApplyError("updated MaaFW interface must be a JSON object")
            return ""
        return str(value.get("version") or "")
    return ""


def _validate_project_interface(project_path: Path) -> None:
    if not _has_interface_file(project_path):
        raise UpdateApplyError("updated MaaFW project has no interface.json")
    _read_interface_version(project_path, strict=True)


def _project_target(project_path: Path, relative: str) -> Path:
    normalized = safe_relative_path(relative)
    target = (project_path / normalized).resolve(strict=False)
    if not is_within(target, project_path):
        raise UpdateApplyError(f"update path escapes project root: {relative}")
    return target


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _apply_progress_step(total_files: int) -> int:
    """逐文件覆盖进度的上报步长：约每 2% 一次，最密不超过每 50 个文件一次。"""

    return max(1, min(APPLY_PROGRESS_MAX_STEP_FILES, total_files // 50))


def _emit(
    progress: Callable[[str, dict[str, Any]], None] | None,
    stage: str,
    payload: dict[str, Any],
) -> None:
    if progress is None:
        return
    try:
        progress(stage, payload)
    except Exception:
        # 进度只是旁观者，不能拖垮事务；但要留痕，否则回调里的
        # ``no running event loop`` 这类错误就此消失。
        logger.warning("MaaFW 更新进度回调失败: stage=%s", stage, exc_info=True)


__all__ = [
    "PackagePlan",
    "UpdateApplyError",
    "UpdatePostValidateRejected",
    "UpdateProjectLockBusy",
    "build_package_plan",
    "project_state_dir_for",
]
