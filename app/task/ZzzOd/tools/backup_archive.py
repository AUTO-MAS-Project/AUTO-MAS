#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 配置备份归档：一条龙原生配置 / MAS 用户配置，两类独立快照。

备份时机：MAS 运行注入前、配置会话基线注入前——此时 zzz-od 尚未被 MAS
触碰，两个视角各自捕获「动手前」的状态：

- ``onedragon``：一条龙自己的原生配置 = ``config/one_dragon.yml``（实例
  注册表）+ 注册表内的原生实例目录（**排除 MAS-xxx 槽**）。防止 MAS 的
  注入/合成视图等机制意外破坏原生配置后可完整找回；恢复只写回这些文件，
  MAS 槽目录永不触碰。
- ``mas``：MAS 用户配置 = 绑定槽（MAS-xxx）目录整份快照——含本页注入的
  账号/任务编排与用户在原生 GUI 里维护的配队等；恢复到槽并回填本页字段。

时间戳快照、指纹去重、保留清理与整目录恢复的通用逻辑由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
zzz-od 特有的文件集收集（排除 MAS 槽）、恢复语义（先清合成视图、恢复前
强制归档当前）与归档目录布局。
"""

import json
import shutil
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    archive_dir,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    restore_dir,
)
from app.utils.io import read_file, write_file

from .zzz_od_config import (
    _one_dragon_file,
    _view_sidecar_path,
    instance_dir,
    normalize_app_group_entries,
    restore_instance_view,
    user_field_patch,
    write_app_group,
    write_game_account,
)

logger = get_logger("ZZZ-OD 配置备份")

MAS_SLOT_PREFIX = "MAS-"
"""MAS 用户槽在注册表中的实例名前缀"""

MAS_USER_INFO_FILE = "mas_user_info.yml"
"""归档在 MAS 槽备份目录内的信息字段快照：基本信息卡中槽文件之外的字段。"""

# 基本信息卡中随槽备份一并归档的 UserData 信息字段（槽目录只覆盖账号/任务编排）
_MAS_INFO_FIELDS: tuple[str, ...] = (
    "Name",
    "Status",
    "Mode",
    "LauncherMode",
    "RemainedDay",
    "Notes",
)


def collect_mas_user_info(user_config) -> dict:
    """从用户配置对象收集基本信息卡的信息字段（Name/Status/Mode/.../PushLogMode）。

    槽备份只落盘账号与任务编排；用户名、启用状态、配置模式、启动器、剩余
    天数、备注与节点详情推送存在 UserData 中，恢复/预览需要与槽快照同批
    归档。字段缺失时跳过，保持与旧备份兼容。
    """

    info: dict = {}
    for field in _MAS_INFO_FIELDS:
        try:
            value = user_config.get("Info", field)
        except Exception:
            value = None
        if value is not None:
            info[field] = value
    try:
        value = user_config.get("Notify", "PushLogMode")
    except Exception:
        value = None
    if value is not None:
        info["PushLogMode"] = value
    return info


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户槽池用）：``data/{script_id}/ZzzOdBackups``。"""

    return Path.cwd() / "data" / script_id / "ZzzOdBackups"


def project_backup_root() -> Path:
    """一条龙备份的项目级根目录：``data/ZzzOdBackups``。

    onedragon（一条龙原生配置）池挂在这里而不是脚本目录下——物理安装目录
    跨脚本共享、不随脚本删除（mas 用户槽池仍按脚本，见 :func:`mas_backup_root`）。
    """

    return Path.cwd() / "data" / "ZzzOdBackups"


