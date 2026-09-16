#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""通用脚本配置备份归档：MAS 用户配置副本 / 脚本原生配置（File/Folder 两态）。

备份时机（MAS「动手前」）：

- 任务启动（manager ``prepare``）：``native`` 归档 ``ConfigPath`` 当前状态
  （Folder 整目录 / File 单文件）——随后非直控运行会换入 MAS 配置、任务
  结束恢复原状，直控+快速配置会直接写入，归档必须在任何写入前；
- 运行 / 配置会话下发前（AutoProxy / ScriptConfig 的 ``set_general``）：
  ``mas`` 归档该用户的 ``ConfigFile`` 目录（下发源，运行回写与会话保存会
  覆盖它）；
- 编辑界面进入（前端 ensure）：``native`` 捕捉「MAS 操作前原始态」；
- 编辑界面退出（前端 ensure）：``mas`` 归档 MAS 配置副本终态。

General 的目录模型与 MAA 不同：``ConfigFile`` **恒按用户**（每个用户持有
自己的目录，脚本态用户也不例外），三态只决定 MAS 是否读写它——因此 mas
池按用户分桶即恢复目标，无 owner 解耦、无侧车（MAS 编辑页字段不注入原生
配置，不属于配置内容）。配置格式任意（透传），预览为**文件清单粒度**
（文件名 + 大小），详细内容经「查看详细配置」在脚本 GUI 里查看。

时间戳快照、指纹去重、保留清理与整目录恢复的通用逻辑由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
General 特有的 File/Folder 两态语义与恢复前强制归档。
"""

import shutil
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    restore_dir,
)

logger = get_logger("通用脚本配置备份")


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户池用）：``data/{script_id}/GeneralBackups``。"""

    return Path.cwd() / "data" / script_id / "GeneralBackups"


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/GeneralBackups/mas/{user_id}``。

    恒按用户分桶——General 的 ConfigFile 目录本来就按用户隔离（无 MAA 式
    脚本态共享 Default），池与恢复目标一一对应。
    """

    return backup_root(script_id) / "mas" / user_id


def mas_config_dir(script_id: str, user_id: str) -> Path:
    """MAS 配置目录：``data/{script_id}/{user_id}/ConfigFile``（恒按用户）。"""

    return Path.cwd() / "data" / script_id / user_id / "ConfigFile"


def native_backup_root(script_id: str, config_path: str | Path) -> Path:
    """脚本原生配置的**脚本级**归档目录：``data/{script_id}/GeneralBackups/native/{key}``。

    通用脚本（脚本级 owner）：归档生命周期随脚本实例；``key`` 仍取物理
    配置根指纹（File 态取文件自身路径、Folder 态取目录路径），脚本内换绑
    配置路径后旧备份不与新配置混淆。
    """

    return (
        Path.cwd()
        / "data"
        / script_id
        / "GeneralBackups"
        / "native"
        / config_root_key(config_path)
    )


# ══════════════════ MAS 配置副本（目录型，恒按用户） ══════════════════


def collect_mas_files(mas_dir: Path) -> dict[str, Path]:
    """收集用户 ConfigFile 目录文件集（目录缺失或为空返回空 dict）。

    供声明式池声明归档内容（``files`` 回调）；:func:`archive_mas_backup`
    亦复用本函数。
    """

    mas_dir = Path(mas_dir)
    if not mas_dir.is_dir() or not any(mas_dir.iterdir()):
        return {}
    return dir_files(mas_dir)


def archive_mas_backup(
    script_id: str, user_id: str, mas_dir: Path, force: bool = False
) -> Path | None:
    """归档用户 ConfigFile 目录到用户池（指纹去重，无变化跳过）。

    ``force=True`` 恢复前存底（不清理历史条目；内容与最新份一致时同样
    跳过——当前配置已存放在该份备份中）。目录不存在或为空时无可归档
    内容，返回 ``None``——首次使用前（从未跑过配置会话）为空是真实状态，
    不播种。
    """

    files = collect_mas_files(mas_dir)
    if not files:
        return None
    dest = archive_files(files, mas_backup_root(script_id, user_id), force=force)
    if dest is None:
        logger.info("用户 {} 的 MAS 配置无变化，跳过归档", user_id)
        return None
    logger.info("用户 {} 的 MAS 配置已归档: {}", user_id, dest.name)
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    """用户池的全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取用户池指定时间戳的归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(script_id: str, user_id: str, ts: str, mas_dir: Path) -> None:
    """把用户池归档恢复到该用户的 ConfigFile 目录（恢复前强制存底当前）。"""

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    mas_dir = Path(mas_dir)
    # 恢复前存底不设目录条件：目标缺失/为空时无可存底内容由 archive 自判
    archive_mas_backup(script_id, user_id, mas_dir, force=True)
    restore_dir(mas_backup_root(script_id, user_id), ts, mas_dir)
    logger.info("用户 {} 的 MAS 配置已恢复备份 {}", user_id, ts)


