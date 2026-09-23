#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MFW 内嵌项目：不可变载荷 + 每脚本视图。

MFW 脚本一律在视图上跑，没有开关：用户选一次项目目录，AUTO-MAS 按 interface 白名单
投影成一份**载荷**（``data/mfw/.payloads/<谱系>/<版本>-<hash>``，全局一份、登记后不再改），
再给脚本物化一棵**视图** ``data/mfw/<脚本 uuid 前 12 位>/``：载荷里 ≥ 64 KB 的文件在视图里
是指向载荷 / 共用库的硬链接，小文件拷贝，运行期产物（``debug/``、``config/`` 里 agent 写的、
``.pycache`` …）是视图私有的。视图路径由脚本 ID 推出，不进配置，用户不可手改；
``Info.Path`` 只是来源目录——导入完成后它对运行没有任何作用，用户删掉也无妨。

视图根上的 ``.auto_mas_view.json`` 记它挂在哪个载荷上（谱系、载荷 id、版本、物化时刻），
是物化事实的唯一来源。换版本 = :func:`switch_view`：在 staging 里按新载荷重建链接森林、
把私有文件带过去、标记先写进 staging，再两次目录 rename 原子换入；journal 在
``data/mfw/.switch/`` 里，进程被杀后 :func:`recover_switches` 按盘上状态收尾。

**写穿防线**：往 staging 写任何文件都走 ``payloads.place_fresh``（先删目标、再链接，链接失败才
以独占方式新建复制）——staging 里多数文件是载荷的硬链接，往已存在的目标里写就等于改载荷。

没有标记的老副本由启动期一次性迁移采纳（:func:`adopt_view`，附录 B）；采纳失败的在运行
前自愈里再试一次，仍失败就报错、本次不运行。

副本放在 ``data/mfw/<…>`` 而不是 ``data/<uuid>/``：后者会被配置备份整目录快照。删脚本时
``remove_script`` 连带删视图（载荷与共用库只少一个链接）。

这里全是同步的文件操作，API 与管理器用 ``asyncio.to_thread`` 调。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.project_update import payloads
from app.task.MaaFW.tools.core.project_update.apply import (
    project_state_dir_for,
)
from app.task.MaaFW.tools.core.project_update.blob_store import (
    RuntimeBlobStore,
    sha256_file,
)
from app.task.MaaFW.tools.core.project_update.contracts import (
    RUNTIME_STATE_FILES,
    VERSION_BOUND_STATE_FILES,
    VIEW_MARKER_FILE_NAME,
)
from app.task.MaaFW.tools.core.project_update.projection import (
    ProjectionError,
    build_projection_plan,
    is_shared_path,
    read_json_object,
)
from app.task.MaaFW.tools.core.runtime_pool.host_environment import (
    EMBEDDED_COPIES_DIR_PARTS,
    EMBEDDED_PAYLOADS_DIR_NAME,
    EMBEDDED_SWITCH_DIR_NAME,
    PROJECT_PYCACHE_DIR_NAME,
)
from app.task.MaaFW.tools.embedded.project_path import (
    release_project_path_sync,
    try_reserve_project_path_sync,
)
from app.utils import get_logger

EMBEDDED_PROJECTS_DIR = Path(*EMBEDDED_COPIES_DIR_PARTS)
logger = get_logger("MFW 内嵌")

# 副本目录名 = 脚本 uuid 去掉连字符的前 12 位（48 位，一个用户几百个脚本撞上的概率可以忽略），
# 仍能从脚本 ID 直接推出、不用查表。不用完整 uuid 只为路径长度，见 EMBEDDED_COPIES_DIR_PARTS。
COPY_DIR_NAME_LENGTH = 12

STAGING_DIR_NAME = ".staging"
PAYLOADS_DIR_NAME = EMBEDDED_PAYLOADS_DIR_NAME
SWITCH_DIR_NAME = EMBEDDED_SWITCH_DIR_NAME
VIEW_MARKER_NAME = VIEW_MARKER_FILE_NAME
VIEW_SCHEMA_VERSION = 1
DEFAULT_CHANNEL = "stable"
# 副本里 Python 字节码缓存的落点（``PYTHONPYCACHEPREFIX``，见 host_environment）：agent 与
# 环境准备写出的 pyc 全在这一个目录下，副本其余部分不再被运行期弄脏；随副本一起删。
PYCACHE_DIR_NAME = PROJECT_PYCACHE_DIR_NAME
# 受管文件被本地改过、切换时被新载荷覆盖前的留档目录（与更新器同一个 state 目录）。
LOCAL_MODIFIED_DIR_NAME = "local-modified"


class EmbeddedProjectError(RuntimeError):
    """内嵌副本操作失败。文案面向用户，调用方原样带出。"""


# 测试注入点：切换在各阶段调用它，测试让它抛 BaseException 模拟进程被杀（不走清理分支）。
_SWITCH_FAULT: Callable[[str], None] | None = None


def _fault(stage: str) -> None:
    if _SWITCH_FAULT is not None:
        _SWITCH_FAULT(stage)


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------


def embedded_projects_root(base: Path | None = None) -> Path:
    return (base if base is not None else Path.cwd()) / EMBEDDED_PROJECTS_DIR


def payloads_root(base: Path | None = None) -> Path:
    return embedded_projects_root(base) / PAYLOADS_DIR_NAME


def switch_root(base: Path | None = None) -> Path:
    return embedded_projects_root(base) / SWITCH_DIR_NAME


def _staging_root(base: Path | None) -> Path:
    root = embedded_projects_root(base) / STAGING_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def embedded_copy_dir_name(script_id: str) -> str:
    """副本目录名：脚本 uuid 去掉连字符的前 12 位；不是 uuid 形状就拒绝，别让别的东西拼进路径。"""

    normalized = str(script_id or "").strip()
    if not normalized:
        raise EmbeddedProjectError("内嵌副本需要 scriptId")
    try:
        return uuid.UUID(normalized).hex[:COPY_DIR_NAME_LENGTH]
    except ValueError as exc:
        raise EmbeddedProjectError(f"scriptId 不是合法的 uuid：{script_id}") from exc


def is_embedded_copy_dir_name(name: str) -> bool:
    """根目录下一个条目是不是副本目录的名字形状（启动期清理只认这种形状）。"""

    return len(name) == COPY_DIR_NAME_LENGTH and all(
        ch in "0123456789abcdef" for ch in name
    )


def embedded_project_dir(script_id: str, base: Path | None = None) -> Path:
    """视图目录：``data/mfw/<脚本 uuid 前 12 位>``，由脚本 ID 推出、不进配置。"""

    return embedded_projects_root(base) / embedded_copy_dir_name(script_id)


def resolve_maafw_project_root(
    script_id: str, script_config: Any, base: Path | None = None
) -> Path:
    """有效项目根：永远是视图。``Info.Path`` 只是来源，运行时不读它。

    所有"拿项目目录做事"的地方都从这里取，别再各自读 Info.Path。视图可能还没建
    （老脚本、刚选目录），要先经 ``ensure_embedded_copy``。
    """

    del script_config  # 只为与旧调用方签名兼容：有效根不再取决于配置
    return embedded_project_dir(script_id, base)


def _clear_readonly_and_retry(
    func: Callable[[str], Any], path: str, _exc_info: Any
) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    if path.exists():
        # 扩展路径：挪进 .staging 的旧视图比原位置深，贴着 MAX_PATH 的深路径在那里删不掉。
        shutil.rmtree(payloads.long_path(path), onexc=_clear_readonly_and_retry)


def _remove_quietly(path: Path, what: str) -> None:
    try:
        if os.path.lexists(path):
            if path.is_dir() and not path.is_symlink():
                remove_tree(path)
            else:
                path.unlink()
    except OSError as exc:
        logger.warning(f"[MFW 内嵌] {what}清理失败，留待启动时清理: {path} - {exc}")


def _update_operation_root(base: Path | None) -> Path:
    """更新器的 operation 根；与 ``project_update/state.py`` 的默认值同一口径。"""

    return (
        (base if base is not None else Path.cwd()) / "data" / "maafw_update_operations"
    )


def discard_copy_update_baseline(script_id: str, base: Path | None = None) -> bool:
    """视图被整体换掉（重新导入 / 克隆）之后，丢掉更新器为这个路径记的清单与预检备忘。

    ``local-modified/`` 留着：切换刚把被覆盖的本地改动留档在那里。
    """

    return _discard_view_baseline(embedded_project_dir(script_id, base), base)


def _discard_view_baseline(view: Path, base: Path | None) -> bool:
    state_dir = project_state_dir_for(view, operation_root=_update_operation_root(base))
    if state_dir.is_symlink() or not state_dir.is_dir():
        return False
    removed = False
    for child in list(state_dir.iterdir()):
        if child.name == LOCAL_MODIFIED_DIR_NAME:
            continue
        if child.is_dir() and not child.is_symlink():
            remove_tree(child)
        else:
            child.unlink()
        removed = True
    return removed


def copy_is_healthy(copy_dir: Path) -> bool:
    return (copy_dir / "interface.json").is_file() or (
        copy_dir / "interface.jsonc"
    ).is_file()


def read_interface_version(project_dir: Path) -> str:
    for name in ("interface.json", "interface.jsonc"):
        candidate = project_dir / name
        if candidate.is_file():
            try:
                return str(
                    read_json_object(candidate, "ProjectInterface").get("version") or ""
                )
            except ProjectionError:
                return ""
    return ""


def _now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _script_channel(script_config: Any) -> str:
    try:
        value = str(script_config.get("Update", "Channel") or "").strip()
    except Exception:  # noqa: BLE001 - 配置桩 / 老配置读不出就按默认渠道
        value = ""
    return value or DEFAULT_CHANNEL


# --------------------------------------------------------------------------
# 视图标记与 journal
# --------------------------------------------------------------------------


def read_view_marker(view_dir: Path) -> dict[str, Any] | None:
    """视图标记；没有、读不出、缺谱系 / 载荷字段都当没有（未采纳的老副本）。"""

    path = Path(view_dir) / VIEW_MARKER_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not str(data.get("lineage") or "") or not str(data.get("payload") or ""):
        return None
    return data