def onedragon_backup_root(root: str | Path) -> Path:
    """一条龙原生配置的项目级归档目录：``data/ZzzOdBackups/onedragon/{key}``。

    ``key`` 是物理安装根的指纹（:func:`config_root_key`）——同一份安装目录
    无论被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。

    旧布局（beta.4 及更早的脚本级池 ``data/{script_id}/ZzzOdBackups/onedragon/``）
    **刻意不兼容**：不做兼容读取、也不自动搬迁。旧池内容本身是干净的原生
    快照（排除 MAS 槽、不含账号/编排，恢复只写回原生位置），但新池按物理
    安装根指纹归桶、跨脚本共享——旧脚本目录的条目无法与桶一一对应，接进
    新池会破坏跨脚本共享语义；确需找回时由维护者用
    ``.dev/migrate_backup_layout.py``（不入库）按指纹手动搬家。
    """

    return project_backup_root() / "onedragon" / config_root_key(root)


def mas_backup_root(script_id: str, slot_idx: int) -> Path:
    """MAS 用户槽的归档目录：``.../ZzzOdBackups/mas/{slot:02d}``。"""

    return backup_root(script_id) / "mas" / f"{int(slot_idx):02d}"


def native_registry_file(root: Path) -> Path:
    """一条龙原生注册表源文件。

    合成视图在盘时（会话/运行残留或闪退现场）``one_dragon.yml`` 是 MAS 的
    视图，sidecar（``one_dragon.yml.mas-view.bak``）才是原生原件——备份一条
    龙原生配置必须拍原件，杜绝把合成视图/MAS 槽混进一条龙备份；无 sidecar
    时现场即原生。
    """

    sidecar = _view_sidecar_path(root)
    if sidecar.exists():
        return sidecar
    return _one_dragon_file(root)