def archive_mas_runtime_backup(script_id: str, user_id: str, mas_dir: Path) -> None:
    """运行 / 配置会话下发前归档 MAS 配置（下发源）到用户池。

    运行回写与会话保存会覆盖它，下发前存底；指纹去重，失败只记日志，
    绝不中止随后的运行或会话（归档是现场保护，不是前置条件）。
    """

    try:
        archive_mas_backup(script_id, user_id, mas_dir)
    except Exception as e:  # noqa: BLE001 - 归档失败不阻断下发
        logger.opt(exception=True).warning(f"MAS 配置下发前归档失败: {e}")


# ══════════════════ 脚本原生配置（ConfigPath，File/Folder 两态） ══════════════════


def collect_native_files(config_path: str | Path, config_mode: str) -> dict[str, Path]:
    """收集脚本原生配置文件集（Folder 整目录 / File 单文件）。

    路径不存在（或 Folder 目录为空）返回空 dict；未知模式记警告后返回
    空 dict。供声明式池声明归档内容（``files`` 回调），也供
    :func:`archive_native_backup` 复用。
    """

    config_path = Path(config_path)
    if config_mode == "Folder":
        if not config_path.is_dir() or not any(config_path.iterdir()):
            return {}
        return dir_files(config_path)
    if config_mode == "File":
        if not config_path.is_file():
            return {}
        return {config_path.name: config_path}
    logger.warning(f"未知的配置路径模式，跳过归档: {config_mode}")
    return {}


def archive_native_backup(
    script_id: str, config_path: Path, config_mode: str, force: bool = False
) -> Path | None:
    """归档脚本原生配置当前状态（Folder 整目录 / File 单文件）。

    归档落到**脚本级池**（``data/{script_id}/``，生命周期随脚本实例；
    池内按物理配置根指纹二级分桶）。路径不存在时无可归档内容，返回
    ``None``；``config_mode`` 取 ``Script.ConfigPathMode``（``Folder`` /
    ``File``）。
    """

    files = collect_native_files(config_path, config_mode)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(script_id, config_path), force=force)
    if dest is None:
        logger.info("通用脚本原生配置无变化，跳过归档")
        return None
    logger.info("通用脚本原生配置已归档: {}", dest.name)
    return dest


def list_native_backups(script_id: str, config_path: str | Path) -> list[str]:
    """脚本原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(script_id, config_path))


def get_native_backup_dir(
    script_id: str, config_path: str | Path, ts: str
) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(script_id, config_path), ts)


def restore_native_backup(
    script_id: str, config_path: Path, config_mode: str, ts: str
) -> None:
    """把归档恢复到脚本原生配置（恢复前强制存底当前，误恢复可找回）。

    Folder 态整目录替换；File 态取备份内的单文件（File 池每份归档只含
    ``ConfigPath.name`` 一个文件）覆盖目标。
    """

    backup_dir = get_native_backup_dir(script_id, config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(script_id, config_path, config_mode, force=True)
    if config_mode == "Folder":
        restore_dir(native_backup_root(script_id, config_path), ts, config_path)
    elif config_mode == "File":
        files = dir_files(backup_dir)
        if not files:
            raise ValueError(f"备份内容为空: {ts}")
        # File 池每份归档只含 ConfigPath.name 一个文件；同名键缺失（如模式
        # 切换后复用同池的旧归档）才回退单文件
        backup_file = files.get(config_path.name) or next(iter(files.values()))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(backup_file, config_path)
    else:
        raise ValueError(f"未知的配置路径模式: {config_mode}")
    logger.info("通用脚本原生配置已恢复备份 {}", ts)