def write_view_marker(directory: Path, data: Mapping[str, Any]) -> None:
    """把标记写进一棵**还没换入**的树（staging）。视图里的标记只随目录 rename 换入，
    不原地改写——内容与标记必须同源。"""

    path = Path(directory) / VIEW_MARKER_NAME
    if os.path.lexists(path):
        path.unlink()
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(dict(data), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _journal_path(view_name: str, base: Path | None) -> Path:
    return switch_root(base) / f"{view_name}.json"


def _read_journal(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def switch_in_progress(script_id: str, base: Path | None = None) -> bool:
    """这个脚本的视图有没有一次没收尾的切换（``.switch/<id>.json`` 在）。"""

    return _journal_path(embedded_copy_dir_name(script_id), base).exists()


# 启动期迁移（采纳 + 统一到组版本）在后台跑、不挡主定时器；期间视图被它预约着的运行在
# 运行前检查里按「正在切换版本」跳过一次。进程内状态，只有迁移本身置位。
_MIGRATION_ACTIVE = threading.Event()


def set_migration_active(active: bool) -> None:
    if active:
        _MIGRATION_ACTIVE.set()
    else:
        _MIGRATION_ACTIVE.clear()


def migration_active() -> bool:
    return _MIGRATION_ACTIVE.is_set()


# 启动期迁移统一到组版本时写进标记的 ``switchedBy``（不是哪个脚本的更新切的）。
MIGRATION_SWITCHED_BY: dict[str, str] = {"scriptId": "迁移", "name": "启动期迁移"}


# 视图标记里「运行环境已为哪个载荷确认过」：切换只换文件，环境确认（isolated_venv 重建等）
# 是另一件事。把「还欠一次确认」落在盘上而不是 manager 实例上：任何路径漏掉的确认
# （运行后被停止、检查切完又提前返回、后台确认失败）都在下次运行前按它补上。
ENV_CONFIRMED_FIELD = "envConfirmedFor"


def env_confirm_pending(marker: Mapping[str, Any] | None) -> bool:
    """视图挂的载荷还没确认过运行环境（没有标记的老副本不算：它不归这套管）。"""

    if marker is None:
        return False
    return str(marker.get(ENV_CONFIRMED_FIELD) or "") != str(
        marker.get("payload") or ""
    )


def mark_env_confirmed(view_dir: Path, payload_id: str | None = None) -> bool:
    """运行环境确认成功后记下 ``envConfirmedFor``；调用方持有该视图的项目预约。

    ``payload_id`` 给了就只在标记仍挂着它时记（确认期间视图被换走就不算数）。标记是
    视图私有的非受管文件，不进指纹；临时文件 + ``os.replace`` 换目录项，其余字段不动。
    """

    marker = read_view_marker(view_dir)
    if marker is None:
        return False
    current = str(marker["payload"])
    if payload_id is not None and current != str(payload_id):
        return False
    if str(marker.get(ENV_CONFIRMED_FIELD) or "") == current:
        return True
    marker[ENV_CONFIRMED_FIELD] = current
    payloads.write_json_atomic(Path(view_dir) / VIEW_MARKER_NAME, marker)
    return True


def switch_or_confirm_in_progress(script_id: str, base: Path | None = None) -> bool:
    """视图正在换版本，或刚换完、后台还在确认运行环境（此刻拿不到它的预约时用）。

    后者的判据：标记挂的载荷 ≠ ``envConfirmedFor``，且这次切换是「从一个确认过的版本」
    或「被兄弟的更新」切过来的——没确认过也没被切过的老视图拿不到预约，多半是运行 /
    更新 / 手动准备环境，不说成「正在切换」。
    """

    if switch_in_progress(script_id, base) or migration_active():
        return True
    marker = read_view_marker(embedded_project_dir(script_id, base))
    if not env_confirm_pending(marker):
        return False
    assert marker is not None
    return "switchedBy" in marker or bool(marker.get(ENV_CONFIRMED_FIELD))


def clear_switched_by(view_dir: Path) -> bool:
    """「本视图被谁的更新切过」那行日志打完后清掉标记里的 ``switchedBy``。

    标记是视图私有的小文件，临时文件 + ``os.replace`` 换目录项；其余字段原样保留。
    """

    marker = read_view_marker(view_dir)
    if marker is None or "switchedBy" not in marker:
        return False
    marker.pop("switchedBy", None)
    payloads.write_json_atomic(Path(view_dir) / VIEW_MARKER_NAME, marker)
    return True


def resolve_view_payload(
    script_id: str, base: Path | None = None
) -> tuple[str, str] | None:
    """脚本视图挂着的（谱系, 载荷 id）：正在切换时取 journal 的 ``to``，否则取标记。"""

    view = embedded_project_dir(script_id, base)
    journal = _read_journal(_journal_path(view.name, base))
    if journal and journal.get("lineage") and journal.get("to"):
        return str(journal["lineage"]), str(journal["to"])
    marker = read_view_marker(view)
    if marker is None:
        return None
    return str(marker["lineage"]), str(marker["payload"])


# --------------------------------------------------------------------------
# 视图物化 / 切换
# --------------------------------------------------------------------------


@dataclass
class ViewResult:
    view: Path
    lineage: str
    payload_id: str
    version: str
    from_payload: str = ""
    linked: int = 0
    copied: int = 0
    carried: int = 0
    archived: list[str] = field(default_factory=list)
    # 同版本合并时目标载荷里没有、或同路径内容不同而已留档的文件（不是本地改动）。
    dropped: list[str] = field(default_factory=list)
    archive_dir: Path | None = None
    elapsed: float = 0.0


def _payload_or_error(root: Path, lineage: str, payload_id: str) -> tuple[Path, dict]:
    try:
        manifest = payloads.read_manifest(root, lineage, payload_id)
        directory = payloads.payload_dir(root, lineage, payload_id)
    except payloads.PayloadError as exc:
        raise EmbeddedProjectError(f"项目版本记录无效：{exc}") from exc
    if manifest is None or not directory.is_dir():
        raise EmbeddedProjectError(f"项目版本 {payload_id} 不在本机，无法切换")
    return directory, manifest


def _differs_from(path: Path, payload_file: Path, entry: Mapping[str, Any]) -> bool:
    """视图里的文件内容是否与载荷记的不同。先比 inode（链接着同一份就是没动过，不读文件），
    再比大小，最后才算 sha。"""

    info = path.stat()
    try:
        payload_info: os.stat_result | None = payload_file.stat()
    except OSError:
        payload_info = None
    if payload_info is not None and (info.st_ino, info.st_dev) == (
        payload_info.st_ino,
        payload_info.st_dev,
    ):
        return False
    size = int(entry.get("size") or 0)
    if size and info.st_size != size:
        return True
    if (
        payload_info is not None
        and info.st_size == payload_info.st_size
        and info.st_mtime_ns == payload_info.st_mtime_ns
    ):
        # 视图里的小文件是连修改时间一起从载荷复制的；大小、时间都没变就是没动过
        # （写入必然刷新修改时间），省掉几千个小文件的哈希。
        return False
    return sha256_file(path) != str(entry.get("sha256") or "")


def _local_modified_dir(
    view: Path, from_id: str, to_id: str, base: Path | None
) -> Path:
    state_dir = project_state_dir_for(view, operation_root=_update_operation_root(base))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return state_dir / LOCAL_MODIFIED_DIR_NAME / f"{from_id or 'none'}→{to_id}-{stamp}"


def _build_view_tree(
    staging: Path,
    payload_path: Path,
    new_files: Mapping[str, Mapping[str, Any]],
    *,
    carry_from: Path | None,
    old_files: Mapping[str, Mapping[str, Any]],
    old_payload_path: Path | None,
    archive_dir: Callable[[], Path],
    result: ViewResult,
    private: Iterable[str] = (),
    archive_dropped: bool = False,
    same_payload: bool = False,
) -> None:
    """§3.2 第 2–3 步：载荷的链接森林 + 私有状态承载。写 staging 一律 ``place_fresh``。

    载荷文件满足共用谓词的挂硬链接（与载荷 / blob 同一 inode），其余复制成视图私有的新
    文件——小文件、``config/`` 这些 agent 可能原地写的，视图里必须是自己的一份。

    ``archive_dropped``：旧载荷里有、新载荷里没有（或同路径内容不同）的文件也留档，不静默
    丢 / 覆盖。同版本号的两份
    载荷之间切换（迁移时把同一版本的多份副本合并到一份）用：那不是「新版本删了它」，
    而是两份副本内容不一样，被切掉的那份独有的文件可能正是它在用的。
    """

    staging.mkdir(parents=True, exist_ok=True)
    private_list = tuple(private)
    for directory in sorted(
        {Path(rel).parent for rel in new_files}, key=lambda item: len(item.parts)
    ):
        (staging / directory).mkdir(parents=True, exist_ok=True)
    for rel, entry in new_files.items():
        action = payloads.place_fresh(
            payload_path / rel,
            staging / rel,
            link=is_shared_path(rel, int(entry.get("size") or 0), private_list),
            make_parent=False,
        )
        if action == "linked":
            result.linked += 1
        else:
            result.copied += 1
    if carry_from is None or not carry_from.is_dir():
        return

    new_keys = {rel.casefold(): rel for rel in new_files}
    old_map = {rel.casefold(): rel for rel in old_files}
    archive: Path | None = None

    def _archive(path: Path, rel: str, *, dropped: bool = False) -> None:
        nonlocal archive
        if archive is None:
            archive = archive_dir()
            result.archive_dir = archive
        try:
            payloads.place_fresh(path, archive / rel, link=True)
            (result.dropped if dropped else result.archived).append(rel)
        except OSError as exc:
            logger.warning(f"[MFW 内嵌] 本地改动留档失败，继续切换: {rel}: {exc}")

    def _walk_error(exc: OSError) -> None:
        raise EmbeddedProjectError(f"读取视图失败: {exc.filename}: {exc}") from exc

    def _blocked(rel_path: Path) -> bool:
        """放进 staging 会与新版本的目录 / 文件撞路径：新版本在这里有个目录，或者某一级
        父路径在新版本里是个文件。载荷优先，私有那份只能留档。"""

        target = staging / rel_path
        if target.is_dir():
            return True
        parent = target.parent
        while parent != staging and staging in parent.parents:
            if parent.exists() and not parent.is_dir():
                return True
            parent = parent.parent
        return False

    for current, dir_names, file_names in os.walk(carry_from, onerror=_walk_error):
        current_path = Path(current)
        relative_dir = current_path.relative_to(carry_from)
        # 字节码缓存不承载：可重建（下次运行按需编译），而它的镜像树是全视图最深的路径，
        # 在比视图深二十来个字符的 staging 里建会超 MAX_PATH（Maa_bbb / FOS 实测）。
        dir_names[:] = [
            name
            for name in dir_names
            if name != "__pycache__"
            and not (relative_dir == Path() and name == PYCACHE_DIR_NAME)
        ]
        if not dir_names and not file_names and relative_dir != Path():
            # 空目录（运行期建的 debug/ 之类）也是私有状态；有内容的目录随文件自然建出。
            target_dir = staging / relative_dir
            if not target_dir.exists() and not _blocked(relative_dir):
                target_dir.mkdir(parents=True, exist_ok=True)
        for name in file_names:
            if relative_dir == Path() and name == VIEW_MARKER_NAME:
                # 旧标记描述的是旧载荷，带进新树就是假事实（§3.2 第 3.5 步）。
                continue
            path = current_path / name
            rel = (relative_dir / name).as_posix()
            key = rel.casefold()
            if key in VERSION_BOUND_STATE_FILES and not same_payload:
                # 换载荷：staging 里已是新载荷那份（或没有），视图这份不带，见 contracts。
                continue
            if key in RUNTIME_STATE_FILES:
                # 运行期状态（账号记录之类）：视图里这份就是真相，不论新旧载荷里有没有、内容
                # 是什么都原样带过去——按受管文件处理会被换回导入时的内容或当成删掉的文件丢掉。
                # place_fresh 先摘掉 staging 里的载荷目录项再链，不往载荷里写。
                if _blocked(relative_dir / name):
                    _archive(path, rel)
                else:
                    payloads.place_fresh(path, staging / rel, link=True)
                    result.carried += 1
                continue
            old_rel = old_map.get(key)
            new_rel = new_keys.get(key)
            if old_rel is None:
                if new_rel is None:
                    if _blocked(relative_dir / name):
                        # 私有文件与新版本的目录撞路径（或私有目录里的文件撞上新版本的
                        # 同名文件）：载荷优先，私有那份留档，切换照常完成。
                        _archive(path, rel)
                        continue
                    # 运行期新建的私有文件：链过去（nlink 通常是 1，不涉及共用）。
                    payloads.place_fresh(path, staging / rel, link=True)
                    result.carried += 1
                elif _differs_from(path, payload_path / new_rel, new_files[new_rel]):
                    # 新版本开始自带这个路径：载荷优先，视图那份留档。绝不能往 staging 里
                    # 那个载荷硬链接上写（写穿防线）。
                    _archive(path, rel)
                continue
            if old_payload_path is not None and _differs_from(
                path, old_payload_path / old_rel, old_files[old_rel]
            ):
                _archive(path, rel)
            elif archive_dropped and (
                new_rel is None
                or str(old_files[old_rel].get("sha256") or "").lower()
                != str(new_files[new_rel].get("sha256") or "").lower()
            ):
                # 同版本合并：目标那份里没有它、或同路径内容不同（两份副本本来就不一样），
                # 都不是「新版本改的 / 删的」，旧内容留档而不静默丢 / 覆盖。
                _archive(path, rel, dropped=True)
            # 在新载荷里 → staging 已是新内容；不在 → 新版本删掉了，不带。


def _realize_view(
    view: Path,
    lineage: str,
    payload_id: str,
    *,
    base: Path | None,
    carry: bool,
    switched_by: Mapping[str, Any] | None = None,
    assume_marker: Mapping[str, Any] | None = None,
) -> ViewResult:
    """按载荷（重）建视图并原子换入。``carry=True`` 且视图有标记时就是 :func:`switch_view`；
    否则整棵换掉（没有标记的老副本、全新脚本）。``assume_marker`` 给没有标记的老副本
    用（采纳）：把它当成已经挂在那个载荷上，私有文件照常带过去。"""

    started = time.monotonic()
    root = payloads_root(base)
    new_dir, new_manifest = _payload_or_error(root, lineage, payload_id)
    new_files = payloads.manifest_files(new_manifest)
    version = str(new_manifest.get("version") or "")

    old_marker = (
        dict(assume_marker)
        if assume_marker is not None
        else (read_view_marker(view) if carry else None)
    )
    if old_marker is not None and str(old_marker.get("lineage") or "") != lineage:
        # 换了个项目（重导另一个项目的目录）：旧项目的私有状态（它的 config/、debug/）
        # 不该进新项目的视图，整棵换掉，与今天重新导入一致。
        old_marker = None
    carry_from = view if (carry and old_marker is not None) else None
    old_files: dict[str, dict[str, Any]] = {}
    old_payload_path: Path | None = None
    old_manifest_version = ""
    from_id = ""
    if old_marker is not None:
        from_id = str(old_marker.get("payload") or "")
        try:
            old_manifest = payloads.read_manifest(
                root, str(old_marker["lineage"]), from_id
            )
            candidate = payloads.payload_dir(root, str(old_marker["lineage"]), from_id)
        except payloads.PayloadError:
            old_manifest, candidate = None, None
        if old_manifest is not None and candidate is not None and candidate.is_dir():
            old_files = payloads.manifest_files(old_manifest)
            old_payload_path = candidate
            old_manifest_version = str(old_manifest.get("version") or "")
        else:
            logger.warning(
                f"[MFW 内嵌] 视图 {view.name} 记的载荷 {from_id} 已不在，"
                "按全部受管文件都可能被改过处理"
            )

    result = ViewResult(
        view=view,
        lineage=lineage,
        payload_id=payload_id,
        version=version,
        from_payload=from_id,
    )
    journal = _journal_path(view.name, base)
    if journal.exists():
        raise EmbeddedProjectError("该脚本的项目上一次切换版本还没收尾，请重启后再试")
    staging_root = _staging_root(base)
    suffix = uuid.uuid4().hex[:8]
    staging = staging_root / f"{view.name}-sw-{suffix}"
    old = staging_root / f"{view.name}-old-{suffix}"
    record: dict[str, Any] = {
        "schemaVersion": VIEW_SCHEMA_VERSION,
        "view": view.name,
        "lineage": lineage,
        "from": from_id,
        "fromLineage": str((old_marker or {}).get("lineage") or ""),
        "to": payload_id,
        "phase": "building",
        "startedAt": _now_text(),
        "staging": str(staging),
        "old": str(old),
    }
    payloads.write_json_atomic(journal, record)
    keep_journal = False
    try:
        _build_view_tree(
            staging,
            new_dir,
            new_files,
            carry_from=carry_from,
            old_files=old_files,
            old_payload_path=old_payload_path,
            same_payload=bool(from_id) and from_id == payload_id,
            archive_dir=lambda: _local_modified_dir(view, from_id, payload_id, base),
            result=result,
            private=payloads.private_paths(root, lineage),
            archive_dropped=bool(
                old_payload_path is not None
                and from_id != payload_id
                and _same_version(str(old_manifest_version or ""), str(version or ""))
            ),
        )
        marker: dict[str, Any] = {
            "schemaVersion": VIEW_SCHEMA_VERSION,
            "lineage": lineage,
            "payload": payload_id,
            "version": version,
            "materializedAt": _now_text(),
        }
        if old_marker is not None and old_marker.get(ENV_CONFIRMED_FIELD):
            # 同谱系换版本：带上旧的确认记录。它 ≠ 新载荷，下次运行前据此补一次确认；
            # 同载荷重建则仍然相等，不必再确认。
            marker[ENV_CONFIRMED_FIELD] = str(old_marker[ENV_CONFIRMED_FIELD])
        if switched_by:
            marker["switchedBy"] = {
                **dict(switched_by),
                "at": _now_text(),
                "from": from_id,
                "to": payload_id,
            }
        write_view_marker(staging, marker)
        if not copy_is_healthy(staging):
            raise EmbeddedProjectError("载荷里没有 interface.json，拒绝换入")
        _fault("built")
        record["phase"] = "swapping"
        payloads.write_json_atomic(journal, record)
        _fault("swapping")
        had_view = view.exists()
        if had_view:
            os.rename(view, old)
            _fault("renamed-old")
        try:
            os.rename(staging, view)
        except OSError:
            if had_view:
                try:
                    os.rename(old, view)
                except OSError:
                    # 放不回去：视图此刻不在，原视图还在 old。journal 与 staging 都留着，
                    # 启动期按「视图不在、old 在」把它放回——删了 journal，old 就会被当成
                    # 半成品清掉，私有状态跟着没了。
                    keep_journal = True
                    logger.error(
                        f"[MFW 内嵌] 视图 {view.name} 换入与放回都失败，原视图留在 {old}，"
                        "重启时恢复"
                    )
            raise
        _fault("renamed-new")
    except Exception:
        # 视图没被换掉（或已经放回）：清半成品、删 journal。清理失败不盖掉原始异常。
        if not keep_journal:
            _remove_quietly(staging, "切换半成品")
            _remove_quietly(journal, "切换 journal")
        raise
    journal.unlink()
    _remove_quietly(old, "旧视图")
    # 视图内容整棵换了：更新器为这个路径记的清单（原地更新事务的基线）已经对不上。
    try:
        _discard_view_baseline(view, base)
    except OSError as exc:
        logger.warning(f"[MFW 内嵌] 丢弃旧更新基线失败: {view.name} - {exc}")
    _reload_interface_cache(view)
    result.elapsed = time.monotonic() - started
    if result.archived:
        preview = ", ".join(result.archived[:10])
        more = " ..." if len(result.archived) > 10 else ""
        logger.info(
            f"[MFW 内嵌] 视图 {view.name} 有 {len(result.archived)} 个受管文件在本地被改过，"
            f"已以新版本为准，旧内容留在 {result.archive_dir}: {preview}{more}"
        )
    if result.dropped:
        preview = ", ".join(result.dropped[:10])
        more = " ..." if len(result.dropped) > 10 else ""
        logger.warning(
            f"[MFW 内嵌] 视图 {view.name} 合并到同版本的 {payload_id} 时，有 "
            f"{len(result.dropped)} 个文件目标里没有或内容不同，旧内容已留档在 {result.archive_dir}: "
            f"{preview}{more}"
        )
    return result


def _same_version(left: str, right: str) -> bool:
    a, b = left.strip().lstrip("vV"), right.strip().lstrip("vV")
    return bool(a) and a == b


def _reload_interface_cache(view: Path) -> None:
    try:
        from app.task.MaaFW.tools.core.interface.loader import (
            load_interface_model_cached,
        )

        load_interface_model_cached(view, force_reload=True)
    except Exception as exc:  # noqa: BLE001 - 缓存刷新失败只影响下次预览多读一遍
        logger.debug(f"[MFW 内嵌] 切换后刷新 interface 缓存失败: {view} - {exc}")


def materialize_view(
    script_id: str,
    lineage: str,
    payload_id: str,
    *,
    carry_from: Path | None = None,
    base: Path | None = None,
    switched_by: Mapping[str, Any] | None = None,
) -> ViewResult:
    """按载荷物化脚本视图。

    ``carry_from`` 为 None：全新视图，目标位置原有的东西（没有标记的老副本）整棵换掉。
    ``carry_from`` 是该脚本自己的视图目录：等同 :func:`switch_view`，私有文件带过去。
    """

    view = embedded_project_dir(script_id, base)
    if carry_from is not None and Path(carry_from) != view:
        raise EmbeddedProjectError("只能从脚本自己的视图承载私有文件")
    return _realize_view(
        view,
        lineage,
        payload_id,
        base=base,
        carry=carry_from is not None,
        switched_by=switched_by,
    )


def switch_view(
    script_id: str,
    payload_id: str,
    *,
    lineage: str | None = None,
    base: Path | None = None,
    switched_by: Mapping[str, Any] | None = None,
) -> ViewResult:
    """把脚本视图切到 ``payload_id``（§3.2）。调用方必须持有该视图的项目预约。

    视图必须有标记（它就是 P_old）。方向无关：升级、改渠道降级、同载荷重建都是这一条。
    """

    view = embedded_project_dir(script_id, base)
    marker = read_view_marker(view)
    if marker is None:
        raise EmbeddedProjectError("视图还没有登记项目版本（未采纳），不能切换")
    return _realize_view(
        view,
        lineage or str(marker["lineage"]),
        payload_id,
        base=base,
        carry=True,
        switched_by=switched_by,
    )


def _journal_staging_path(raw: Any, staging_root: Path) -> Path | None:
    """journal 里记的 staging / old 路径；不在 ``.staging`` 之下的一律不认（不删别处的东西）。"""

    text = str(raw or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.parent.resolve() != staging_root.resolve():
        logger.warning(f"[MFW 内嵌] 切换 journal 指向 staging 之外，忽略: {text}")
        return None
    return candidate


def recover_switches(
    base: Path | None = None,
    *,
    started_at: float | None = None,
    reserve: bool = False,
) -> list[str]:
    """启动期按 journal 收尾被打断的切换；返回做过的事（日志用）。

    一律先读视图标记再决定（标记随目录原子换入，与内容同源），**没有「重跑切换」这一档**：

    - ``building``：两次 rename 都没发生 → 删 staging、删 journal；
    - ``swapping`` 且视图不在、old 在：rename#1 做了、#2 没做 → old 放回；
    - ``swapping`` 且视图不在、old 也不在（新建视图：导入到新脚本、克隆、重建丢失视图，
      本来就没有旧视图）：staging 里的标记 = ``to`` → 把 staging 换成视图；否则删 staging、删 journal；
    - ``swapping`` 且视图标记 = ``to``：两次 rename 都做完了 → 删 old（若还在）、删 journal；
    - ``swapping`` 且视图标记 ≠ ``to``（或没有标记）：rename#1 还没发生 → 删 staging、删 journal。

    后台初始化时 API 已在服务：``started_at`` 给了就不碰本进程起来之后才写的 journal，
    ``reserve`` 为真时拿不到视图预约（正在切换 / 运行）的也不碰。
    """

    directory = switch_root(base)
    if not directory.is_dir():
        return []
    staging_root = embedded_projects_root(base) / STAGING_DIR_NAME
    done: list[str] = []
    for journal in sorted(directory.glob("*.json")):
        name = journal.stem
        if not is_embedded_copy_dir_name(name):
            continue
        if started_at is not None:
            try:
                if journal.stat().st_mtime >= started_at:
                    continue
            except OSError:
                continue
        view = embedded_projects_root(base) / name
        key: str | None = None
        if reserve:
            key = try_reserve_project_path_sync(view)
            if key is None:
                continue
        try:
            line = _recover_one(journal, view, staging_root)
        finally:
            release_project_path_sync(key)
        if line:
            done.append(f"{name}: {line}")
    for line in done:
        logger.info(f"[MFW 内嵌] 切换恢复 {line}")
    return done


def _recover_one(journal: Path, view: Path, staging_root: Path) -> str:
    record = _read_journal(journal)
    if record is None:
        _remove_quietly(journal, "损坏的切换 journal")
        return "journal 损坏，已删除"
    staging = _journal_staging_path(record.get("staging"), staging_root)
    old = _journal_staging_path(record.get("old"), staging_root)
    target = str(record.get("to") or "")
    phase = str(record.get("phase") or "")
    if phase != "swapping":
        if staging is not None:
            _remove_quietly(staging, "切换半成品")
        _remove_quietly(journal, "切换 journal")
        return "构建阶段被打断，视图仍在原版本"
    if not view.exists():
        if old is not None and old.is_dir():
            os.rename(old, view)
            if staging is not None:
                _remove_quietly(staging, "切换半成品")
            _remove_quietly(journal, "切换 journal")
            return "换入前被打断，已放回原视图"
        staged = read_view_marker(staging) if staging is not None else None
        if (
            staging is not None
            and staged is not None
            and str(staged.get("payload") or "") == target
            and copy_is_healthy(staging)
        ):
            # 新建视图（本来就没有旧视图）：staging 已完整、标记就是目标，补完换入。
            os.rename(staging, view)
            _remove_quietly(journal, "切换 journal")
            return "新建视图的换入被打断，已补完换入"
        if staging is not None:
            _remove_quietly(staging, "切换半成品")
        _remove_quietly(journal, "切换 journal")
        return "新建视图的切换被打断，半成品已清理（视图下次运行前重建）"
    marker = read_view_marker(view)
    if marker is not None and str(marker.get("payload") or "") == target:
        # 两次 rename 都做完了（标记随目录换入）；同载荷重建时 staging 可能还在。
        for leftover in (old, staging):
            if leftover is not None:
                _remove_quietly(leftover, "切换残留")
        _remove_quietly(journal, "切换 journal")
        return "切换已完成，收尾"
    if staging is not None:
        _remove_quietly(staging, "切换半成品")
    _remove_quietly(journal, "切换 journal")
    return "换入前被打断，视图仍在原版本"


# --------------------------------------------------------------------------
# 导入 / 克隆 / 自愈
# --------------------------------------------------------------------------


def _config_class_name(project_dir: Path) -> str:
    try:
        from app.task.MaaFW.tools.core.interface.loader import (
            load_interface_model,
        )
        from app.task.MaaFW.tools.embedded.flavor import decide_project_config_class

        return decide_project_config_class(load_interface_model(project_dir)).__name__
    except Exception:  # noqa: BLE001 - 只是给新建对话框过滤用的簿记，识别失败留空
        return ""


def import_embedded_project(
    script_id: str,
    source_path: str | Path,
    *,
    base: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    channel: str = DEFAULT_CHANNEL,
) -> dict[str, Any]:
    """来源目录 → 载荷（登记进脚本所在渠道的组）→ 视图切到组的 latest。

    返回值直接写进 ``Embedded.*``：``report`` / ``sourceVersion`` / ``importedAt`` /
    ``copyPath``（``sourceVersion`` 是用户选的那个目录的版本，不是切换后的组版本）。
    导入的版本不比组新时视图上的是组既有的载荷（§3.5「本地导入并组」）。
    失败时 staging 被清掉、视图原样不动——重新导入失败不会把旧副本弄没。
    """

    source = Path(str(source_path or "").strip())
    if not source.is_absolute() or not source.is_dir():
        raise EmbeddedProjectError(
            "来源目录不存在或不是绝对路径，请先在项目路径里选一个 MFW 项目目录"
        )
    source = source.resolve()
    final_dir = embedded_project_dir(script_id, base)
    root = embedded_projects_root(base)
    if _is_relative_to(source, root):
        raise EmbeddedProjectError("来源目录不能是内嵌副本自己")

    try:
        plan = build_projection_plan(source)
        interface = read_json_object(
            plan.rules.interface_base / "interface.json"
            if (plan.rules.interface_base / "interface.json").is_file()
            else plan.rules.interface_base / "interface.jsonc",
            "ProjectInterface",
        )
        lineage = payloads.lineage_key(interface)
    except ProjectionError as exc:
        raise EmbeddedProjectError(f"导入失败：{exc}") from exc
    except payloads.PayloadError as exc:
        raise EmbeddedProjectError(f"导入失败：{exc}") from exc
    for resource_name in plan.rules.unavailable_resources:
        logger.warning(
            f"[MFW 内嵌] {source} 声明的资源 {resource_name} 在发行包里没有目录，"
            "副本里该资源不可用，其余照常导入"
        )

    store_root = payloads_root(base)
    blob_store = RuntimeBlobStore.default(base)
    private = payloads.private_paths(store_root, lineage)
    staging = _staging_root(base) / f"payload-{lineage}-{uuid.uuid4().hex[:8]}"
    try:
        built = payloads.build_from_source(
            source,
            staging,
            blob_store=blob_store,
            private=private,
            progress=progress,
            plan=plan,
        )
        finalized = payloads.finalize(staging, blob_store=blob_store, private=private)
        if not copy_is_healthy(staging):
            raise EmbeddedProjectError("投影结果里没有 interface.json，拒绝换入")
        source_version = read_interface_version(staging)
        info = payloads.lineage_info_from_interface(interface)
        info["configClass"] = _config_class_name(staging)
        registered = payloads.register(
            store_root,
            staging,
            lineage=lineage,
            channel=channel or DEFAULT_CHANNEL,
            source={"kind": "import", "ref": str(source)},
            by=str(script_id),
            version=source_version,
            lineage_info=info,
            known_hashes=finalized.hashes,
            bundled={
                "maafw": plan.bundled_maafw_version or "",
                "python": plan.bundled_python_version or "",
            },
        )
        payloads.add_known_source(store_root, lineage, str(source))
    except payloads.PayloadError as exc:
        _remove_quietly(staging, "导入半成品")
        raise EmbeddedProjectError(f"导入失败：{exc}") from exc
    except Exception:
        _remove_quietly(staging, "导入半成品")
        raise

    view_result = _realize_view(
        final_dir, lineage, registered.target_id, base=base, carry=True
    )
    if registered.target_id != registered.payload_id:
        logger.info(
            f"[MFW 内嵌] 导入的版本 {source_version} 不比组里的新，"
            f"视图用组当前版本 {view_result.version}（{registered.latest_id}）"
        )
    # 视图换树后 _realize_view 已丢掉更新器为这个路径记的旧清单（不丢的话后面每次更新
    # 都会以「文件被本地修改」失败，而且没有别的入口能清它）。

    report = plan.report()
    report["sourcePath"] = str(source)
    report["copyPath"] = str(final_dir)
    # 与其它副本共用的文件（同内容只在磁盘上存一份）。
    report["sharedFiles"] = built.shared_files + finalized.ingested_files
    report["sharedBytes"] = built.shared_bytes + finalized.ingested_bytes
    return {
        "report": report,
        "sourceVersion": source_version,
        "importedAt": _now_text(),
        "copyPath": str(final_dir),
    }


# 克隆没有标记的老副本时不带的运行期产物：MaaFW 原生日志目录、Python 字节码缓存、导入半成品。
CLONE_SKIP_ROOT_NAMES = frozenset({"debug", STAGING_DIR_NAME, VIEW_MARKER_NAME})
CLONE_SKIP_DIR_NAMES = frozenset({"__pycache__", PYCACHE_DIR_NAME})


def _payload_available(lineage: str, payload_id: str, base: Path | None) -> bool:
    try:
        root = payloads_root(base)
        return (
            payloads.payload_dir(root, lineage, payload_id).is_dir()
            and payloads.read_manifest(root, lineage, payload_id) is not None
        )
    except payloads.PayloadError:
        return False


def clone_embedded_copy(
    source_script_id: str, target_script_id: str, base: Path | None = None
) -> bool:
    """同一项目再建一个脚本：从源脚本挂着的载荷物化目标视图；返回是否克隆了。

    源有标记（或正在切换）→ 直接从载荷物化，不读源视图，源运行期的私有状态不带过去。
    源是还没采纳的老副本 → 退回按目录克隆（已共用的再挂链接、共用候选经共用库放、其余复制，
    ``debug/`` 与字节码不带）。目标原有的视图只在新树建好后才被换掉，失败时原样不动。
    """

    resolved = resolve_view_payload(source_script_id, base)
    if resolved is not None and _payload_available(*resolved, base):
        lineage, payload_id = resolved
        _realize_view(
            embedded_project_dir(target_script_id, base),
            lineage,
            payload_id,
            base=base,
            carry=False,
        )
        return True
    return _clone_legacy_copy(source_script_id, target_script_id, base)


def _clone_legacy_copy(
    source_script_id: str, target_script_id: str, base: Path | None
) -> bool:
    source_dir = embedded_project_dir(source_script_id, base)
    if not copy_is_healthy(source_dir):
        return False
    # 按目录克隆要读源副本的每个文件：源正在运行（写 config/、debug/）、更新或准备环境时
    # 读到的是半截状态。拿不到源的预约就不克隆（载荷路径不读源视图，不需要这一步）。
    source_key = try_reserve_project_path_sync(source_dir)
    if source_key is None:
        raise EmbeddedProjectError(
            "源脚本的项目副本正被占用（运行 / 更新 / 准备环境），请稍后再试"
        )
    try:
        return _clone_legacy_copy_locked(source_script_id, target_script_id, base)
    finally:
        release_project_path_sync(source_key)


def _clone_legacy_copy_locked(
    source_script_id: str, target_script_id: str, base: Path | None
) -> bool:
    source_dir = embedded_project_dir(source_script_id, base)
    target_dir = embedded_project_dir(target_script_id, base)
    if not copy_is_healthy(source_dir):
        return False
    staging_root = _staging_root(base)
    staging_dir = staging_root / f"{target_dir.name}-{uuid.uuid4().hex[:8]}"
    old_dir = staging_root / f"{target_dir.name}-old-{uuid.uuid4().hex[:8]}"
    blob_store = RuntimeBlobStore.default(base)

    def _walk_error(exc: OSError) -> None:
        # 读不了的子目录不能静默跳过：那会产出一份缺子树却「健康」的副本。
        raise EmbeddedProjectError(f"复制副本失败: {exc.filename}: {exc}") from exc

    try:
        for current_root, dir_names, file_names in os.walk(
            source_dir, onerror=_walk_error
        ):
            relative = Path(current_root).relative_to(source_dir)
            dir_names[:] = sorted(
                name
                for name in dir_names
                if name not in CLONE_SKIP_DIR_NAMES
                and not (relative == Path() and name in CLONE_SKIP_ROOT_NAMES)
            )
            (staging_dir / relative).mkdir(parents=True, exist_ok=True)
            for name in file_names:
                if relative == Path() and name in CLONE_SKIP_ROOT_NAMES:
                    continue
                src = Path(current_root) / name
                dst = staging_dir / relative / name
                try:
                    info = src.stat()
                    if info.st_nlink > 1:
                        payloads.place_fresh(src, dst, link=True)
                        continue
                    if is_shared_path(relative / name, info.st_size):
                        blob_store.place(src, dst)
                        continue
                    payloads.place_fresh(src, dst, link=False)
                except OSError as exc:
                    raise EmbeddedProjectError(
                        f"复制副本失败: {src.name}: {exc}"
                    ) from exc
        if not copy_is_healthy(staging_dir):
            raise EmbeddedProjectError("克隆结果里没有 interface.json，拒绝换入")
        if target_dir.exists():
            target_dir.rename(old_dir)
        staging_dir.rename(target_dir)
    except Exception:
        if old_dir.exists() and not target_dir.exists():
            old_dir.rename(target_dir)
        _remove_quietly(staging_dir, "克隆半成品")
        raise
    _remove_quietly(old_dir, "旧副本")
    # 目标的树整棵换了，更新器上一次记下的清单已经对不上（与重新导入同理）。
    discard_copy_update_baseline(target_script_id, base)
    return True


@dataclass
class PayloadGarbageReport:
    payloads: int = 0
    lineages: list[str] = field(default_factory=list)
    # 删掉时就腾出来的字节（只有这一个链接的文件）；与共用库共享的那部分要等紧接着的
    # 共用库回收（那一行另报）。
    freed_bytes: int = 0


def _unique_bytes(path: Path) -> int:
    """目录里只有一个硬链接的文件的总字节：删掉这棵树立即腾出来的空间。"""

    total = 0
    if path.is_file():
        info = path.stat()
        return info.st_size if info.st_nlink <= 1 else 0
    for current, _dirs, files in os.walk(payloads.long_path(path)):
        for name in files:
            try:
                info = os.stat(os.path.join(current, name))
            except OSError:
                continue
            if info.st_nlink <= 1:
                total += info.st_size
    return total


def _payload_references(base: Path | None) -> tuple[set[str], set[str]]:
    """（引用集, 还活着的谱系）：所有视图标记的 ``payload`` ∪ 未完成 journal 的 ``to``；
    有视图标记、有 journal 指向、或有没采纳的老副本的谱系算活着。"""

    referenced: set[str] = set()
    live: set[str] = set()
    views_root = embedded_projects_root(base)
    for child in views_root.iterdir() if views_root.is_dir() else ():
        if not (child.is_dir() and is_embedded_copy_dir_name(child.name)):
            continue
        marker = read_view_marker(child)
        if marker is None:
            # 还没采纳的老副本（迁移失败、下次再试）：它的谱系也还活着。
            if copy_is_healthy(child):
                try:
                    live.add(payloads.lineage_key_for_project(child))
                except (payloads.PayloadError, ProjectionError, OSError):
                    pass
            continue
        lineage = str(marker["lineage"])
        live.add(lineage)
        referenced.add(payloads.payload_ref(lineage, str(marker["payload"])))
    journals = switch_root(base)
    if journals.is_dir():
        for journal in journals.glob("*.json"):
            record = _read_journal(journal) or {}
            lineage = str(record.get("lineage") or "")
            if lineage:
                live.add(lineage)
                if record.get("to"):
                    referenced.add(payloads.payload_ref(lineage, str(record["to"])))
    return referenced, live


def _candidate_lineage(root: Path, path: Path) -> str:
    return path.name if path.parent == root else path.parent.name


def collect_payload_garbage(
    *,
    started_at: float,
    live_sources: Iterable[str] = (),
    base: Path | None = None,
) -> PayloadGarbageReport:
    """§3.1 第 10 步：删掉没人引用的载荷；谱系里一个视图都不剩时整个谱系一起删。

    引用集 = 所有视图标记的 ``payload`` ∪ 未完成 journal 的 ``to``。还活着的谱系 = 有视图
    标记或 journal 指向的，外加 ``live_sources``（脚本还在、视图却没了的那些脚本的导入来源）
    按载荷清单反查到的谱系——视图丢了的脚本下次运行前要靠它重建，不能先把谱系收掉。
    活着的谱系里 ``latest[*]`` 照旧算引用；不活的谱系（最后一个脚本已删）整个目录收走。
    本进程起来之后才建 / 才登记过的一律不收。载荷删掉后它独有的 blob 只剩库里一个链接，
    由紧接着的共用库回收收走。

    回收跑在后台、API 已在服务：先粗判出有候选的谱系，**删之前在该谱系的锁内按盘上最新
    状态再判一次**（登记、推进 latest 都在同一把锁里做）。否则判定与删除之间登记进来的
    新载荷、刚被推成 latest 的旧载荷会被一起删掉，挂着它的视图从此更新不了。谱系锁正被
    占用（正在登记）的这轮不收。
    """

    root = payloads_root(base)
    report = PayloadGarbageReport()
    if not root.is_dir():
        return report
    referenced, live = _payload_references(base)
    source_live: set[str] = set()
    for source in live_sources:
        if not str(source or "").strip():
            continue
        try:
            found = _lineage_by_import_source(str(source), base)
        except (OSError, payloads.PayloadError):
            found = None
        if found is not None:
            source_live.add(found[0])
    candidates = payloads.collect_unreferenced(
        root, referenced, started_at, live_lineages=live | source_live
    )
    for key in sorted({_candidate_lineage(root, path) for path in candidates}):
        directory = root / key
        whole = False
        try:
            with payloads.lineage_lock(root, key, timeout=0):
                referenced, live = _payload_references(base)
                fresh = [
                    path
                    for path in payloads.collect_unreferenced(
                        root, referenced, started_at, live_lineages=live | source_live
                    )
                    if _candidate_lineage(root, path) == key
                ]
                whole = any(path.parent == root for path in fresh)
                if whole:
                    # 整个谱系：锁文件在锁内删不掉，先清掉其余内容，放锁之后再收目录。
                    fresh = [
                        entry
                        for entry in directory.iterdir()
                        if entry.name != payloads.LINEAGE_LOCK_NAME
                    ]
                for path in fresh:
                    try:
                        freed = _unique_bytes(path)
                    except OSError:
                        freed = 0
                    try:
                        if path.is_dir() and not path.is_symlink():
                            remove_tree(path)
                            if not whole:
                                report.payloads += 1
                        elif os.path.lexists(path):
                            path.unlink()
                        else:
                            continue
                        report.freed_bytes += freed
                    except OSError as exc:
                        logger.warning(f"[MFW 内嵌] 载荷回收失败: {path} - {exc}")
        except TimeoutError:
            logger.debug(f"[MFW 内嵌] 谱系 {key} 正在登记，本轮不回收")
            continue
        except OSError as exc:
            logger.warning(f"[MFW 内嵌] 载荷回收失败: {directory} - {exc}")
            continue
        if whole:
            report.lineages.append(key)
            # 放锁之后收锁文件与空目录；其间若有新的登记进来，目录非空 / 锁文件被占用，
            # 删不掉就留着——它已经是新谱系了。
            with suppress(OSError):
                (directory / payloads.LINEAGE_LOCK_NAME).unlink()
            with suppress(OSError):
                directory.rmdir()
    # 老版本挪开了却没删干净的谱系
    for leftover in root.glob(".trash-*"):
        try:
            if leftover.stat().st_mtime < started_at:
                remove_tree(leftover)
        except OSError:
            continue
    return report


def _view_markers(base: Path | None) -> dict[str, dict[str, Any]]:
    """所有视图的标记：{视图目录名: 标记}。"""

    root = embedded_projects_root(base)
    markers: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return markers
    for child in root.iterdir():
        if child.is_dir() and is_embedded_copy_dir_name(child.name):
            marker = read_view_marker(child)
            if marker is not None:
                markers[child.name] = marker
    return markers


def embedded_status(
    script_id: str, script_config: Any, *, base: Path | None = None
) -> dict[str, Any]:
    """给界面看的状态：视图健不健康、来源还在不在、报告。

    多带的 ``lineage`` / ``payloadId`` / ``version`` / ``siblingCount``（与本视图挂同一个载荷的
    其它视图数）只给日志行用；``api_service.embedded.embedded_status_data`` 按显式字段构造响应，这几个键到不了 API。
    """

    copy_dir = embedded_project_dir(script_id, base)
    source = str(script_config.get("Info", "Path") or "").strip()
    raw_report = script_config.get("Embedded", "Report")
    report: dict[str, Any] = {}
    if isinstance(raw_report, dict):
        report = raw_report
    elif isinstance(raw_report, str) and raw_report.strip():
        try:
            parsed = json.loads(raw_report)
            report = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            report = {}
    marker = read_view_marker(copy_dir)
    lineage = str((marker or {}).get("lineage") or "")
    payload_id = str((marker or {}).get("payload") or "")
    sibling_count = 0
    if marker is not None:
        sibling_count = sum(
            1
            for name, other in _view_markers(base).items()
            if name != copy_dir.name
            and str(other.get("lineage") or "") == lineage
            and str(other.get("payload") or "") == payload_id
        )
    return {
        "copyPath": str(copy_dir),
        "copyHealthy": copy_is_healthy(copy_dir),
        "sourcePath": source,
        "sourceExists": bool(source) and Path(source).is_dir(),
        "sourceVersion": str(script_config.get("Embedded", "SourceVersion") or ""),
        "importedAt": str(script_config.get("Embedded", "ImportedAt") or ""),
        "report": report,
        "lineage": lineage,
        "payloadId": payload_id,
        "version": str((marker or {}).get("version") or "")
        or read_interface_version(copy_dir),
        "siblingCount": sibling_count,
    }


def imported_source_path(script_config: Any) -> str:
    """导入报告里记的来源目录；没导入过（老脚本）时为空。"""

    raw = script_config.get("Embedded", "Report")
    report: Any = raw
    if isinstance(raw, str):
        try:
            report = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return ""
    if not isinstance(report, dict):
        return ""
    return str(report.get("sourcePath") or "").strip()


def _same_directory(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
            str(Path(right).resolve())
        )
    except OSError:
        return False


def inherit_embedded_record(
    source_config: Any, target_script_id: str, base: Path | None = None
) -> dict[str, Any]:
    """从源脚本克隆之后，目标该写进 ``Embedded.*`` 的记录：报告沿用源的（``copyPath``
    改成自己的），来源版本沿用源记的（没有就读视图 interface），导入时间取现在。
    ``Info.Path`` 与 ``Report.sourcePath`` 必须成对继承（``ensure_embedded_copy`` 靠它们
    判断要不要重导）。"""

    target_dir = embedded_project_dir(target_script_id, base)
    raw = source_config.get("Embedded", "Report")
    report: Any = {}
    if isinstance(raw, str):
        try:
            report = json.loads(raw) if raw.strip() else {}
        except ValueError:
            report = {}
    elif isinstance(raw, dict):
        report = dict(raw)
    if not isinstance(report, dict):
        report = {}
    report["copyPath"] = str(target_dir)
    return {
        "report": report,
        "sourceVersion": str(source_config.get("Embedded", "SourceVersion") or "")
        or read_interface_version(target_dir),
        "importedAt": _now_text(),
        "copyPath": str(target_dir),
    }


def _group_target(lineage: str, channel: str, fallback: str, base: Path | None) -> str:
    """组语义下视图该挂的载荷：``latest[channel]``，该渠道没有就用 ``fallback``。"""

    try:
        entry = payloads.latest(payloads_root(base), lineage, channel)
    except payloads.PayloadError:
        entry = None
    if entry and _payload_available(lineage, str(entry["id"]), base):
        return str(entry["id"])
    return fallback


def _rebuild_from_group(
    script_id: str,
    script_config: Any,
    source: str,
    siblings: Iterable[tuple[str, Any]],
    *,
    base: Path | None,
    send_log: Callable[[str], None] | None,
) -> dict[str, Any] | None:
    """来源目录已删、视图又没了：从同项目的载荷重建。找不到返回 None。

    视图没了、标记也跟着没了，谱系只能从同来源的其它脚本上认出来：有标记的兄弟 →
    按它的谱系取本脚本渠道的 ``latest`` 物化（不读兄弟视图、不要兄弟空闲）；只有没采纳的
    老副本兄弟 → 照旧按目录克隆（持兄弟预约）。
    """

    channel = _script_channel(script_config)
    for other_id, other_config in siblings:
        other_id = str(other_id)
        if other_id == script_id:
            continue
        other_source = imported_source_path(other_config) or str(
            other_config.get("Info", "Path") or ""
        )
        if not other_source or not _same_directory(source, other_source):
            continue
        resolved = resolve_view_payload(other_id, base)
        if resolved is not None and _payload_available(*resolved, base):
            lineage, fallback = resolved
            target = _group_target(lineage, channel, fallback, base)
            _realize_view(
                embedded_project_dir(script_id, base),
                lineage,
                target,
                base=base,
                carry=False,
            )
        else:
            other_dir = embedded_project_dir(other_id, base)
            if not copy_is_healthy(other_dir):
                continue
            # 老副本正在更新 / 准备环境时不能克隆半截树；换下一个同来源的脚本。
            key = try_reserve_project_path_sync(other_dir)
            if key is None:
                continue
            try:
                if not _clone_legacy_copy_locked(other_id, script_id, base):
                    continue
            finally:
                release_project_path_sync(key)
        other_name = str(other_config.get("Info", "Name") or other_id[:8])
        message = f"[MFW 内嵌] 来源目录已不存在，已从脚本「{other_name}」的项目重建"
        logger.info(message)
        if send_log is not None:
            send_log(message)
        return inherit_embedded_record(other_config, script_id, base)
    # 没有同来源的兄弟：按载荷清单记的导入来源反查谱系（兄弟都删了、只剩载荷的情形）。
    found = _lineage_by_import_source(source, base)
    if found is not None:
        lineage, fallback = found
        target = _group_target(lineage, channel, fallback, base)
        _realize_view(
            embedded_project_dir(script_id, base),
            lineage,
            target,
            base=base,
            carry=False,
        )
        message = "[MFW 内嵌] 来源目录已不存在，已按本机登记的项目版本重建"
        logger.info(message)
        if send_log is not None:
            send_log(message)
        # 报告与来源版本沿用自己原来的记录（导入时间刷新）。
        return inherit_embedded_record(script_config, script_id, base)
    return None


def _lineage_by_import_source(source: str, base: Path | None) -> tuple[str, str] | None:
    """``source`` 这个目录属于哪个谱系，回（谱系, 兜底载荷 id）。

    先查谱系记下的 ``knownSources``（导入与采纳时写，更新得来的谱系也有）；兜底载荷取该谱系
    某个渠道的 latest（调用方再按自己的渠道取组版本）。老数据没有 ``knownSources`` 时退回
    按载荷清单 ``source.ref``（只有 ``kind=import`` 的清单记了导入目录）取最新登记的。
    """

    root = payloads_root(base)
    known = payloads.lineage_by_known_source(root, source)
    if known is not None:
        latest_map = payloads.read_lineage(root, known)["latest"]
        for channel in [DEFAULT_CHANNEL, *sorted(latest_map)]:
            entry = latest_map.get(channel)
            if (
                isinstance(entry, Mapping)
                and entry.get("id")
                and _payload_available(known, str(entry["id"]), base)
            ):
                return known, str(entry["id"])
        ids = [
            pid
            for pid in payloads.list_ids(root, known)
            if _payload_available(known, pid, base)
        ]
        if ids:
            return known, ids[-1]
        # 谱系还在、载荷都没了：退回下面按清单找（找不到就是 None）
    best: tuple[str, str, str] | None = None
    for lineage in payloads.list_lineages(root):
        for payload_id in payloads.list_ids(root, lineage):
            manifest = payloads.read_manifest(root, lineage, payload_id) or {}
            origin = manifest.get("source") or {}
            if str(origin.get("kind") or "") != "import":
                continue
            if not _same_directory(str(origin.get("ref") or ""), source):
                continue
            built = str(manifest.get("builtAt") or "")
            if best is None or built > best[2]:
                best = (lineage, payload_id, built)
    return (best[0], best[1]) if best is not None else None


def _adopt_or_raise(
    script_id: str,
    script_config: Any,
    *,
    base: Path | None,
    send_log: Callable[[str], None] | None,
) -> None:
    if send_log is not None:
        send_log("[MFW 内嵌] 副本还没有登记项目版本，正在登记")
    try:
        adopted = adopt_view(
            script_id,
            channel=_script_channel(script_config),
            source=imported_source_path(script_config)
            or str(script_config.get("Info", "Path") or ""),
            base=base,
        )
        # 同版本已有别的副本登记过：谁当 latest 按确定规则定，不看谁先来。只动本谱系。
        settle_adopted_latest(base, lineages=[adopted.lineage])
    except EmbeddedProjectError:
        raise
    except Exception as exc:  # noqa: BLE001 - 原因原样给用户
        raise EmbeddedProjectError(f"副本登记项目版本失败：{exc}") from exc


def ensure_embedded_copy(
    script_id: str,
    script_config: Any,
    *,
    base: Path | None = None,
    send_log: Callable[[str], None] | None = None,
    siblings: Iterable[tuple[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """视图不在（老脚本、被删）或来源换了目录时导入一次；返回新报告，否则 None。

    调用方拿到非 None 要把报告写回配置。调用方持有该视图的项目预约。健康但还没有标记的
    视图（启动期采纳失败的老副本）就地再试一次采纳，仍失败就报错、本次不运行——不存在
    「无标记的视图照常跑」。来源目录不在：视图还健康就什么都不做——导入完成后来源本来
    就可以删；视图也没了就从同项目的载荷 / 同来源的老副本重建，实在没有才抛错让用户
    重新选目录。
    """

    copy_dir = embedded_project_dir(script_id, base)
    healthy = copy_is_healthy(copy_dir)
    source = str(script_config.get("Info", "Path") or "").strip()
    keep = healthy and (
        not source
        or _same_directory(source, imported_source_path(script_config))
        or not Path(source).is_dir()
    )
    if keep:
        # 视图还是它自己的来源（或来源已删 / 换成了不存在的路径）：照常用它。
        if read_view_marker(copy_dir) is None:
            _adopt_or_raise(script_id, script_config, base=base, send_log=send_log)
        return None
    if not source:
        raise EmbeddedProjectError("还没有选择 MFW 项目目录")
    if not Path(source).is_dir():
        marker = read_view_marker(copy_dir)
        if marker is not None:
            # 视图目录还在、interface 没了：按自己的谱系重建到组版本。
            lineage = str(marker["lineage"])
            target = _group_target(
                lineage, _script_channel(script_config), str(marker["payload"]), base
            )
            if _payload_available(lineage, target, base):
                if send_log is not None:
                    send_log("[MFW 内嵌] 视图不完整，正在按已登记的项目版本重建")
                _realize_view(copy_dir, lineage, target, base=base, carry=True)
                return None
        rebuilt = _rebuild_from_group(
            script_id,
            script_config,
            source,
            siblings or (),
            base=base,
            send_log=send_log,
        )
        if rebuilt is not None:
            return rebuilt
        raise EmbeddedProjectError(
            "副本不在了，来源目录也已不存在；请重新选择一个解压好的 MFW 项目目录"
        )
    if send_log is not None:
        send_log(
            "[MFW 内嵌] 正在从来源目录导入副本"
            if not healthy
            else "[MFW 内嵌] 来源目录已更换，正在重新导入副本"
        )
    return import_embedded_project(
        script_id, source, base=base, channel=_script_channel(script_config)
    )


# --------------------------------------------------------------------------
# 采纳：把没有标记的老副本登记成载荷（附录 B；启动期一次性迁移与运行前自愈共用）
# --------------------------------------------------------------------------

# 整目录私有（运行期产物、更新器保留目录、半成品）：不进载荷，原样留在视图里。
ADOPT_PRIVATE_ROOTS = frozenset(
    {
        "debug",
        "logs",
        "temp",
        ".pycache",
        ".mas-update",
        ".mas-update-cache",
        ".staging",
    }
)
# 已知的运行期状态文件：采纳时一律按私有（不论清单 / 来源怎么说）；切换时视图里那份原样带过去。
ADOPT_RUNTIME_FILES = RUNTIME_STATE_FILES
# 更新器 journal 里「落地已完成」的状态：这些记录里的清单路径是副本最后一次更新落下的。
_APPLY_COMMITTED = "committed"


def _recorded_update_manifest(view: Path, base: Path | None) -> dict[str, str] | None:
    """老的原地更新事务给这个副本记的包内清单 ``{rel: sha256}``（有的话）。

    清单路径不猜：从更新 journal（``maafw_update_operations/*/state.json``）里本副本
    最近一次 ``committed`` 记录的 ``manifestPath`` 读。
    """

    root = _update_operation_root(base)
    if not root.is_dir():
        return None
    target = os.path.normcase(str(view.resolve()))
    best: tuple[float, Path] | None = None
    for state_file in root.glob("*/state.json"):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(state, dict) or state.get("status") != _APPLY_COMMITTED:
            continue
        project = str(state.get("projectPath") or "")
        manifest_path = str(state.get("manifestPath") or "")
        if not project or not manifest_path:
            continue
        try:
            if os.path.normcase(str(Path(project).resolve())) != target:
                continue
        except OSError:
            continue
        stamp = float(state.get("updatedAt") or state.get("createdAt") or 0)
        if best is None or stamp > best[0]:
            best = (stamp, Path(manifest_path))
    if best is None or not best[1].is_file():
        return None
    try:
        data = json.loads(best[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return None
    return {str(rel): str(sha or "").lower() for rel, sha in files.items()}


def _adoption_whitelist(view: Path) -> Callable[[str], bool] | None:
    """按视图自己的 interface 重算投影白名单（附录 B 第 4 条）：采纳时载荷的去留只看它。"""

    try:
        from app.task.MaaFW.tools.core.project_update.projection import (
            build_projection_rules,
        )

        rules = build_projection_rules(view, strict=False)
    except (ProjectionError, OSError):
        return None
    return lambda rel: rules.keeps(Path(rel))


def settle_adopted_latest(
    base: Path | None = None, *, lineages: Iterable[str] | None = None
) -> list[tuple[str, str, str]]:
    """全部采纳完之后，按确定的规则重定每个谱系每个渠道同版本的 latest（不看采纳顺序）。

    ``lineages`` 给了就只重定这些谱系（运行前就地采纳一份时只动它自己的谱系）。
    返回 ``[(谱系, 渠道, 新 latest id)]``，只列变了的。之后的组同步据此把视图统一过去。
    """

    root = payloads_root(base)
    changed: list[tuple[str, str, str]] = []
    targets = (
        payloads.list_lineages(root)
        if lineages is None
        else [key for key in lineages if key in set(payloads.list_lineages(root))]
    )
    for lineage in targets:
        for channel in list(payloads.read_lineage(root, lineage)["latest"]):
            try:
                chosen = payloads.settle_same_version_latest(root, lineage, channel)
            except (OSError, payloads.PayloadError) as exc:
                logger.warning(
                    f"[MFW 内嵌] 重定 {lineage}/{channel} 的 latest 失败: {exc}"
                )
                continue
            if chosen is not None:
                changed.append((lineage, channel, chosen))
                logger.info(
                    f"[MFW 内嵌] 谱系 {lineage} 渠道 {channel} 同版本有多份，latest 定为 {chosen}"
                )
    return changed


def adopt_view(
    script_id: str,
    *,
    channel: str,
    source: str = "",
    base: Path | None = None,
) -> ViewResult:
    """把没有标记的老副本就地登记成载荷，视图挂上去（附录 B 第 1–7 条）。

    调用方持有该视图的项目预约。**载荷内容以视图自身为准**：对视图按它自己的 interface
    算投影白名单，白名单内、不在排除表 / 已知运行期状态名单里的文件全部进载荷，内容取
    视图里的现状（热更新改过的受管文件也算——视图才是这个版本真正在跑的内容，来源目录
    可能是旧版本）；白名单外的、运行期状态、日志一律私有，原样留在视图里。更新器清单与
    来源目录只用来标 ``origin``（清单里、内容没变的是 ``package``，其余 ``import``），
    不再决定去留——否则「来源旧、视图新、无清单」会登记出残缺载荷。

    载荷在 staging 里建好（大文件并入共用库）、登记，再按 :func:`switch_view` 同一套把视图
    重建一遍（私有文件 inode 不变），写上标记。同版本多份载荷谁当 latest 不在这里定
    （登记是「同版本保留先来的」）：调用方全部采纳完再 :func:`settle_adopted_latest`。
    任一步失败：不写标记、staging 丢掉，调用方下次再试。不写任何配置。
    """

    view = embedded_project_dir(script_id, base)
    if not copy_is_healthy(view):
        raise EmbeddedProjectError("副本不完整（没有 interface.json），无法登记版本")
    if read_view_marker(view) is not None:
        raise EmbeddedProjectError("副本已经登记过版本")
    interface = payloads.read_project_interface(view)
    lineage = payloads.lineage_key(interface)
    version = str(interface.get("version") or "")
    recorded = _recorded_update_manifest(view, base)
    if recorded is not None:
        recorded = {rel.casefold(): sha for rel, sha in recorded.items()}
    whitelist = _adoption_whitelist(view)
    if whitelist is None:
        logger.warning(
            f"[MFW 内嵌] 视图 {view.name} 算不出投影白名单，除运行期状态与日志外全部按载荷登记"
        )

    payload_files: dict[str, str] = {}  # rel -> sha256
    origins: dict[str, str] = {}
    for current, dir_names, file_names in os.walk(view):
        current_path = Path(current)
        relative_dir = current_path.relative_to(view)
        if relative_dir == Path():
            dir_names[:] = [
                name for name in dir_names if name.casefold() not in ADOPT_PRIVATE_ROOTS
            ]
        dir_names[:] = [name for name in dir_names if name != "__pycache__"]
        for name in file_names:
            if relative_dir == Path() and name == VIEW_MARKER_NAME:
                continue
            path = current_path / name
            if path.is_symlink():
                continue
            rel = (relative_dir / name).as_posix()
            key = rel.casefold()
            if key in ADOPT_RUNTIME_FILES or key.endswith(".log"):
                # 已知的运行期状态（M9A 的账号记录、runner 每次重写的 maa_option.json……）
                # 一律私有：进了载荷就会在换版本时被当成「新版本删掉的文件」丢掉，账号级
                # 记录跟着没了。
                continue
            if whitelist is not None and not whitelist(rel):
                continue
            digest = sha256_file(path)
            payload_files[rel] = digest
            # 清单只用来标来源：内容与更新器记的一致就是更新包铺的。
            if recorded is not None and recorded.get(key) == digest:
                origins[rel] = payloads.ORIGIN_PACKAGE
            else:
                origins[rel] = payloads.ORIGIN_IMPORT
    if not any(
        rel.casefold() in {"interface.json", "interface.jsonc"} for rel in payload_files
    ):
        # interface 被改过（备份恢复等）：仍以视图里的为准进载荷，否则载荷不健康。
        for name in ("interface.json", "interface.jsonc"):
            if (view / name).is_file():
                payload_files[name] = sha256_file(view / name)
                origins[name] = payloads.ORIGIN_IMPORT
                break

    root = payloads_root(base)
    blob_store = RuntimeBlobStore.default(base)
    private = tuple(payloads.private_paths(root, lineage))
    staging = _staging_root(base) / f"payload-{lineage}-{uuid.uuid4().hex[:8]}"
    try:
        for rel in sorted(payload_files):
            source_file = view / rel
            size = source_file.stat().st_size
            shared = is_shared_path(rel, size, private)
            payloads.place_fresh(source_file, staging / rel, link=shared)
            if shared:
                # 链过来的是副本里那一份：就地并入共用库（库里已有同内容就换成库的链接）。
                blob_store.ingest_in_place(staging / rel)
        info = payloads.lineage_info_from_interface(interface)
        info["configClass"] = _config_class_name(staging)
        registered = payloads.register(
            root,
            staging,
            lineage=lineage,
            channel=channel or DEFAULT_CHANNEL,
            # 有更新器清单背书的记 update（ref 留空：它不是一个下载源，别让「来源」显示成
            # 本地路径）；其余记 import，ref 是来源目录（视图丢了时据此反查谱系）。
            source=(
                {"kind": "update", "ref": ""}
                if recorded is not None
                else {"kind": "import", "ref": str(source or "")}
            ),
            by="迁移",
            version=version,
            lineage_info=info,
            known_hashes=payload_files,
            origins=origins,
        )
        # 脚本记着的来源目录记进谱系（更新得来的载荷清单里没有导入目录）：视图丢了时
        # 反查谱系重建、整谱系回收认「脚本还在」都靠它。
        payloads.add_known_source(root, lineage, str(source or ""))
    except Exception:
        _remove_quietly(staging, "采纳半成品")
        raise
    # 视图就当作已挂在这份载荷上重建一遍：载荷文件换成载荷 / 共用库的链接，私有文件
    # inode 不变地带过去，标记随目录原子换入。
    return _realize_view(
        view,
        lineage,
        registered.payload_id,
        base=base,
        carry=True,
        assume_marker={"lineage": lineage, "payload": registered.payload_id},
    )


# --------------------------------------------------------------------------
# 传播：组里的空闲视图立即切到目标载荷
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupMember:
    """调用方在事件循环线程上从脚本表抄出来的一行（守护线程里遍历脚本表会撞
    「dict changed size」）。``busy`` = 脚本配置正锁着（运行中）。"""

    script_id: str
    channel: str
    busy: bool = False
    name: str = ""
    # 该脚本自己解析出的代理（脚本级优先，留空跟随全局）；切过去之后的运行环境确认用它。
    proxy_url: str | None = None


@dataclass
class PropagationResult:
    switched: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    # ``hold=True`` 时切过的视图的项目预约没放：{script_id: 预约 key}，交给环境确认线程放。
    held: dict[str, str] = field(default_factory=dict)


def release_held_reservations(held: Mapping[str, str]) -> None:
    """放掉 :func:`propagate_payload` 留着的预约（没交出去的那部分）。"""

    for key in list(held.values()):
        release_project_path_sync(key)


SKIP_BUSY = "正在运行，跑完后再切"
SKIP_RESERVED = "项目正被占用（运行 / 更新 / 准备环境），下次运行前再切"
SKIP_UNADOPTED = "还没登记项目版本（未采纳的老副本），本次不切"


def propagate_payload(
    lineage: str,
    channel: str,
    payload_id: str,
    members: Iterable[GroupMember | tuple[str, str]],
    *,
    switched_by: Mapping[str, Any] | None = None,
    exclude: Iterable[str] = (),
    base: Path | None = None,
    hold: bool = False,
) -> PropagationResult:
    """把组（谱系 + 渠道）里挂在别的载荷上的空闲视图切到 ``payload_id``。

    ``members`` 是调用方算好的候选脚本（``GroupMember`` 或 ``(script_id, channel)``），
    这里按视图标记筛出同谱系、同渠道、``payload ≠ 目标`` 的；不比版本号。对每个：
    拿得到项目预约就 :func:`switch_view`（``switchedBy`` 记下是谁的操作）后释放；运行中或
    拿不到预约就跳过——pending 是派生状态（``view.payload ≠ latest[channel]``），不写任何东西，
    由它自己下次运行前兑现。返回切了谁、跳了谁（附原因）、谁失败了。

    ``hold=True``：切成功的视图不放预约，记进 ``result.held`` 交给调用方（环境确认线程），
    切换与确认之间不留空档；调用方负责放（:func:`release_held_reservations`）。
    """

    result = PropagationResult()
    excluded = {str(item) for item in exclude}
    try:
        for raw in members:
            member = raw if isinstance(raw, GroupMember) else GroupMember(*raw)
            script_id = str(member.script_id)
            if script_id in excluded or (member.channel or DEFAULT_CHANNEL) != channel:
                continue
            try:
                view = embedded_project_dir(script_id, base)
            except EmbeddedProjectError:
                continue
            marker = read_view_marker(view)
            if marker is None:
                if copy_is_healthy(view):
                    try:
                        same = payloads.lineage_key_for_project(view) == lineage
                    except (payloads.PayloadError, ProjectionError):
                        same = False
                    if same:
                        result.skipped[script_id] = SKIP_UNADOPTED
                continue
            if str(marker.get("lineage") or "") != lineage:
                continue
            if str(marker.get("payload") or "") == payload_id:
                continue
            if member.busy:
                result.skipped[script_id] = SKIP_BUSY
                continue
            key = try_reserve_project_path_sync(view)
            if key is None:
                result.skipped[script_id] = SKIP_RESERVED
                continue
            keep = False
            try:
                switch_view(
                    script_id,
                    payload_id,
                    lineage=lineage,
                    base=base,
                    switched_by=switched_by,
                )
                result.switched.append(script_id)
                if hold:
                    result.held[script_id] = key
                    keep = True
            except Exception as exc:  # noqa: BLE001 - 一个 T 失败只影响它自己
                logger.opt(exception=True).warning(
                    f"[MFW 内嵌] 同步脚本 {script_id} 到 {payload_id} 失败: {exc}"
                )
                result.failed[script_id] = str(exc) or type(exc).__name__
            finally:
                if not keep:
                    release_project_path_sync(key)
    except BaseException:
        # 中途出意外：已经留着的预约不能泄漏（否则那些视图再也拿不到预约）。
        release_held_reservations(result.held)
        result.held.clear()
        raise
    return result


def shell_hint_from_report(script_config: Any) -> str:
    """副本里没有 MFW.exe 可扫，外壳家族只能从导入报告取。"""

    raw = script_config.get("Embedded", "Report")
    report: Any = raw
    if isinstance(raw, str):
        try:
            report = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return ""
    if not isinstance(report, dict):
        return ""
    families = report.get("shellFamilies")
    if not isinstance(families, list):
        return ""
    present = {str(item).strip() for item in families}
    for family in ("MXU", "MFAAvalonia", "MFW", "CFA", "MaaPiCli"):
        if family in present:
            return family
    return ""


__all__ = [
    "EMBEDDED_PROJECTS_DIR",
    "MIGRATION_SWITCHED_BY",
    "ENV_CONFIRMED_FIELD",
    "PYCACHE_DIR_NAME",
    "STAGING_DIR_NAME",
    "VIEW_MARKER_NAME",
    "EmbeddedProjectError",
    "GroupMember",
    "PayloadGarbageReport",
    "PropagationResult",
    "ViewResult",
    "clear_switched_by",
    "clone_embedded_copy",
    "collect_payload_garbage",
    "copy_is_healthy",
    "env_confirm_pending",
    "mark_env_confirmed",
    "release_held_reservations",
    "switch_or_confirm_in_progress",
    "discard_copy_update_baseline",
    "embedded_copy_dir_name",
    "embedded_project_dir",
    "embedded_projects_root",
    "embedded_status",
    "ensure_embedded_copy",
    "import_embedded_project",
    "imported_source_path",
    "inherit_embedded_record",
    "is_embedded_copy_dir_name",
    "materialize_view",
    "payloads_root",
    "propagate_payload",
    "read_interface_version",
    "read_view_marker",
    "recover_switches",
    "remove_tree",
    "resolve_maafw_project_root",
    "resolve_view_payload",
    "set_migration_active",
    "settle_adopted_latest",
    "migration_active",
    "shell_hint_from_report",
    "switch_root",
    "switch_in_progress",
    "switch_view",
    "write_view_marker",
]