def _onedragon_files(root: Path) -> dict[str, Path]:
    """当前一条龙原生配置的文件集：one_dragon.yml（原生注册表）+ 注册表内原生实例目录。

    注册表源走 :func:`native_registry_file`（视图在盘时读 sidecar 原件）；
    实例目录按「一条龙原生注册表」逐 idx 收集，MAS- 前缀槽排除——与 final
    架构一致：项目级池只含一条龙自己的内容，绝不带上 MAS 注入的槽。
    """

    files: dict[str, Path] = {}
    od_file = native_registry_file(root)
    if od_file.is_file():
        # one_dragon.yml 条目始终指向原生注册表内容（sidecar 存在时取 sidecar）
        files["one_dragon.yml"] = od_file
    for raw in (read_file(od_file) or {}).get("instance_list") or []:
        item = raw if isinstance(raw, dict) else {}
        if str(item.get("name") or "").startswith(MAS_SLOT_PREFIX):
            continue  # MAS 用户槽不属于一条龙原生配置
        idx = int(item.get("idx", -1))
        idx_dir = instance_dir(root, idx)
        if not idx_dir.is_dir():
            continue
        for path in sorted(idx_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(idx_dir).as_posix()
                files[f"{idx}/{rel}"] = path
    return files


# ══════════════════ 一条龙原生配置 ══════════════════


def archive_onedragon_backup(root: Path, force: bool = False) -> Path | None:
    """归档一条龙原生配置（one_dragon.yml + 原生实例目录，排除 MAS 槽）。

    归档落到该项目级池（按物理安装根指纹分桶），与脚本实例解耦。内容与
    最近一份备份完全一致时跳过（``force=True`` 强制归档，用于恢复前存底——
    让「恢复前的配置」在列表里有明确的时间戳条目）；跳过返回 ``None``，
    否则返回归档目录。
    """

    files = _onedragon_files(root)
    if not files:
        raise ValueError(f"一条龙原生配置不存在: {root}")

    dest = archive_files(files, onedragon_backup_root(root), force=force)
    if dest is None:
        logger.info("一条龙原生配置无变化，跳过归档")
        return None

    logger.info(f"一条龙原生配置已归档: {dest.name} ({len(files)} 个文件)")
    return dest


def list_onedragon_backups(root: str | Path) -> list[str]:
    """一条龙原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(onedragon_backup_root(root))


def get_onedragon_backup_dir(root: str | Path, ts: str) -> Path | None:
    """取指定时间戳的一条龙归档目录；不存在返回 None。"""

    return get_backup_dir(onedragon_backup_root(root), ts)


def restore_onedragon_backup(root: Path, ts: str) -> None:
    """把归档恢复到一条龙原生位置（恢复前自动归档当前，误恢复可找回）。

    只写回备份中存在的文件（one_dragon.yml + 对应实例目录）；MAS 槽目录
    与备份外的实例目录一律不触碰。恢复前先清残留合成视图，防止 sidecar
    自愈把刚恢复的注册表盖回旧内容。
    """

    backup_dir = get_onedragon_backup_dir(root, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    backup_files = dir_files(backup_dir)
    if not backup_files:
        raise ValueError(f"备份内容为空: {ts}")

    # 先清残留合成视图（幂等；无 sidecar 即 no-op）
    restore_instance_view(root)
    # 恢复前强制归档当前原生配置——「恢复前的配置」在列表里有明确的时间戳条目
    archive_onedragon_backup(root, force=True)

    od_file = backup_files.get("one_dragon.yml")
    if od_file is not None:
        shutil.copyfile(od_file, _one_dragon_file(root))

    # 备份中的实例目录逐个替换（MAS 槽不在备份内，天然不受影响）
    idx_dirs = sorted(
        {rel.split("/", 1)[0] for rel in backup_files if "/" in rel},
    )
    for idx_dir_name in idx_dirs:
        idx = int(idx_dir_name)
        target = instance_dir(root, idx)
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(backup_dir / idx_dir_name, target)

    logger.info(f"一条龙原生配置已恢复备份 {ts} (实例目录 {len(idx_dirs)} 个)")


# ══════════════════ MAS 用户配置（绑定槽） ══════════════════


def archive_mas_backup(
    script_id: str,
    slot_idx: int,
    slot_dir: Path,
    force: bool = False,
    meta: dict | None = None,
) -> Path | None:
    """归档 MAS 用户槽目录整份（覆盖式加时间戳）。

    内容与最近一份备份完全一致时跳过（``force=True`` 强制归档，用于恢复前
    存底）；跳过返回 ``None``，否则返回归档目录。``meta`` 为随槽一起归档的
    信息字段快照（见 :data:`MAS_USER_INFO_FILE`），写入后 ``list/preview/
    restore`` 可在不触碰当前配置的情况下还原该时点的基本信息卡内容。

    指纹一致性：``mas_user_info.yml`` 必须在 ``archive_dir`` 内部指纹对比
    之前已存在于源目录内（否则新归档目录比旧目录多 1 个文件、hash 永远
    不等 → MAS 池每轮都新建一份，第 11 次起最旧的被清）。本函数把 meta
    临时写入源槽做指纹对比，归档后立刻清理临时文件——归档目录内仍保留
    完整 ``mas_user_info.yml`` 副本。
    """

    staged_meta_path: Path | None = None
    if meta:
        # 临时把 meta 写进源目录，dir_files 自动收录，让指纹对比看到这一文件
        staged_meta_path = slot_dir / MAS_USER_INFO_FILE
        write_file(staged_meta_path, meta)
    try:
        dest = archive_dir(slot_dir, mas_backup_root(script_id, slot_idx), force=force)
    finally:
        # 即便 archive_dir 抛错也清理临时文件，避免污染源 slot_dir
        if staged_meta_path is not None:
            try:
                staged_meta_path.unlink()
            except OSError as e:
                logger.warning(f"清理临时 {MAS_USER_INFO_FILE} 失败: {e}")
    if dest is None:
        logger.info(f"槽 {slot_idx:02d} MAS 配置无变化，跳过归档")
        return None
    if meta:
        # 归档目录内保留完整副本（list/preview/restore 消费该文件）
        write_file(dest / MAS_USER_INFO_FILE, meta)

    logger.info(f"槽 {slot_idx:02d} MAS 配置已归档: {dest.name}")
    return dest


def list_mas_backups(script_id: str, slot_idx: int) -> list[str]:
    """MAS 用户槽全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, slot_idx))


