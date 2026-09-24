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

"""BAAH 配置文件读写与关键项托管。

BAAH 的用户配置是 ``BAAH_CONFIGS/<名字>.json`` 的**扁平 JSON**（没有嵌套分组），
软件配置单独放在 ``DATA/CONFIGS/software_config.json``。运行前必须把若干关键项
改成托管取值，运行结束后恢复用户原值。

写盘必须自校验：BAAH 读取配置时会吞掉所有异常并退回空配置，语法错误或带 BOM
的文件不会报错，而是静默按默认值运行。
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils import get_logger

logger = get_logger("BAAH 配置托管")

## 用户配置中需要托管的项
##
## 运行结束后自动退出：BAAH 默认停在 input() 等待回车，进程永不结束，会让本软件
## 误判为脚本卡死并反复重启；失败重试与通知同样收归本软件统一负责。
MANAGED_USER_VALUES: dict[str, Any] = {
    ## 运行结束后自动关闭 BAAH
    "CLOSE_BAAH_FINISH": True,
    ## 发生错误后也自动关闭 BAAH
    "CLOSE_BAAH_ERROR": True,
    ## 模拟器与游戏的启停由本软件编排，避免 BAAH 关掉仍需复用的实例
    "CLOSE_EMULATOR_FINISH": False,
    "CLOSE_EMULATOR_ERROR": False,
    "CLOSE_GAME_FINISH": False,
    "CLOSE_GAME_ERROR": False,
    ## 模拟器由本软件拉起，不允许 BAAH 再自行启动：它的启动路径按实例编号走，
    ## 配置与实际目标稍有出入就会拉起另一个实例，且冷启动耗时会吃掉它的等待窗口
    "TARGET_EMULATOR_PATH": "",
    ## 监听 TARGET_PORT 的进程就是本软件刚拉起的模拟器，BAAH 的"清理残留"会把它
    ## taskkill 掉；此时 TARGET_EMULATOR_PATH 已置空，BAAH 也拉不回来
    "KILL_PORT_IF_EXIST": False,
    ## ADB 目标改由 MAS 按所绑定的模拟器槽位推算，不再依赖 BAAH 侧手填
    "ADB_DIRECT_USE_SERIAL_NUMBER": False,
    ## 脚本运行报错后自动重新运行脚本的次数
    "RETRY_WHEN_ERROR": 0,
    ## 正常运行结束与错误时的通知改由本软件发送
    "NOTI_WHEN_SUCCESS": False,
    "NOTI_WHEN_ERROR": False,
}

## 软件配置中需要托管的项
##
## BAAH 默认不把日志写进文件，而任务报告的任务节点依赖日志文件采集。
MANAGED_SOFTWARE_VALUES: dict[str, Any] = {
    "SAVE_LOG_TO_FILE": True,
}

## 用户配置目录名（BAAH 程序目录下）
CONFIG_DIR_NAME = "BAAH_CONFIGS"
## 软件配置相对路径（BAAH 程序目录下）
SOFTWARE_CONFIG_RELATIVE = Path("DATA") / "CONFIGS" / "software_config.json"
## 日志目录相对路径（BAAH 程序目录下）
LOG_DIR_RELATIVE = Path("DATA") / "LOGS"


@dataclass
class ManagedConfigBackup:
    """托管前的配置快照，用于运行结束后恢复原值。"""

    ## 用户配置文件路径
    user_config_path: Path
    ## 用户配置在托管前的完整内容
    user_config: dict[str, Any] = field(default_factory=dict)
    ## 用户配置在托管前是否存在（不存在时恢复阶段应删除）
    user_config_existed: bool = False
    ## 软件配置文件路径，未托管时为 None
    software_config_path: Path | None = None
    ## 软件配置在托管前的完整内容
    software_config: dict[str, Any] = field(default_factory=dict)
    ## 软件配置在托管前是否存在
    software_config_existed: bool = False
    ## 是否真的执行过托管写入
    applied: bool = False


def read_json(path: Path) -> dict[str, Any]:
    """读取 JSON 配置。

    只有「文件不存在」才按空配置处理。其余情况——读取被拒绝、内容损坏、
    顶层不是对象——一律抛出：把它们当成空配置，托管流程就会拿这个空对象
    去比对与恢复，运行结束后等于把用户的配置文件清空。

    Args:
        path: 配置文件路径。

    Returns:
        dict[str, Any]: 解析出的配置内容；文件不存在时为空字典。

    Raises:
        OSError: 文件存在但读不出来（被占用、权限不足等）。
        ValueError: 内容不是合法 JSON，或顶层不是对象。
    """

    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError as e:
        raise ValueError(f"BAAH 配置不是 UTF-8 文本: {path} ({e})") from e

    try:
        content: Any = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"BAAH 配置内容损坏, 无法解析: {path} ({e})") from e

    if not isinstance(content, dict):
        raise ValueError(f"BAAH 配置顶层不是键值对象: {path}")

    return content


def write_json(path: Path, data: dict[str, Any]) -> None:
    """原子写入 JSON 配置。

    写入使用不带 BOM 的 UTF-8，并先做一次解析自校验，再以临时文件替换目标文件。

    Args:
        path: 配置文件路径。
        data: 要写入的配置内容。
    """

    text = json.dumps(data, indent=4, ensure_ascii=False)
    ## 自校验：BAAH 不会为损坏的配置报错，落盘内容必须保证可解析
    json.loads(text)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def resolve_config_name(config_name: str) -> str:
    """校验并规范化用户填写的 BAAH 配置名。

    Args:
        config_name: 用户在界面上填写的配置名，可带 ``.json`` 后缀。

    Returns:
        str: 规范化后的配置名（不含后缀）。

    Raises:
        ValueError: 配置名为空或包含路径分隔符。
    """

    name = config_name.strip()
    if name.lower().endswith(".json"):
        name = name[: -len(".json")]
    name = name.strip()
    if not name:
        raise ValueError("未填写 BAAH 配置文件名")
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError(f"BAAH 配置名不合法: {config_name}")
    return name


def resolve_user_config_path(config_dir: Path, config_name: str) -> Path:
    """把配置名解析为 BAAH 用户配置文件路径。

    Args:
        config_dir: BAAH 配置目录。
        config_name: 用户填写的配置名。

    Returns:
        Path: 配置文件路径。
    """

    return config_dir / f"{resolve_config_name(config_name)}.json"


def list_config_names(config_dir: Path) -> list[str]:
    """列出 BAAH 配置目录下已有的配置文件名。

    Args:
        config_dir: BAAH 配置目录（``BAAH_CONFIGS``）。

    Returns:
        list[str]: 配置文件名列表（不含 ``.json`` 后缀），按名称排序；
            目录不存在时返回空列表。
    """

    if not config_dir.is_dir():
        return []

    return sorted(path.stem for path in config_dir.glob("*.json") if path.is_file())


def apply_managed_config(
    user_config_path: Path,
    software_config_path: Path | None,
    runtime_values: dict[str, Any] | None = None,
) -> ManagedConfigBackup:
    """写入托管项并返回恢复所需的快照。

    Args:
        user_config_path: BAAH 用户配置文件路径。
        software_config_path: BAAH 软件配置文件路径，None 表示不托管软件配置。
        runtime_values: 本次运行才确定的托管项，会覆盖同名静态托管项，
            例如模拟器调度解析出的 ADB 地址。

    Returns:
        ManagedConfigBackup: 运行结束后交回 ``restore_managed_config`` 的快照。

    Raises:
        Exception: 写入任一配置文件失败。抛出前已把两份配置回滚到调用前的状态。
    """

    backup = ManagedConfigBackup(user_config_path=user_config_path)

    ## 先把两份配置全部读完再开始写：读取阶段不改动任何文件，中途失败也就不会
    ## 留下「用户配置已改、软件配置没改」的半托管状态
    user_config = read_json(user_config_path)
    backup.user_config_existed = user_config_path.exists()
    backup.user_config = dict(user_config)

    software_config: dict[str, Any] = {}
    if software_config_path is not None:
        software_config = read_json(software_config_path)
        backup.software_config_path = software_config_path
        backup.software_config_existed = software_config_path.exists()
        backup.software_config = dict(software_config)

    managed_values = dict(MANAGED_USER_VALUES)
    if runtime_values:
        managed_values.update(runtime_values)

    user_changed = False
    for key, value in managed_values.items():
        if user_config.get(key) != value:
            user_config[key] = value
            user_changed = True

    software_changed = False
    if software_config_path is not None:
        for key, value in MANAGED_SOFTWARE_VALUES.items():
            if software_config.get(key) != value:
                software_config[key] = value
                software_changed = True

    ## 两份配置要么都写好、要么都不写：任一写入失败就立刻回滚已经落盘的那份。
    ## 调用方拿到异常时不会有备份对象，等到收尾阶段也就无从恢复，只能靠这里兜住
    try:
        if user_changed:
            write_json(user_config_path, user_config)
            logger.info(f"已写入 BAAH 托管配置项: {user_config_path}")

        if software_changed and software_config_path is not None:
            write_json(software_config_path, software_config)
            logger.info(f"已写入 BAAH 托管软件配置项: {software_config_path}")
    except Exception as e:
        logger.opt(exception=True).warning(f"写入 BAAH 托管配置失败, 正在回滚: {e}")
        _restore_files(backup)
        raise

    ## applied 表示「确实改动过文件」：两份都没变时收尾阶段无需恢复
    backup.applied = user_changed or software_changed
    return backup


def _restore_files(backup: ManagedConfigBackup) -> list[str]:
    """把两份配置恢复为备份内容。

    每步独立容错：失败只记录日志并汇总，不向调用方抛出，避免影响任务收尾。
    写入阶段回滚与收尾阶段恢复共用这一份逻辑。

    Args:
        backup: 托管前的快照。

    Returns:
        list[str]: 恢复失败的描述，空列表表示全部恢复成功。
    """

    failures: list[str] = []

    try:
        if backup.user_config_existed:
            write_json(backup.user_config_path, backup.user_config)
        elif backup.user_config_path.exists():
            ## 配置文件是本次运行期间新建的，恢复阶段删除
            backup.user_config_path.unlink()
    except Exception as e:
        logger.opt(exception=True).warning(f"恢复 BAAH 用户配置失败: {e}")
        failures.append(f"用户配置 {backup.user_config_path.name}({e})")

    software_config_path = backup.software_config_path
    if software_config_path is not None:
        try:
            if backup.software_config_existed:
                write_json(software_config_path, backup.software_config)
            elif software_config_path.exists():
                software_config_path.unlink()
        except Exception as e:
            logger.opt(exception=True).warning(f"恢复 BAAH 软件配置失败: {e}")
            failures.append(f"软件配置 {software_config_path.name}({e})")

    return failures


def restore_managed_config(backup: ManagedConfigBackup | None) -> list[str]:
    """把托管项恢复为运行前的取值。

    每步独立容错：恢复失败只记录日志，不向调用方抛出，避免影响任务收尾。
    快照为 None 表示本次运行尚未写入过托管项（任务在托管前就被停止），直接返回。
    但失败必须让调用方看得见——静默返回会让用户的配置一直带着托管值，
    而任务却显示为正常完成。

    Args:
        backup: ``apply_managed_config`` 返回的快照，允许为 None。

    Returns:
        list[str]: 恢复失败的描述，空列表表示全部恢复成功。
    """

    if backup is None or not backup.applied:
        return []

    return _restore_files(backup)


def latest_log_file(log_dir: Path, not_before: float) -> Path | None:
    """返回日志目录内不早于指定时间的最新 BAAH 日志文件。

    BAAH 每次运行都会新建 ``log_<时间戳>.txt``，因此按启动时刻过滤即可锁定本次日志。

    Args:
        log_dir: BAAH 日志目录。
        not_before: 起始时间戳（``time.time()`` 语义），早于它的日志文件会被忽略。

    Returns:
        Path | None: 本次运行的日志文件路径，未产生时为 None。
    """

    if not log_dir.is_dir():
        return None

    try:
        candidates = [
            path
            for path in log_dir.glob("log_*.txt")
            if path.stat().st_mtime >= not_before
        ]
    except OSError as e:
        logger.warning(f"扫描 BAAH 日志目录失败: {e}")
        return None

    if not candidates:
        return None

    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_log_time_range(log_path: Path, time_format: str) -> tuple[int, int] | None:
    """按日志首行的实际排版推算时间戳的字符切片区间。

    BAAH 的行格式是「{版本} - {分:秒} - {级别} : {消息}」，例如
    ``2.4.13 - 24:19 - INFO : 执行任务EnterGame``。版本号的位数会随版本变化
    （``2.4.13`` 是 6 位，``2.4.100`` 是 7 位），所以区间**不能写死**：写死的
    区间一旦对不上，``LogMonitor`` 会把每一行都判为解析失败并静默丢弃，
    表现成「日志文件找到了却一行都采集不到」，最终每次都判任务失败。

    做法是按首行第一个 `` - `` 的位置定位，这正是版本号与时间戳之间的分隔符。

    Args:
        log_path: 本次运行的日志文件路径。
        time_format: 时间戳格式，用于推算区间长度（``%M:%S`` 为 5 个字符）。

    Returns:
        tuple[int, int] | None: ``(start, end)`` 切片区间；首行读不到或不含
        分隔符时返回 None。
    """

    try:
        with log_path.open("r", encoding="utf-8-sig", errors="replace") as f:
            first_line = ""
            for raw in f:
                if raw.strip():
                    first_line = raw.rstrip("\r\n")
                    break
    except OSError as e:
        logger.warning(f"读取 BAAH 日志首行失败: {log_path} ({e})")
        return None

    if not first_line:
        return None

    separator_at = first_line.find(" - ")
    if separator_at < 0:
        logger.warning(f"BAAH 日志首行没有分隔符, 无法定位时间戳: {first_line[:80]}")
        return None

    start = separator_at + len(" - ")
    ## 长度按格式自身推算，避免把 MM:SS 的 5 个字符写死在这里
    length = len(datetime.now().strftime(time_format))
    return (start, start + length)
