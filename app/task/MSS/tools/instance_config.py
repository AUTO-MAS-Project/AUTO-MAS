#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MSS 根目录下的路径解析与实例配置读写。

MAS 从 MSS 外壳的目录里读两样东西：当前激活的实例 ID，和外壳按天写的日志文件。
实例配置本身（``config/instances/<实例ID>.json``）平时归外壳管——用户在外壳里配好
任务与选项，MAS 不碰；只有「计划表与活动编排」会读它、按规则改 ``CurrentTasks``
与三个选项再写回，跑完恢复原样（规则见 ``orchestrate``，理由见那里的模块说明）。

已实测的契约（样本：``D:\\jiao_ben\\maa\\mss``）：

- 实例 ID 取自 ``<根>/appsettings.json`` 的 ``Instances.List``（样本为 ``default``）；
- 日志在 ``<根>/logs/log-YYYYMMDD.log``。常规路径由 AutoProxy 按日期直接算出，
  这里的 :func:`latest_log_file` 只作日期路径还没出现时的兜底。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.utils.io import read_dict_file, read_file, write_file

## 外壳可执行文件与 PI V2 清单名（都在 MSS 根目录下）
EXE_NAME = "MFAAvalonia.exe"
INTERFACE_NAME = "interface.json"
## 外壳全局设置（实例列表与当前激活实例在这里）
APP_SETTINGS_NAME = "appsettings.json"
## 实例配置目录与日志目录（相对 MSS 根目录）
INSTANCE_DIR_RELATIVE = ("config", "instances")
LOG_DIR_NAME = "logs"
## instance id 读不到时的回退值，也是 MSS 发行包的默认实例
DEFAULT_INSTANCE_ID = "default"
## 实例配置文件名后缀
INSTANCE_SUFFIX = ".json"
## MAS 自己维护的实例：编排写进这一份，用户自己的实例一个字节都不动
MAS_INSTANCE_ID = "auto-mas"
MAS_INSTANCE_NAME = "AUTO-MAS"
## 外壳全局设置里与实例有关的键；前两个是逗号分隔的实例 ID 列表（实测样本
## "default,936fa0a9"），后两个决定外壳打开时激活哪个
INSTANCES_LIST_KEY = "Instances.List"
INSTANCES_ORDER_KEY = "Instances.Order"
INSTANCES_ACTIVE_KEY = "Instances.LastActive"
INSTANCES_ACTIVE_NAME_KEY = "Instances.LastActiveName"


def resolve_instance_dir(root: Path) -> Path:
    """返回 MSS 实例配置目录（``<根>/config/instances``）。

    Args:
        root: MSS 根目录（含 MFAAvalonia.exe 与 interface.json）。

    Returns:
        Path: 实例配置目录路径，不保证存在。
    """

    return root.joinpath(*INSTANCE_DIR_RELATIVE)


def resolve_instance_id(root: Path) -> str:
    """读 ``<根>/appsettings.json`` 的 ``Instances.List`` 得到当前激活实例 ID。

    外壳可以纳管多个实例，MAS 只驱动当前激活的那一个：``Instances.List`` 是
    实例 ID 列表，取第一个；读不到时回退 ``default``（发行包的默认实例）。

    Args:
        root: MSS 根目录。

    Returns:
        str: 实例 ID。
    """

    settings = read_file(root / APP_SETTINGS_NAME)
    if isinstance(settings, dict):
        raw = str(settings.get("Instances.List") or "").strip()
        ## 分隔符未在实测样本中出现（本机只有 default），按常见几种切开取首个非空段
        for token in raw.replace("|", ",").replace(";", ",").split(","):
            instance_id = token.strip()
            if instance_id and instance_id not in {".", ".."}:
                return instance_id
    return DEFAULT_INSTANCE_ID


def resolve_instance_path(root: Path, instance_id: str | None = None) -> Path:
    """返回实例配置文件路径。

    Args:
        root: MSS 根目录。
        instance_id: 实例 ID；省略时按 appsettings.json 解析。

    Returns:
        Path: ``<根>/config/instances/<实例ID>.json``。
    """

    return resolve_instance_dir(root) / (
        f"{instance_id or resolve_instance_id(root)}{INSTANCE_SUFFIX}"
    )


def read_instance_config(path: Path) -> dict[str, Any]:
    """读外壳实例配置。

    Args:
        path: 实例配置文件路径。

    Returns:
        dict[str, Any]: 配置内容；文件不存在时为空字典。

    Raises:
        ConfigCorruptedError: 文件在，但解析不了或根节点不是映射。
    """

    return read_dict_file(path)


