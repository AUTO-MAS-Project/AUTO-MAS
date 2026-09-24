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
- ``recycle``：槽回收池 = 槽目录被删除前的最后一份存底（删用户/删脚本/
  孤儿槽回收三处），挂在项目级、按安装根指纹分桶——槽目录的归属是那份
  安装目录而不是某个脚本实例，删脚本不该把存底一起删掉。槽的 mas 备份池
  也随槽一起搬进来（``{slot}/mas-backups``）：mas 池按脚本+槽分桶、没有
  用户维度，槽号被新用户复用后留在原位会串到别人名下。

时间戳快照、指纹去重、保留清理与整目录恢复的通用逻辑由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
zzz-od 特有的文件集收集（排除 MAS 槽）、恢复语义（先清合成视图、恢复前
强制归档当前）与归档目录布局。
"""

import json
import shutil
from pathlib import Path

import yaml

from app.utils import get_logger
from app.utils.config_archive import (
    archive_dir,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    restore_dir,
    timestamp_sort_key,
)
from app.utils.io import ConfigCorruptedError, force_rmtree, read_dict_file

from .zzz_od_config import (
    _one_dragon_file,
    _view_sidecar_path,
    instance_dir,
    launch_args_patch,
    normalize_app_group_entries,
    restore_instance_view,
    user_field_patch,
    write_app_group,
    write_game,
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


def read_native_registry(root: Path) -> dict:
    """读一条龙原生注册表内容（视图在盘时读 sidecar 原件，与备份口径一致）。

    sidecar 后缀是 ``.mas-view.bak``，``read_file`` 按后缀不认得、会退回
    原始字符串，必须显式指定 YAML 解析；一条龙本体 non-atomic 写落盘可能
    留下 NUL 填充，故按 ``.sanitized.yaml`` 容错读（与运行记录同款），
    结构完整时仍能枚举出实例目录。

    结构判据（依据上游源码 ``src/one_dragon/base/config/one_dragon_config.py``）：
    ``dict_instance_list`` 对缺键按 ``get('instance_list', [])`` 默认空读，
    ``delete_instance`` 没有「至少留一个」守卫（上游 GUI 删光实例后落盘
    ``instance_list: []`` 是真实可达状态），首次落盘也可能只写
    ``instance_run`` 等键——故**缺键与空列表都是上游语义内的合法状态**
    （等价空注册表），只有「键存在但不是列表」「条目不是映射或 idx 不是
    整数」才只可能是损坏，抛 :class:`ConfigCorruptedError` 交由调用方
    决定（备份拦截不产生残缺快照，恢复由用户确认后强制进行），不再静默
    按空处理。

    Raises:
        ConfigCorruptedError: 文件存在但内容不可信（含损坏位置）。
    """

    od_file = native_registry_file(root)
    if not od_file.is_file():
        return {}
    # 上游 non-atomic 写残留 NUL 属正常可读回，走 sanitized 容错解析；
    # 其余坏档（截断/非映射）由 read_dict_file 显式报损坏（带路径）
    data = read_dict_file(od_file, format=".sanitized.yaml")
    if "instance_list" not in data:
        # 缺键：上游 getter 对缺键默认空读，等价空注册表
        return data
    entries = data["instance_list"]
    if not isinstance(entries, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("idx"), int)
        or isinstance(item.get("idx"), bool)
        for item in entries
    ):
        # 键存在但不是列表（含显式 null——上游遍历会直接崩），或条目
        # 非映射 / idx 缺失或非整数：调用方遍历会炸无关
        # TypeError/ValueError，或静默得出错误的占用判定与文件集，
        # 一律按损坏上报
        raise ConfigCorruptedError(od_file)
    return data


def collect_onedragon_files(root: Path) -> dict[str, Path]:
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
    for raw in read_native_registry(root).get("instance_list") or []:
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
    最近一份备份完全一致时跳过（``force=True`` 恢复前存底，同样不产生
    冗余条目）；跳过返回 ``None``，否则返回归档目录。
    """

    files = collect_onedragon_files(root)
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


