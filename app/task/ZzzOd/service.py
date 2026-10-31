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

"""ZZZ-OD 实例、槽位与编辑业务；HTTP 层只负责契约映射。"""

import asyncio
from pathlib import Path
from typing import Any

from app.utils.common.log import logger as _utils_logger

from .config_context import ZzzOdContext
from .recovery import ZzzOdRecovery

logger = _utils_logger.get_logger("配置管理")


def read_task_catalog(root: Path) -> list[dict[str, Any]]:
    """读取任务目录并补齐专项支持的配置与跳转能力。"""
    from .tools import get_task_app_fields, get_task_app_jump, list_app_catalog

    return [
        {
            **item,
            "configurable": get_task_app_fields(str(item["app_id"])) is not None,
            "jump": get_task_app_jump(str(item["app_id"])),
        }
        for item in list_app_catalog(root)
    ]


class ZzzOdService:
    def __init__(self, context: ZzzOdContext) -> None:
        self.context = context
        self.recovery = ZzzOdRecovery(context)

    def get_root(self, script_id: str) -> Path:
        """zzz-od 安装根目录（哨兵校验后返回；供 API 层统一复用）。"""

        return self.context.root(self.context.script_config(script_id))

    def get_instances(self, script_id: str) -> list[dict]:
        """列出 zzz-od 实例（供用户配置「快速导入」选择来源实例）。"""

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)
        from app.task.ZzzOd.tools import list_instances

        return [
            {
                "idx": int(item.get("idx", 0)),
                "name": str(item.get("name", "")),
                "active": bool(item.get("active")),
                "active_in_od": bool(item.get("active_in_od")),
                "force_login_before_run": bool(item.get("force_login_before_run")),
            }
            for item in list_instances(root)
        ]

    def add_instance(self, script_id: str, name: str) -> list[dict]:
        """直控：新建一条龙实例（最小空闲槽避开原生与本安装的 MAS 绑定槽）。

        变更注册表与实例目录前先归档原生配置（指纹去重），保证可恢复。
        """

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.slots import collect_used_slot_idxs
        from app.task.ZzzOd.tools import add_instance

        self.ensure_direct_backup(script_id)
        idx = add_instance(
            root, name, collect_used_slot_idxs(root, scripts=self.context.scripts)
        )
        logger.info(f"ZZZ-OD 原生来源新建实例: 槽 {idx:02d} (名称 {name})")
        return self.get_instances(script_id)

    def rename_instance(
        self, script_id: str, instance_idx: int, name: str
    ) -> list[dict]:
        """直控：重命名实例（只改注册表 name，实例目录不变）。"""

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.tools import rename_instance

        self.ensure_direct_backup(script_id)
        rename_instance(root, instance_idx, name)
        logger.info(f"ZZZ-OD 原生来源重命名实例: {instance_idx:02d} → {name}")
        return self.get_instances(script_id)

    def set_instance_active_in_od(
        self, script_id: str, instance_idx: int, value: bool
    ) -> list[dict]:
        """直控：切换实例是否参与「全部实例」运行模式（active_in_od）。"""

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.tools import set_instance_active_in_od

        self.ensure_direct_backup(script_id)
        set_instance_active_in_od(root, instance_idx, value)
        logger.info(f"ZZZ-OD 直控实例 {instance_idx:02d} 参与全部实例 → {bool(value)}")
        return self.get_instances(script_id)

    def set_instance_active(self, script_id: str, instance_idx: int) -> list[dict]:
        """直控：把所选实例设为当前活跃（「仅运行当前」运行的就是它）。"""

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.tools import set_active_instance

        self.ensure_direct_backup(script_id)
        set_active_instance(root, instance_idx)
        logger.info(f"ZZZ-OD 直控实例 {instance_idx:02d} 已设为当前活跃")
        return self.get_instances(script_id)

    def set_instance_run_mode(self, script_id: str, instance_run: str) -> None:
        """直控：设置运行实例（one_dragon.yml 全局 instance_run，白名单校验）。

        运行实例是脚本级全局设置，与直控页当前编辑哪个实例无关。
        """

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.tools import save_native_instance_run

        self.ensure_direct_backup(script_id)
        save_native_instance_run(root, instance_run)
        logger.info(f"ZZZ-OD 原生来源运行实例 → {instance_run}")

    def set_instance_force_login(
        self, script_id: str, instance_idx: int, value: bool
    ) -> list[dict]:
        """直控：切换实例「运行前切换账号」（映射一条龙原生能力，MAS 不干涉）。"""

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.tools import set_instance_force_login

        self.ensure_direct_backup(script_id)
        set_instance_force_login(root, instance_idx, value)
        logger.info(
            f"ZZZ-OD 直控实例 {instance_idx:02d} 运行前切换账号 → {bool(value)}"
        )
        return self.get_instances(script_id)

    def delete_instance(self, script_id: str, instance_idx: int) -> list[dict]:
        """直控：删除实例（注册表 + 实例目录；MAS 绑定槽与最后实例受保护）。"""

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.slots import collect_used_slot_idxs
        from app.task.ZzzOd.tools import remove_instance

        self.ensure_direct_backup(script_id)
        remove_instance(
            root,
            instance_idx,
            protected_idxs=collect_used_slot_idxs(root, scripts=self.context.scripts),
        )
        logger.info(f"ZZZ-OD 直控删除实例: {instance_idx:02d}")
        return self.get_instances(script_id)

    async def get_slots(self, script_id: str) -> list[dict]:
        """实例槽总览：原生实例 / MAS 绑定槽 / 无主残留（含未落盘的绑定）。

        槽目录是 MAS 分配在一条龙安装目录里的，注册表里没有它、GUI 看不见，
        「槽目录数为什么和用户数对不上」只能靠这份对照表看清：``kind`` 与
        ``has_dir`` 一起看——绑定但没跑过的用户是「mas 且无目录」。

        Raises:
            ConfigCorruptedError: 一条龙注册表不可读（原生名单缺失，不能把
                原生实例误标成无主残留）。
        """

        from app.task.ZzzOd.slots import collect_slot_owners
        from app.task.ZzzOd.tools import list_slot_overview

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)
        owners = collect_slot_owners(root, scripts=self.context.scripts)
        # 槽总览要 rglob 统计各槽目录占用，是阻塞 IO，放线程里跑
        return await asyncio.to_thread(list_slot_overview, root, owners)

    async def clean_slots(self, script_id: str) -> list[int]:
        """手动清理该安装下无人绑定的实例槽，返回实际回收的槽号。

        与运行/会话前的自动回收同源（先归档进回收池再删目录；原生实例与
        被任一 ZzzOd 用户绑定的槽不动），但范围更宽、且失败会抛出：手动清理
        不受「只收归属用户已不存在的号」的台账限制（来路不明的残留正是用户要清的
        对象），注册表缺失/损坏也直接报错，界面才能说明「为什么没清」。
        原生来源用户显式发起即可，不受「原生来源零写入」约束——那条约束管的是 MAS
        在运行期间自行写安装目录。

        Raises:
            RuntimeError: 有同安装的 ZzzOd 脚本正在运行（在跑用户的绑定号
                可能未持久化，清理会误收其槽）。
            ValueError: 一条龙注册表不存在或不可读（无从判定无主槽）。
        """

        from app.task.ZzzOd.slots import recycle_unbound_slots

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)
        self.context.ensure_install_unlocked(root)
        # 归档 + 删目录是阻塞 IO，放线程里跑
        return await asyncio.to_thread(
            recycle_unbound_slots,
            root,
            scripts=self.context.scripts,
            only_allocated=False,
            swallow=False,
        )

    async def get_recycle(self, script_id: str) -> list[dict]:
        """回收池条目（被删用户/脚本留下的槽内容与该槽 MAS 备份池快照）。"""

        from app.task.ZzzOd.tools import list_recycle_entries

        script_config = self.context.script_config(script_id)
        return await asyncio.to_thread(
            list_recycle_entries, self.context.root(script_config)
        )

    async def clear_recycle(self, script_id: str) -> int:
        """清空本安装的回收池，返回删除的条目数。

        只删 recycle 池（被删用户/脚本留下的存底）；``onedragon`` 原生池与
        mas 配置恢复池在别的子树，不受影响。

        Raises:
            RuntimeError: 有同安装的 ZzzOd 脚本正在运行——运行路径会向回收池
                归档存底（注入前回收、撞号存底），并发清空会互相踩。
        """

        from app.task.ZzzOd.tools import clear_recycle_pool

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)
        self.context.ensure_install_unlocked(root)
        # 删池是阻塞 IO，放线程里跑
        return await asyncio.to_thread(clear_recycle_pool, root)

    async def get_app_config(
        self,
        script_id: str,
        user_id: str,
        app_id: str,
        instance_idx: int | None = None,
    ) -> dict:
        """任务级配置（字段元数据 + 当前值）。

        instance_idx 给定时（原生来源模式）读取该原生实例的 per-app YAML；
        否则读取用户绑定槽（未分配槽时取元数据默认值）。
        """

        from app.task.ZzzOd.tools import (
            get_task_app_fields,
            instance_dir,
            read_app_config,
            resolve_field_options,
        )

        fields_meta = get_task_app_fields(app_id)
        if fields_meta is None:
            raise ValueError(f"任务 {app_id} 不支持在 MAS 侧配置")

        if instance_idx is not None:
            root, _ = self.context.native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            _, root, user_cfg, _ = self.context.user(script_id, user_id)
            slot = int(user_cfg.Info.SlotIdx or -1)
        current = read_app_config(root, slot, app_id) if slot > 0 else {}
        # 预备编队等选项随槽而异（team.yml 在实例目录），无槽时无动态选项
        config_dir = instance_dir(root, slot) if slot > 0 else None

        def _show_when_out(sw: dict | list | None) -> dict:
            """show_when 透传：单条件 dict 或条件列表（{field, value, not?}）。"""

            if not sw:
                return {}
            conds = sw if isinstance(sw, list) else [sw]
            return {
                "showWhen": [
                    {
                        "field": str(c["field"]),
                        "value": str(c["value"]),
                        **({"not": True} if c.get("not") else {}),
                    }
                    for c in conds
                ]
            }

        fields = []
        for meta in fields_meta:
            ftype = str(meta.get("type") or "select")
            field_out: dict = {
                "field": str(meta["field"]),
                "title": str(meta["title"]),
                "type": ftype,
            }
            if ftype == "plan_list":
                # 计划列表：当前值整表返回；列元数据内联（动态列选项服务端解析），
                # 级联列选项由前端从任务选项端点的训练副本树取
                value = current.get(meta["field"])
                field_out["value"] = value if isinstance(value, list) else []
                field_out["options"] = []
                field_out["columns"] = [
                    {
                        "field": str(c["field"]),
                        "title": str(c["title"]),
                        "type": str(c.get("type") or "select"),
                        "options": [
                            {"label": str(o["label"]), "value": str(o["value"])}
                            for o in resolve_field_options(root, c, config_dir)
                        ],
                        **_show_when_out(c.get("show_when")),
                    }
                    for c in meta.get("columns") or []
                ]
                field_out["newItem"] = dict(meta.get("new_item") or {})
            else:
                options = resolve_field_options(root, meta, config_dir)
                default = meta.get("default")
                if default is None and options:
                    default = str(options[0]["value"])
                value = current.get(meta["field"], default)
                if ftype == "bool":
                    value = bool(value)
                elif ftype == "number":
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        value = int(default or 0)
                else:
                    # select / team：展示为字符串（team 与选项 value 同型，保存转 int）
                    value = None if value is None else str(value)
                field_out["value"] = value
                field_out["options"] = [
                    {"label": str(o["label"]), "value": str(o["value"])}
                    for o in options
                ]
            fields.append(field_out)
        return {"appId": app_id, "fields": fields}

    async def save_app_config(
        self,
        script_id: str,
        user_id: str,
        app_id: str,
        values: dict,
        instance_idx: int | None = None,
    ) -> dict:
        """保存任务级配置到目标位置（字段白名单校验后写入）。

        instance_idx 给定时（原生来源模式）直接写该原生实例的 per-app YAML；
        否则写用户绑定槽（首次编辑会自动分配绑定槽）。值按字段类型转换
        （select→str / bool→bool / number→int），plan_list 整表合并写入并
        按 plan_id 保留既有 run_times。
        """

        from app.task.ZzzOd.tools import (
            get_task_app_fields,
            merge_plan_list,
            read_app_config,
            write_app_config,
        )

        fields_meta = get_task_app_fields(app_id)
        if fields_meta is None:
            raise ValueError(f"任务 {app_id} 不支持在 MAS 侧配置")
        meta_by_field = {str(m["field"]): m for m in fields_meta}
        unknown = {str(k) for k in values} - set(meta_by_field)
        if unknown:
            raise ValueError(f"不支持的配置字段: {', '.join(sorted(unknown))}")

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        if instance_idx is not None:
            self.context.native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            from app.task.ZzzOd.slots import (
                collect_used_slot_idxs,
                ensure_user_slot,
            )

            _, _, user_cfg, uid = self.context.user(script_id, user_id)
            used = collect_used_slot_idxs(
                root, exclude_uids={uid}, scripts=self.context.scripts
            )
            slot = await ensure_user_slot(
                root, user_cfg, used, script_id=script_id, owner_uid=str(uid)
            )

        current = read_app_config(root, slot, app_id) if slot > 0 else {}
        patch: dict = {}
        for key, raw in values.items():
            meta = meta_by_field[str(key)]
            ftype = str(meta.get("type") or "select")
            if ftype == "plan_list":
                columns = meta.get("columns") or []
                existing = current.get(str(key))
                patch[str(key)] = merge_plan_list(
                    columns,
                    dict(meta.get("new_item") or {}),
                    existing if isinstance(existing, list) else [],
                    raw if isinstance(raw, list) else [],
                )
            elif ftype == "bool":
                patch[str(key)] = bool(raw)
            elif ftype == "number":
                patch[str(key)] = int(raw)
            elif ftype == "team":
                # 预备编队下标：上游按 int 消费（-1=游戏内配队），下拉提交字符串
                try:
                    patch[str(key)] = int(raw)
                except (TypeError, ValueError):
                    patch[str(key)] = -1
            else:
                # select：按声明选项的原始类型还原——GET 侧选项 value 已被
                # str() 抹平，前端回传字符串；选项声明为 int 的字段（周挑战
                # 起始日）落盘必须是 int，否则上游 `>=` 比较抛 TypeError
                raw_str = str(raw)
                matched = next(
                    (
                        o.get("value")
                        for o in meta.get("options") or []
                        if str(o.get("value")) == raw_str
                    ),
                    None,
                )
                if isinstance(matched, int) and not isinstance(matched, bool):
                    patch[str(key)] = matched
                else:
                    patch[str(key)] = raw_str

        config = write_app_config(root, slot, app_id, patch)
        if instance_idx is not None:
            logger.info(
                f"ZZZ-OD 实例 {slot:02d} 任务 {app_id} 配置已由直控页面保存: {values}"
            )
        else:
            logger.info(
                f"ZZZ-OD 用户 {user_id} 任务 {app_id} 配置已保存到槽 {slot:02d}: {values}"
            )
        return config

    async def get_task_options(self, script_id: str, app_id: str) -> dict:
        """任务计划的动态选项（副本级联树 / 配队方案 / 挑战配置等）。

        全部从安装目录静态读取（compendium_data.yml + 配置目录扫描），
        与一条龙原生 GUI 选项同源，上游升级后无需改 MAS。
        """

        from app.task.ZzzOd.tools import (
            auto_battle_options,
            get_task_app_fields,
            lost_void_challenge_options,
            lost_void_missions,
            train_categories,
        )

        if get_task_app_fields(app_id) is None:
            raise ValueError(f"任务 {app_id} 不支持在 MAS 侧配置")

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)
        return {
            "appId": app_id,
            "trainCategories": train_categories(root),
            "lostVoidMissions": lost_void_missions(root),
            "autoBattle": auto_battle_options(root),
            "challenge": lost_void_challenge_options(root),
        }

    async def get_teams(
        self, script_id: str, user_id: str, instance_idx: int | None = None
    ) -> dict:
        """预备编队完整列表（固定 20 个，与一条龙原生编队页一致）。

        team.yml：名称 + 绑定配队方案 + 成员（agent_id → 代理人下拉可选）。
        缺失项按上游规则补「编队N」默认编队。
        instance_idx 给定时（原生来源模式）读该原生实例；否则读用户绑定槽。
        附带配队方案与代理人选项（静态数据，不含识别能力）供前端渲染。
        """

        from app.task.ZzzOd.tools import (
            agent_id_options,
            auto_battle_options,
            expand_team_list,
            instance_dir,
        )

        if instance_idx is not None:
            root, _ = self.context.native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            _, root, user_cfg, _ = self.context.user(script_id, user_id)
            slot = int(user_cfg.Info.SlotIdx or -1)

        teams = []
        if slot > 0:
            for item in expand_team_list(instance_dir(root, slot)):
                teams.append(
                    {
                        "idx": int(item["idx"]),
                        "name": str(item["name"]),
                        "autoBattle": str(item["auto_battle"]),
                        "agents": [str(a) for a in item["agent_id_list"]],
                    }
                )
        return {
            "teams": teams,
            "autoBattle": auto_battle_options(self.get_root(script_id)),
            "agentOptions": agent_id_options(self.get_root(script_id)),
        }

    async def save_teams(
        self,
        script_id: str,
        user_id: str,
        teams: list,
        instance_idx: int | None = None,
    ) -> list:
        """整表保存预备编队（名称 + 绑定配队方案，成员按行保留）。"""

        from app.task.ZzzOd.tools import instance_dir, write_team_list

        if instance_idx is not None:
            self.context.native_instance(script_id, instance_idx)
            slot = int(instance_idx)
        else:
            from app.task.ZzzOd.slots import (
                collect_used_slot_idxs,
                ensure_user_slot,
            )

            _, root, user_cfg, uid = self.context.user(script_id, user_id)
            used = collect_used_slot_idxs(
                root, exclude_uids={uid}, scripts=self.context.scripts
            )
            slot = await ensure_user_slot(
                root, user_cfg, used, script_id=script_id, owner_uid=str(uid)
            )

        saved = write_team_list(instance_dir(self.get_root(script_id), slot), teams)
        logger.info(f"ZZZ-OD 预备编队已保存到槽 {slot:02d}: {len(saved)} 个编队")
        return saved

    async def get_native_config(self, script_id: str, instance_idx: int) -> dict:
        """读取实例原生配置（账号字段 + 启动参数 + 任务编排 + 运行实例），供直控页面表单渲染。

        account 条目含默认值合并与可选项；launchArgs 为 game.yml 启动参数
        （缺失合并上游默认值，-use-d3d12 拆出为 dx12 开关）；tasks 为原生
        app_list 与应用目录合并后的任务卡片数据（enabled 保持原生状态）；
        instanceRun 为 one_dragon.yml 的 instance_run 原值（仅运行当前/全部实例）。
        """

        root, instance = self.context.native_instance(script_id, instance_idx)
        slot = int(instance_idx)

        from app.task.ZzzOd.tools import (
            read_native_account_fields,
            read_native_after_done,
            read_native_instance_run,
            read_native_launch_args,
            read_native_tasks,
        )

        catalog = read_task_catalog(root)
        return {
            "instanceIdx": slot,
            "instanceName": str(instance.get("name", "")),
            "account": read_native_account_fields(root, slot),
            "tasks": read_native_tasks(root, slot, catalog),
            "instanceRun": read_native_instance_run(root),
            "afterDone": read_native_after_done(root),
            "launchArgs": read_native_launch_args(root, slot),
        }

    async def save_native_config(
        self,
        script_id: str,
        instance_idx: int,
        account: dict | None = None,
        tasks: list[dict] | None = None,
        instance_run: str | None = None,
        launch_args: dict | None = None,
        after_done: str | None = None,
    ) -> dict:
        """把直控页面改动直接写回所选实例原生配置（可选增量，缺省字段不写回）。

        账号字段白名单过滤 + 只写非默认值；任务编排保留完整顺序（含未启用项）；
        instance_run / after_done 白名单校验；launchArgs 整组提交（六字段 +
        dx12 开关合并进高级参数，值未变跳过）。由调用方按需传参：任务开关/
        运行实例等即时写入只传对应字段，避免把未确认的账号草稿一并落盘。
        """

        root, instance = self.context.native_instance(script_id, instance_idx)
        slot = int(instance_idx)

        from app.task.ZzzOd.tools import (
            read_native_after_done,
            read_native_instance_run,
            save_native_account_fields,
            save_native_after_done,
            save_native_instance_run,
            save_native_launch_args,
            save_native_tasks,
        )

        if account is not None:
            save_native_account_fields(root, slot, account)
        if tasks is not None:
            save_native_tasks(root, slot, tasks)
        if launch_args is not None:
            save_native_launch_args(root, slot, launch_args)
        if instance_run is not None:
            # 等于原生文件当前值时跳过写：避免直控页保存账号/任务时把
            # 用户没改过的运行实例值写死（review 提的：从没动过下拉的多
            # 实例用户会被「仅运行当前」覆盖 → 一条龙从跑全部变成只跑当前）
            current = read_native_instance_run(root)
            if instance_run != current:
                save_native_instance_run(root, instance_run)
        if after_done is not None:
            current_after_done = read_native_after_done(root)
            if after_done != current_after_done:
                save_native_after_done(root, after_done)
        logger.info(f"ZZZ-OD 实例 {slot:02d} 原生配置已由直控页面保存")
        return {
            "instanceIdx": slot,
            "instanceName": str(instance.get("name", "")),
            "savedAccountCount": len(account) if account is not None else 0,
        }

    def ensure_direct_backup(self, script_id: str) -> dict:
        """直控前置保护：确保一条龙原生配置已有最新备份（指纹去重）。

        对当前一条龙原生配置（one_dragon.yml + 原生实例目录，排除 MAS 槽）
        与最近一份备份做指纹对比：无任何备份或内容已变化则立即归档——让
        用户在直控页误操作改坏原生配置前，始终存在一个「切换时点」的恢复点。

        Returns:
            {"created": 是否本次新建, "time": 最新备份时间戳}。
        """

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.tools import (
            archive_onedragon_backup,
            list_onedragon_backups,
        )

        dest = archive_onedragon_backup(root)
        times = list_onedragon_backups(root)
        return {
            "created": dest is not None,
            "time": times[0] if times else "",
        }

    def get_launchers(self, script_id: str) -> dict:
        """返回 zzz-od 两种启动器的安装情况（启动器下拉/禁用未安装项用）。

        Returns:
            {"original_available": bool, "integrated_available": bool}
        """

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)

        from app.task.ZzzOd.launchers import find_launchers

        available = find_launchers(root)
        return {
            "original_available": "原始" in available,
            "integrated_available": "集成" in available,
        }
