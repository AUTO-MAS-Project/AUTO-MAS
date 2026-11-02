#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 配置定位与跨脚本占用校验；配置操作能力由宿主注入。"""

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from app.config import ConfigCollection, ConfigEntry
from app.models.config import ZzzOdConfig, ZzzOdUserConfig


class ZzzOdConfigGateway(Protocol):
    """宿主提供配置能力，专项持有业务流程。"""

    ScriptConfig: ConfigCollection[ConfigEntry]

    async def flush(self) -> None: ...

    async def add_user(self, script_id: str) -> tuple[uuid.UUID, ConfigEntry]: ...


class ZzzOdContext:
    """共享配置集合，通过注入能力完成通用配置操作。"""

    def __init__(
        self,
        scripts: ConfigCollection[ConfigEntry],
        *,
        flush: Callable[[], Awaitable[None]],
        add_user: Callable[[str], Awaitable[tuple[uuid.UUID, ConfigEntry]]],
    ) -> None:
        self.scripts = scripts
        self.flush = flush
        self.add_user = add_user

    def script_config(self, script_id: str) -> ZzzOdConfig:
        """解析 ZZZ-OD 脚本配置并拒绝跨类型 ID 访问。"""

        script_config = self.scripts[uuid.UUID(script_id)]
        if not isinstance(script_config, ZzzOdConfig):
            raise TypeError("脚本配置类型错误, 不是 ZZZ-OD 类型")
        return script_config

    def root(self, script_config: ZzzOdConfig) -> Path:
        """返回 zzz-od 安装根目录并按哨兵文件校验有效。

        三层防线（与路径字段声明、自动发现/check() 同一组哨兵）：
        1. 拒绝未配置路径——``Path("").is_dir()``
           在 cwd 下为真，independent 来源保存会把 ``config/01/`` 建进 MAS 工作目录；
        2. 拒绝非绝对路径 / 不存在的目录 / ``Path.cwd()``；
        3. ``validate_install`` 安装哨兵（``src`` 目录）——任意随机目录
           （如 D:\\）只要 is_dir 就放行会在其下建出 config/01。不要求
           ``config/one_dragon.yml``：它由一条龙首次运行生成，全新安装
           尚未初始化时不应卡住启动器下拉/实例列表/任务目录等发现能力
           （读写路径自身会按需初始化；完整初始化校验用 validate_root）。
        """

        raw = str(script_config.Info.RootPath or "").strip()
        if not raw:
            raise ValueError("请先在脚本设置中配置绝区零一条龙安装目录")
        root = Path(raw).expanduser()
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("请先在脚本设置中配置绝区零一条龙安装目录")
        resolved = root.resolve()
        if resolved == Path.cwd().resolve():
            raise ValueError("绝区零一条龙安装目录不能为 MAS 工作目录")

        from app.task.ZzzOd.tools import validate_install

        validate_install(resolved)
        return resolved

    def ensure_install_unlocked(self, root: Path) -> None:
        """任一指向同一安装的 ZzzOd 脚本正在运行时拒绝槽级写操作。

        槽目录跨脚本共享同一份安装目录：另一脚本运行中时，其用户的绑定号
        可能尚未持久化（首次分配的 SlotIdx 还在等待异步落盘），
        持久配置里的占用判定读不到——此时清理/恢复会误动在跑用户的槽。

        Raises:
            RuntimeError: 有同安装的 ZzzOd 脚本处于运行中。
        """

        from app.utils.common.config import archive as _utils_config_archive

        key = _utils_config_archive.config_root_key(root)
        for script_config in self.scripts.values():
            if (
                not isinstance(script_config, ZzzOdConfig)
                or not script_config.is_locked
            ):
                continue
            script_root = str(script_config.Info.RootPath or "").strip()
            if (
                script_root
                and _utils_config_archive.config_root_key(script_root) == key
            ):
                raise RuntimeError("有正在运行的绝区零一条龙脚本, 请结束后再试")

    def user(
        self, script_id: str, user_id: str
    ) -> tuple[ZzzOdConfig, Path, ZzzOdUserConfig, uuid.UUID]:
        """解析 ZZZ-OD 脚本/安装目录/用户配置对象，拒绝无效 ID。"""

        script_config = self.script_config(script_id)
        root = self.root(script_config)
        uid = uuid.UUID(user_id)
        if uid not in script_config.UserData:
            raise ValueError("用户不存在")
        return script_config, root, script_config.UserData[uid], uid

    def slot_occupant(
        self,
        root: Path,
        script_id: str,
        user_uid: uuid.UUID | None,
        slot: int,
        *,
        exclude_same_script: bool = False,
    ) -> str | None:
        """判定目标实例槽当前被谁占用（返回可读描述；空闲/仅本用户时 None）。

        占用者可能是：指向同一份安装的其他 ZzzOd 脚本/同脚本其他用户（按
        ``Info.SlotIdx`` 绑定）或一条龙原生实例（按原生注册表）。绑定只算
        指向本安装的脚本——槽目录按安装目录隔离，别的安装的同号槽互不相干。
        注册表源走原生原件（合成视图在盘时读 sidecar），与备份口径一致。
        仅本用户绑定或槽目录虽在但无人认领（孤儿槽）视为空闲——孤儿槽可被
        恢复重新认领。``user_uid=None`` 表示不排除任何用户（回收池恢复这类
        没有用户上下文的场景：任何绑定都算占用）。

        ``exclude_same_script=True``：忽略本脚本内用户的绑定占用（仅剩其他
        脚本与原生实例算占用）——删脚本时整个脚本都在移除，同脚本用户间的
        相互占用不该挡住回收（否则共享同一槽的两个用户会互相把对方当占用、
        双双跳过，槽与备份池残留）。
        """

        from app.task.ZzzOd.tools import read_native_registry
        from app.utils.common.config import archive as _utils_config_archive

        # 1) 其他 ZzzOd 用户（含其他脚本）按 SlotIdx 绑定占用
        key = _utils_config_archive.config_root_key(root)
        for script_uid, script_config in self.scripts.items():
            if not isinstance(script_config, ZzzOdConfig):
                continue
            if exclude_same_script and str(script_uid) == script_id:
                continue
            script_root = str(script_config.Info.RootPath or "").strip()
            if (
                not script_root
                or _utils_config_archive.config_root_key(script_root) != key
            ):
                continue
            script_name = str(script_config.Info.Name or "未知脚本")
            for other_uid, cfg in script_config.UserData.items():
                if other_uid == user_uid:
                    continue
                if int(cfg.Info.SlotIdx or -1) == slot:
                    user_name = str(cfg.Info.Name or "未知用户")
                    return f"脚本「{script_name}」的用户「{user_name}」"

        # 2) 一条龙原生实例（按原生注册表）
        data = read_native_registry(root)
        for item in data.get("instance_list") or []:
            if not isinstance(item, dict):
                continue
            if int(item.get("idx", -1)) == slot:
                return str(item.get("name") or f"原生实例 {slot:02d}")
        return None

    def native_instance(self, script_id: str, instance_idx: int) -> tuple[Path, dict]:
        """解析 zzz-od 安装根目录与原生实例，校验实例存在（直控编辑目标）。"""

        script_config = self.script_config(script_id)
        root = self.root(script_config)

        from app.task.ZzzOd.tools import list_instances

        instance = next(
            (
                item
                for item in list_instances(root)
                if int(item.get("idx", -1)) == int(instance_idx)
            ),
            None,
        )
        if instance is None:
            raise ValueError(f"实例 {int(instance_idx):02d} 不存在")
        return root, instance