def restore_onedragon_backup(
    root: Path, ts: str, *, snapshot_current: bool = True
) -> None:
    """把归档恢复到一条龙原生位置（恢复前自动归档当前，误恢复可找回）。

    只写回备份中存在的文件（one_dragon.yml + 对应实例目录）；MAS 槽目录
    与备份外的实例目录一律不触碰。恢复前先清残留合成视图，防止 sidecar
    自愈把刚恢复的注册表盖回旧内容。

    ``snapshot_current=False``：注册表损坏且用户已确认强制恢复时跳过
    「恢复前强制归档当前」——该步要读损坏的注册表；跳过即少一份存底，
    但不阻断用户主动发起的恢复。

    ``snapshot_current=True`` 时先校验注册表可读（损坏抛
    :class:`ConfigCorruptedError`），且校验在清合成视图之前：否则「清视图」
    已把 sidecar 覆盖回 ``one_dragon.yml`` 并删掉 sidecar，用户看到的 409
    发生在现场已被改动之后。校验内容与随后归档读到的同源。
    """

    backup_dir = get_onedragon_backup_dir(root, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    backup_files = dir_files(backup_dir)
    if not backup_files:
        raise ValueError(f"备份内容为空: {ts}")

    if snapshot_current:
        read_native_registry(root)

    # 先清残留合成视图（幂等；无 sidecar 即 no-op）
    restore_instance_view(root)
    if snapshot_current:
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


def mas_user_info_content(meta: dict) -> str:
    """信息字段快照的 YAML 内容（与 ``write_file`` 落盘序列化一致，免临时文件）。"""

    return yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)


def collect_mas_files(
    slot_dir: str | Path, meta: dict | None = None
) -> dict[str, "Path | str"]:
    """收集 MAS 用户槽文件集 + 信息字段快照（内存 YAML，免临时落盘）。

    槽目录不存在时无可归档内容，返回空 dict（信息快照不单独入档）。
    """

    slot_dir = Path(slot_dir)
    files: dict[str, "Path | str"] = {}
    if slot_dir.is_dir():
        files.update(dir_files(slot_dir))
    if meta and files:
        files[MAS_USER_INFO_FILE] = mas_user_info_content(meta)
    return files


def archive_mas_backup(
    script_id: str,
    slot_idx: int,
    slot_dir: Path,
    force: bool = False,
    meta: dict | None = None,
) -> Path | None:
    """归档 MAS 用户槽目录整份（覆盖式加时间戳）。

    内容与最近一份备份完全一致时跳过（``force=True`` 恢复前存底，同样
    不产生冗余条目）；跳过返回 ``None``，否则返回归档目录。``meta`` 为随槽一起归档的
    信息字段快照（见 :data:`MAS_USER_INFO_FILE`），写入后 ``list/preview/
    restore`` 可在不触碰当前配置的情况下还原该时点的基本信息卡内容。

    指纹一致性：``mas_user_info.yml`` 以内存 YAML 随文件集一起入档
    （:func:`archive_files` 支持内存内容），不落临时文件进源槽；归档目录
    内保留完整副本，源槽目录永不污染。
    """

    files = collect_mas_files(slot_dir, meta)
    if not files:
        return None
    dest = archive_files(files, mas_backup_root(script_id, slot_idx), force=force)
    if dest is None:
        logger.info(f"槽 {slot_idx:02d} MAS 配置无变化，跳过归档")
        return None

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
    """把 MAS 页面账号字段、启动参数与任务编排物化进绑定槽。

    账号字段（区服/路径/语言/账号/密码/B服名/自定义窗口标题）、启动参数
    （``game.yml`` 六字段）与任务编排只存在 MAS UserData，槽只有在会话/
    运行注入时才带上——直接快照槽会漏掉它们，恢复这种备份会把 MAS 本页
    账号与编排清空（编排侧见 :func:`materialize_user_applist`，账号字段
    同款陷阱）。经统一归档入口 :func:`archive_mas_config_backup` 与恢复前
    存底调用；写盘与注入同款：账号只写非空字段、启动参数整组下发、编排
    整表含未启用项，不清运行记录。
    """

    write_game_account(slot_dir, user_field_patch(user_config))
    write_game(slot_dir, launch_args_patch(user_config))
    materialize_user_applist(slot_dir, user_config.get("OneDragon", "AppList"))