def get_mas_backup_dir(script_id: str, slot_idx: int, ts: str) -> Path | None:
    """取指定时间戳的 MAS 归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, slot_idx), ts)


def restore_mas_backup(
    script_id: str,
    slot_idx: int,
    ts: str,
    slot_dir: Path,
    meta: dict | None = None,
) -> None:
    """把归档恢复到 MAS 用户槽目录（恢复前自动归档当前，误恢复可找回）。

    ``meta`` 为恢复前当前信息字段快照，随归档一并存底（恢复动作自身会覆盖
    UserData 的信息字段，需把覆盖前的值也留下）。
    """

    slot_dir = Path(slot_dir)
    if slot_dir.is_dir():
        # 恢复前强制归档当前内容——「恢复前的配置」在列表里有明确的时间戳条目
        archive_mas_backup(script_id, slot_idx, slot_dir, force=True, meta=meta)
    restore_dir(mas_backup_root(script_id, slot_idx), ts, slot_dir)


def materialize_user_applist(slot_dir: Path, applist_json: str | None) -> bool:
    """把 MAS 页面任务编排（AppList JSON 整表）物化进绑定槽 ``_group.yml``。

    槽只有在配置会话/运行注入时才会带上编排；用户只在 MAS 页面保存过编排
    就退出的话，直接快照槽会漏掉它，恢复这种备份会把编排清空。退出编辑页
    归档 mas 前调用：写盘与注入同款（整表含未启用项原位，不清运行记录）。
    AppList 为空或非法时跳过，返回是否实际写入。
    """

    try:
        apps = json.loads(str(applist_json or "[]"))
    except json.JSONDecodeError:
        return False
    if not isinstance(apps, list) or not apps:
        return False
    write_app_group(slot_dir, normalize_app_group_entries(apps))
    return True


def materialize_user_fields(slot_dir: Path, user_config) -> None:
    """把 MAS 页面账号字段与任务编排物化进绑定槽（``game_account.yml`` + ``_group.yml``）。

    账号字段（区服/路径/语言/账号/密码/B服名/自定义窗口标题）与任务编排只
    存在 MAS UserData，槽只有在会话/运行注入时才带上——直接快照槽会漏掉
    它们，恢复这种备份会把 MAS 本页账号与编排清空（编排侧见
    :func:`materialize_user_applist`，账号字段同款陷阱）。经统一归档入口
    :func:`archive_mas_config_backup` 与恢复前存底调用；写盘与注入同款：
    账号只写非空字段、编排整表含未启用项，不清运行记录。
    """

    write_game_account(slot_dir, user_field_patch(user_config))
    materialize_user_applist(slot_dir, user_config.get("OneDragon", "AppList"))


def archive_mas_config_backup(
    script_id: str,
    slot_idx: int,
    slot_dir: Path,
    user_config,
    *,
    force: bool = False,
    meta: dict | None = None,
) -> Path | None:
    """归档 MAS 用户槽的「页面配置快照」：先物化账号+编排，再走原语快照。

    ZzzOd 的账号/编排只存在 MAS UserData，槽要会话/运行注入才带上——**所有
    把当前 MAS 配置存为备份的入口（编辑页退出 / 会话启动 / 运行注入前 /
    导入覆盖前 / 恢复前存底）都必须经本函数**，否则备份缺账号，预览与恢复
    回填全会落空。裸快照原语 :func:`archive_mas_backup` 不再直接对外用于
    「MAS 配置快照」语义（仅 :func:`restore_mas_backup` 内部恢复前存底使用）。
    """

    materialize_user_fields(slot_dir, user_config)
    return archive_mas_backup(script_id, slot_idx, slot_dir, force=force, meta=meta)