def write_instance_config(path: Path, config: Mapping[str, Any]) -> None:
    """原子写回外壳实例配置。

    外壳只在启动时读一次配置，所以「启动前写」就够了。

    Args:
        path: 实例配置文件路径。
        config: 要写入的完整配置。
    """

    write_file(path, dict(config))


def read_app_settings(root: Path) -> dict[str, Any]:
    """读外壳全局设置 ``appsettings.json``。

    Args:
        root: MSS 根目录。

    Returns:
        dict[str, Any]: 设置内容；读不到或不是映射时为空字典。
    """

    settings = read_file(root / APP_SETTINGS_NAME)
    return dict(settings) if isinstance(settings, Mapping) else {}


def split_instance_ids(raw: object) -> list[str]:
    """拆开外壳的实例 ID 列表。

    实测分隔符是英文逗号（样本 ``"default,936fa0a9"``）。

    Args:
        raw: 设置里读出来的原始值。

    Returns:
        list[str]: 去空白后的实例 ID 列表。
    """

    return [token.strip() for token in str(raw or "").split(",") if token.strip()]


def resolve_active_instance_id(root: Path) -> str:
    """用户在外壳里当前激活的实例 ID。

    它就是 MAS 实例时（MAS 会把激活实例指过去）退回列表里第一个非 MAS 实例，
    免得拿 MAS 自己生成的配置当模板。

    Args:
        root: MSS 根目录。

    Returns:
        str: 实例 ID；都取不到时回退 :data:`DEFAULT_INSTANCE_ID`。
    """

    settings = read_app_settings(root)
    active = str(settings.get(INSTANCES_ACTIVE_KEY) or "").strip()
    if active and active != MAS_INSTANCE_ID:
        return active

    for instance_id in split_instance_ids(settings.get(INSTANCES_LIST_KEY)):
        if instance_id != MAS_INSTANCE_ID:
            return instance_id
    return DEFAULT_INSTANCE_ID


def register_mas_instance(root: Path) -> Path:
    """把 MAS 实例挂进外壳的实例列表，并让它成为外壳打开时激活的那个。

    外壳按 ``Instances.List`` 显示实例、按 ``Instances.LastActive`` 决定打开哪个；
    两者都指到 MAS 实例，用户在外壳里看到的就是 MAS 实际会跑的那份任务。

    Args:
        root: MSS 根目录。

    Returns:
        Path: ``appsettings.json`` 路径。
    """

    path = root / APP_SETTINGS_NAME
    settings = read_app_settings(root)

    for key in (INSTANCES_LIST_KEY, INSTANCES_ORDER_KEY):
        ids = split_instance_ids(settings.get(key))
        if MAS_INSTANCE_ID not in ids:
            ids.append(MAS_INSTANCE_ID)
        settings[key] = ",".join(ids)

    settings[INSTANCES_ACTIVE_KEY] = MAS_INSTANCE_ID
    settings[INSTANCES_ACTIVE_NAME_KEY] = MAS_INSTANCE_NAME
    write_file(path, settings)
    return path


def resolve_temp_dir(script_id: str) -> Path:
    """返回 MAS 存放注入快照的目录。

    与 MAA / M9A 同一个约定（``data/<脚本ID>/Temp``）：编排前的 ``config/instances``
    会整目录快照到这里，崩溃时下次运行自动恢复，正常跑完由调度器清掉。
    快照放在 MAS 自己的数据目录里，不往外壳目录里丢额外文件。

    Args:
        script_id: 脚本 ID。

    Returns:
        Path: 快照目录路径，不保证存在。
    """

    return Path.cwd() / "data" / script_id / "Temp"


def latest_log_file(log_dir: Path, since: float) -> Path | None:
    """在日志目录里找 ``since`` 之后被写过的最新日志文件。

    外壳按天写 ``log-YYYYMMDD.log``，常规路径由日期直接算出（见 AutoProxy 的
    按日滚动解析）；本函数只作兜底，用于日期路径还没出现时的等待窗口。

    Args:
        log_dir: 日志目录。
        since: 起始时间戳（``time.time()`` 口径）。

    Returns:
        Path | None: 最新的日志文件；没有符合条件时返回 None。
    """

    if not log_dir.is_dir():
        return None

    candidates = [
        path
        for path in log_dir.glob("log-*.log")
        if path.is_file() and path.stat().st_mtime >= since
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