def archive_mas_config_backup(
    script_id: str,
    slot_idx: int,
    slot_dir: Path,
    user_config,
    *,
    force: bool = False,
    meta: dict | None = None,
    fail_on_snapshot_error: bool = False,
) -> Path | None:
    """归档 MAS 用户槽的「页面配置快照」：先物化账号+编排，再走原语快照。

    ZzzOd 的账号/编排只存在 MAS UserData，槽要会话/运行注入才带上——**所有
    把当前 MAS 配置存为备份的入口（编辑页退出 / 会话启动 / 运行注入前 /
    导入覆盖前 / 恢复前存底）都必须经本函数**，否则备份缺账号，预览与恢复
    回填全会落空。裸快照原语 :func:`archive_mas_backup` 不再直接对外用于
    「MAS 配置快照」语义（仅 :func:`restore_mas_backup` 内部恢复前存底使用）。

    失败语义分两段：物化（写槽）失败照常抛出——注入/会话依赖物化结果，
    半成品槽不该继续；快照（指纹归档）失败默认只记日志返回 ``None``——
    归档是现场保护，不是前置条件。**覆盖性操作（导入覆盖前）必须传
    ``fail_on_snapshot_error=True``**：存底是覆盖的前提，失败照常覆盖会把
    覆盖前现场彻底丢掉。
    """

    materialize_user_fields(slot_dir, user_config)
    try:
        return archive_mas_backup(script_id, slot_idx, slot_dir, force=force, meta=meta)
    except Exception:
        if fail_on_snapshot_error:
            raise
        logger.opt(exception=True).warning(
            "ZZZ-OD 用户槽配置快照失败，已跳过（不阻断注入/会话）"
        )
        return None


# ══════════════════ 实例槽回收（删除前存底） ══════════════════


def recycle_backup_root(root: str | Path, slot_idx: int) -> Path:
    """实例槽回收池：``data/ZzzOdBackups/recycle/{安装根指纹}/{slot:02d}``。"""

    return (
        project_backup_root()
        / "recycle"
        / config_root_key(root)
        / f"{int(slot_idx):02d}"
    )


def recycle_pool_root(root: str | Path) -> Path:
    """实例槽回收池的安装根桶：``data/ZzzOdBackups/recycle/{安装根指纹}``。

    清空回收池即删除本目录（只含被删用户/脚本留下的存底；``onedragon`` 与
    mas 配置恢复池在别的子树，不受影响）。
    """

    return project_backup_root() / "recycle" / config_root_key(root)


def _has_native_registry(root: Path) -> bool:
    """回收前置：一条龙注册表必须在场。

    注册表缺失时无从区分「盘上的目录是原生实例」与「是 MAS 残留」，回收
    可能删掉用户自己的原生实例目录（含账号配置），故一律放弃；注册表损坏
    由 :func:`read_native_registry` 抛错，同样交给调用方放弃。
    """

    return native_registry_file(root).is_file()


def native_slot_idxs(root: Path) -> set[int]:
    """一条龙原生注册表登记的实例下标。

    走 :func:`read_native_registry`（合成视图在盘时读 sidecar 原件）：按现场
    ``one_dragon.yml`` 判定会把合成视图里的 MAS 槽当原生、把原生实例目录当
    孤儿，回收就会删掉用户自己的实例目录。

    Raises:
        ConfigCorruptedError: 注册表内容不可信，调用方必须放弃回收。
    """

    return {
        int(item.get("idx", -1))
        for item in read_native_registry(root).get("instance_list") or []
        if isinstance(item, dict)
    }


def list_slot_idxs(root: Path) -> list[int]:
    """盘上实际存在的实例槽下标（``config/NN`` 数字目录，升序）。"""

    config_root = Path(root) / "config"
    if not config_root.is_dir():
        return []
    return sorted(
        int(child.name)
        for child in config_root.iterdir()
        if child.is_dir() and child.name.isdigit()
    )


def list_orphan_slots(
    root: Path, bound_idxs: set[int], *, allocated_idxs: set[int] | None = None
) -> list[int]:
    """盘上既不在原生注册表、也没有 MAS 用户绑定的槽（升序）。

    这类槽是「MAS 分配过、用户或脚本已删除」的残留：一条龙注册表里没有它，
    GUI 看不见也删不掉，只能由 MAS 回收；不回收就永久占用 idx
    （``find_free_instance_idx`` 把盘上目录也当占用），新用户只能往后排。
    ``bound_idxs`` 必须含全部 ZzzOd 用户（含本次要注入/会话的），否则会把
    正在用的槽当孤儿回收，槽里的配队等随即丢失。

    ``allocated_idxs`` 是「允许回收的号」白名单：自动路径传的是台账里归属
    用户已不存在的号（``AutoProxy._recyclable_allocated_idxs``），不在名单里
    的一律保留。一条龙原生流程是「先建目录后写注册表」，用户在原生 GUI 新建
    实例的瞬间盘上目录已存在、注册表尚未落盘，单看盘上目录会把它误判成残留
    删掉；同理，运行期副本里的绑定号还没回写时，只按持久绑定判孤儿也会收走
    在用的槽。``None`` 表示不设限（手动清理这类用户显式发起的动作）。

    Raises:
        ConfigCorruptedError: 注册表不可读——原生名单缺失，不能把原生实例
            误标成孤儿。
    """

    native = native_slot_idxs(root)
    bound = {int(i) for i in bound_idxs}
    allowed = None if allocated_idxs is None else {int(i) for i in allocated_idxs}
    return [
        idx
        for idx in list_slot_idxs(root)
        if idx not in native
        and idx not in bound
        and (allowed is None or idx in allowed)
    ]


def recycle_slot(root: Path, slot_idx: int, *, reason: str) -> bool:
    """把一个实例槽归档进回收池后删除目录（幂等，目录不存在即无操作）。

    先归档后删除：归档失败（文件被占用、磁盘满）时保留目录——宁可留下残留，
    也不做没有存底的删除；内容与回收池最近一份一致时归档原语自动跳过
    （内容已在池里），照常删除目录。

    Returns:
        是否真的删掉了目录（目录不存在、被跳过或归档失败时为 ``False``）。
    """

    slot_dir = instance_dir(root, slot_idx)
    if not slot_dir.is_dir():
        return False
    if not _has_native_registry(root):
        logger.warning(f"一条龙注册表不存在，跳过槽 {slot_idx:02d} 回收（{reason}）")
        return False
    try:
        archive_dir(slot_dir, recycle_backup_root(root, slot_idx))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"槽 {slot_idx:02d} 归档失败，保留目录不回收（{reason}）: {e}"
        )
        return False
    force_rmtree(slot_dir)
    logger.info(f"槽 {slot_idx:02d} 已回收（{reason}）")
    return True


def archive_taken_slot(root: Path, slot_idx: int, *, reason: str) -> bool:
    """槽号被一条龙原生实例抢走后，把残留内容存底进回收池（**不删目录**）。

    一条龙的「新增实例」只按自己的注册表找最小空号，看不见不在注册表里的
    MAS 槽，所以会把 MAS 槽的号当成空号拿去用。号被抢走后 ``config/NN`` 已经
    是那条原生实例的配置目录——删掉会毁掉用户的原生实例，故只归档不删。
    这样 MAS 侧残留（配队等）仍可从回收池找回，而不是永远卡在原生实例目录里
    （该号已进原生注册表，不再是「孤儿」，自动回收不会再碰它）。

    Returns:
        是否真的产生了新快照（目录不存在、内容与池内最近一份一致而跳过、
        或归档失败时为 ``False``）。
    """

    slot_dir = instance_dir(root, slot_idx)
    if not slot_dir.is_dir():
        return False
    try:
        archived = archive_dir(slot_dir, recycle_backup_root(root, slot_idx))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"槽 {slot_idx:02d} 的残留内容归档失败（{reason}）: {e}"
        )
        return False
    if archived is not None:
        logger.info(f"槽 {slot_idx:02d} 的残留内容已存底进回收池（{reason}）")
    return archived is not None


def recycle_orphan_slots(
    root: Path,
    bound_idxs: set[int],
    *,
    allocated_idxs: set[int] | None = None,
    swallow: bool = True,
) -> list[int]:
    """回收全部孤儿槽，返回实际删掉的槽下标。

    拿不到权威的原生名单时整体放弃（注册表缺失或损坏），宁可不收。
    ``allocated_idxs`` 见 :func:`list_orphan_slots`。
    ``swallow=True``（自动路径）：放弃时只告警并返回空列表，不阻断运行/会话；
    ``swallow=False``（手动清理）：把原因抛给调用方，界面才能显示「为什么没
    收」而不是恒显示「已回收 0 个」。

    Raises:
        ValueError: 注册表缺失且 ``swallow=False``。
        ConfigCorruptedError: 注册表不可读且 ``swallow=False``。
    """

    if not _has_native_registry(root):
        if not swallow:
            raise ValueError("一条龙注册表不存在，无法判定无主槽")
        logger.warning("一条龙注册表不存在，跳过孤儿槽回收")
        return []
    try:
        orphans = list_orphan_slots(root, bound_idxs, allocated_idxs=allocated_idxs)
    except ConfigCorruptedError as e:
        if not swallow:
            raise
        logger.warning(f"一条龙注册表不可读，跳过孤儿槽回收: {e}")
        return []
    return [idx for idx in orphans if recycle_slot(root, idx, reason="未绑定任何用户")]


def recycle_mas_backups(
    root: Path, script_id: str, slot_idx: int, *, reason: str
) -> bool:
    """把槽的 MAS 备份池整体归档进回收池后删除原池（幂等）。

    mas 池按 ``(脚本, 槽)`` 分桶、没有用户维度，槽被回收后 idx 会分给新用户
    ——留在原位会让新用户在「配置恢复」里看到前任用户的备份，甚至一键把
    前任的账号/编排恢复到自己的槽。归档进回收池（``.../{slot}/mas-backups``）
    而不是直接删：不丢历史，仍可从回收池找回。

    Returns:
        是否真的删掉了原池（池不存在、注册表缺失被跳过或归档失败时为 ``False``）。
    """

    pool = mas_backup_root(script_id, slot_idx)
    if not pool.is_dir():
        return False
    if not _has_native_registry(root):
        # 与 recycle_slot 同一守卫：注册表缺失时槽目录都没敢收，池也不能搬——
        # 否则槽原样留着、它的「配置恢复」历史却已被搬走，两条口径不一致
        logger.warning(
            f"一条龙注册表不存在，跳过槽 {slot_idx:02d} 的 MAS 备份池回收（{reason}）"
        )
        return False
    dest_root = recycle_backup_root(root, slot_idx) / "mas-backups"
    try:
        archive_dir(pool, dest_root)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"槽 {slot_idx:02d} 的 MAS 备份池归档失败，保留原池不回收（{reason}）: {e}"
        )
        return False
    force_rmtree(pool)
    logger.info(f"槽 {slot_idx:02d} 的 MAS 备份池已归档到回收池（{reason}）")
    return True


# ══════════════════ 实例槽总览与回收池查看 ══════════════════


def _dir_size(directory: Path) -> int:
    """目录内文件总字节数（总览展示占用用；单个文件读不到不影响合计）。"""

    total = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def list_slot_overview(root: Path, owners: dict[int, list[dict]]) -> list[dict]:
    """盘上实例槽总览：原生实例 / MAS 绑定槽 / 无主残留（按槽号升序）。

    元素含 ``idx`` / ``kind`` / ``has_dir`` / ``size`` / ``owners``。
    ``kind``：``native``=一条龙原生注册表里的实例；``mas``=有 MAS 用户绑定；
    ``orphan``=盘上有目录但既非原生也无人绑定（回收对象）。``owners`` 由
    调用方按同一份安装（:func:`config_root_key`）收集后传入——本模块不感知
    MAS 用户结构。**绑定但盘上无目录的槽也会出现**（``has_dir=False``）：
    那正是「槽目录数与用户数对不上」时最该看到的一行。

    Raises:
        ConfigCorruptedError: 注册表不可读——原生名单缺失，不能把原生实例
            误标成孤儿。
    """

    native = native_slot_idxs(root)
    bound = {int(i) for i in owners}
    entries: list[dict] = []
    for idx in sorted(native | set(list_slot_idxs(root)) | bound):
        slot_dir = instance_dir(root, idx)
        has_dir = slot_dir.is_dir()
        if idx in native:
            kind = "native"
        elif idx in bound:
            kind = "mas"
        else:
            kind = "orphan"
        entries.append(
            {
                "idx": idx,
                "kind": kind,
                "has_dir": has_dir,
                "size": _dir_size(slot_dir) if has_dir else 0,
                "owners": owners.get(idx, []),
            }
        )
    return entries


def _recycle_entry(slot_idx: int, kind: str, directory: Path) -> dict:
    """回收池一条记录（槽号 / 类别 / 时间戳 / 文件数 / 字节数 / 绝对路径）。"""

    return {
        "slot": slot_idx,
        "kind": kind,
        "ts": directory.name,
        "files": len(dir_files(directory)),
        "size": _dir_size(directory),
        "path": str(directory),
    }


def list_recycle_entries(root: Path) -> list[dict]:
    """回收池条目（按时间戳倒序，含槽目录快照与 mas 备份池快照两类）。

    布局：``recycle/{安装根指纹}/{slot:02d}/{ts}``（槽目录快照）与
    ``.../{slot:02d}/mas-backups/{ts}``（该槽的 MAS 备份池快照）。目录名
    不符合本模块布局的一律跳过。
    """

    pool_root = project_backup_root() / "recycle" / config_root_key(root)
    if not pool_root.is_dir():
        return []
    entries: list[dict] = []
    for slot_dir in sorted(pool_root.iterdir()):
        if not slot_dir.is_dir() or not slot_dir.name.isdigit():
            continue
        slot = int(slot_dir.name)
        # 只认本模块生成的时间戳目录名：同级的 mas-backups 不是槽快照
        entries.extend(
            _recycle_entry(slot, "slot", slot_dir / ts)
            for ts in list_times(slot_dir)
            if get_backup_dir(slot_dir, ts) is not None
        )
        entries.extend(
            _recycle_entry(slot, "mas", slot_dir / "mas-backups" / ts)
            for ts in list_times(slot_dir / "mas-backups")
        )
    return sorted(
        entries,
        key=lambda item: (timestamp_sort_key(item["ts"]), item["slot"]),
        reverse=True,
    )


def restore_recycle_slot(
    root: Path, slot_idx: int, ts: str, *, target_slot: int | None = None
) -> None:
    """把回收池里的槽目录快照恢复到 ``config/{目标槽:02d}``（先存底当前内容）。

    ``target_slot`` 留空表示恢复回原槽号；给出其他槽号即落到指定槽（现唯一
    调用方传的是目标用户的绑定槽——只物化内容不建立绑定的恢复没有出口，
    见 ``AppConfig.restore_zzzod_recycle``）。恢复是覆盖性操作，目标槽的选定
    与归属由调用方经 ``ensure_user_slot`` 解析；目标槽当前内容先按同一套归档
    进回收池——误恢复可找回。

    Raises:
        ValueError: 回收条目不存在或内容为空、该条目是只能查看的备份池快照，
            或恢复前存底失败。
    """

    dest_idx = int(slot_idx) if target_slot is None else int(target_slot)
    source_store = recycle_backup_root(root, slot_idx)
    # 类别判定走 get_backup_dir（内建时间戳格式校验）：ts 来自请求，裸拼路径
    # 会让 ``../``、绝对路径（Windows 下绝对路径会顶掉前缀）去探到池外目录，
    # 误判成备份池快照而把真实原因（条目不存在）盖掉
    if (
        get_backup_dir(source_store, ts) is None
        and get_backup_dir(source_store / "mas-backups", ts) is not None
    ):
        # 同桶里还挂着该槽的 MAS 备份池快照（{slot}/mas-backups/{ts}）：它只
        # 能查看不能恢复，直接说清楚，别让用户对着「备份不存在」猜
        raise ValueError(
            f"{ts} 是该槽 MAS 备份池的快照，不是槽内容快照，无法恢复到实例槽"
        )
    slot_dir = instance_dir(root, dest_idx)
    if slot_dir.is_dir():
        try:
            # force=True：存底不裁剪现存条目——否则恢复最旧一份时，本次存底
            # 会把保留池挤满、恰好裁掉正要恢复的那条，restore_dir 报不存在
            archive_dir(slot_dir, recycle_backup_root(root, dest_idx), force=True)
        except Exception as e:
            raise ValueError(f"恢复前存底失败，已中止: {e}") from e
    restore_dir(source_store, ts, slot_dir)


def clear_recycle_pool(root: Path) -> int:
    """清空本安装的回收池，返回删除的条目数（池不存在时为 0）。

    只删 ``recycle/{安装根指纹}/``（被删用户/脚本留下的存底）；``onedragon``
    原生池与 mas 配置恢复池在别的子树，不受影响。
    """

    pool_root = recycle_pool_root(root)
    if not pool_root.is_dir():
        return 0
    count = len(list_recycle_entries(root))
    force_rmtree(pool_root)
    logger.info(f"已清空实例槽回收池（{count} 条）")
    return count
