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

"""ZZZ-OD 导入、恢复、预览与删除时的槽回收；文件原语复用通用归档基座。"""

import asyncio
import json
import shutil
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from typing import cast

from app.config import ConfigEntry
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.utils import constants as _utils_constants
from app.utils import io as _utils_io
from app.utils.common.log import logger as _utils_logger

from .config_context import ZzzOdContext

logger = _utils_logger.get_logger("配置管理")


class ZzzOdRecovery:
    def __init__(self, context: ZzzOdContext) -> None:
        self.context = context

    async def prepare_script_removal(self, script: ConfigEntry) -> None:
        """删脚本前回收全部槽及其恢复历史，同脚本用户互不阻挡。"""
        script_id = str(script.uid)
        script_config = cast(ZzzOdConfig, script)
        for uid in list(script_config.UserData.keys()):
            await self._recycle_user_slot(
                script_id=script_id,
                script_config=script_config,
                user_uid=uid,
                action="删除脚本",
                exclude_same_script=True,
            )

    def prepare_user_removal(
        self, script: ConfigEntry, user_id: uuid.UUID
    ) -> Callable[[], Awaitable[None]] | None:
        """捕获槽信息；公共层提交删除后才回收，锁拒绝时不动文件。"""
        script_config = cast(ZzzOdConfig, script)
        if user_id not in script_config.UserData:
            return None
        user_cfg = script_config.UserData[user_id]
        slot = int(user_cfg.Info.SlotIdx or -1)
        if slot <= 0:
            return None
        return partial(
            self._recycle_bound_slot,
            script_id=str(script.uid),
            script_config=script_config,
            user_uid=user_id,
            slot=slot,
            name=str(user_cfg.Info.Name or ""),
            action="删除用户",
        )

    async def restore_recycle(
        self,
        script_id: str,
        slot_idx: int,
        ts: str,
        *,
        target_user: str | None = None,
        new_user_name: str | None = None,
    ) -> tuple[int, str]:
        """把回收池里的一条槽快照恢复给某个 MAS 用户（现有用户或新建用户）。

        恢复的落点是**用户的绑定槽**，而不是某个裸槽号：只把内容物化到
        ``config/NN`` 而不建立绑定的恢复没有出口——MAS 下次运行不会认领它，
        用户拿不到内容（想取出文件用回收池的「查看」直接复制）。

        ``target_user`` 指定现有用户 uid；``new_user_name`` 新建一个用户并把
        内容恢复到它的槽（名字即该值）。二者必须且只能给一个。目标用户尚无
        绑定槽时按常规分配（含认领它上次没跑完的槽）；已有绑定槽时覆盖其内容
        ——恢复前自动存底，误恢复可从回收池找回。

        Returns:
            ``(目标槽号, 用户名)``。

        Raises:
            RuntimeError: 有同安装的 ZzzOd 脚本正在运行，或本脚本配置已锁定
                （恢复会写 ``config/NN`` 与用户绑定号，可能与在跑任务竞态）。
            ValueError: 恢复目标非法（两个都给/都不给、新用户名为空、指定用户
                不属于该脚本），或回收条目不存在/内容为空。条目问题先于建用户
                判定，恢复中失败也会把刚建的用户撤掉，不留半成品。
        """

        from app.task.ZzzOd.slots import collect_used_slot_idxs, ensure_user_slot
        from app.task.ZzzOd.tools import restore_recycle_slot
        from app.task.ZzzOd.tools.backup_archive import recycle_backup_root
        from app.utils.common.config import archive as _utils_config_archive

        script_config = self.context.script_config(script_id)
        root = self.context.root(script_config)
        self.context.ensure_install_unlocked(root)
        if script_config.is_locked:
            raise RuntimeError("脚本正在运行, 请结束后再试")
        if bool(target_user) == bool(new_user_name):
            raise ValueError("恢复目标必须且只能选一个：现有用户或新建用户")
        # 先验明快照在场再动手：建用户、写绑定都是持久化的，等写完才发现
        # 条目不对就留下一个没内容的半成品用户
        if (
            _utils_config_archive.get_backup_dir(
                recycle_backup_root(root, slot_idx), ts
            )
            is None
        ):
            raise ValueError(f"备份不存在: {ts}")

        created_uid: uuid.UUID | None = None
        try:
            if new_user_name is not None:
                name = str(new_user_name).strip()
                if not name:
                    raise ValueError("新用户名称不能为空")
                # 复用宿主的通用添加用户入口，初始化与守卫不另走分支。
                uid, created_user = await self.context.add_user(script_id)
                created_uid = uid
                if not isinstance(created_user, ZzzOdUserConfig):
                    raise TypeError("用户配置类型错误")
                user_cfg = created_user
                await user_cfg.update(
                    type(user_cfg).model_validate({"Info": {"Name": name}}),
                    check_visibility=False,
                )
            else:
                _, _, user_cfg, uid = self.context.user(script_id, str(target_user))
                name = str(user_cfg.Info.Name or "")

            used = collect_used_slot_idxs(
                root, exclude_uids={uid}, scripts=self.context.scripts
            )
            dest = await ensure_user_slot(
                root, user_cfg, used, script_id=script_id, owner_uid=str(uid)
            )
            # 存底 + 整目录替换是阻塞 IO（拷贝槽目录），放线程里跑
            await asyncio.to_thread(
                restore_recycle_slot, root, slot_idx, ts, target_slot=dest
            )
        except Exception:
            # 恢复中失败把刚建的用户撤掉：留着它会是个没内容的半成品用户；
            # 它的槽随后因归属消失被自动回收（内容已在回收池存底，可再恢复）
            if created_uid is not None:
                try:
                    script_config.UserData.remove(created_uid)
                    await script_config.UserData.commit()
                except Exception as e:
                    logger.opt(exception=True).warning(
                        f"恢复失败后撤回新建用户失败（请手动删除）: {e}"
                    )
            raise
        logger.info(
            f"ZZZ-OD 槽 {slot_idx:02d} 已从回收池恢复到用户「{name}」的槽 "
            f"{dest:02d} 快照 {ts}"
        )
        return dest, name

    async def restore_backup(
        self, script_id: str, user_id: str, ts: str, target: str, *, force: bool = False
    ) -> int:
        """把指定备份恢复到目标位置，返回关联槽 idx（-1 表示不涉及槽）。

        - target="onedragon"：把一条龙原生配置备份（one_dragon.yml + 原生
          实例目录）恢复到一条龙本身——只写回备份中的文件，MAS 槽目录永不
          触碰；恢复前自动归档当前原生配置，误恢复可找回；
        - target="mas"：把 MAS 用户槽备份恢复到绑定槽，并从恢复后的槽内容
          把账号字段与任务编排全量回填到 MAS 本页字段（表单随即刷新）——
          配队等 MAS 不管的内容随槽内容回到该时点。

        ``force=True``：源注册表损坏且用户已在二次确认中选择强制恢复——
        onedragon 跳过「恢复前存底」（该步要读损坏的注册表），mas 跳过
        占用守卫（可能覆盖原生实例槽，覆盖前仍会对槽做强制存底）。
        """

        from app.task.ZzzOd.tools import (
            MAS_USER_INFO_FILE,
            collect_mas_user_info,
            get_mas_backup_dir,
            get_onedragon_backup_dir,
            instance_dir,
            materialize_user_fields,
            normalize_app_group_entries,
            read_app_group,
            read_game,
            read_game_account,
            read_team_list,
            restore_mas_backup,
            restore_onedragon_backup,
        )
        from app.utils.common.config import archive as _utils_config_archive

        _, root, user_cfg, uid = self.context.user(script_id, user_id)

        if target == "onedragon":
            # 恢复守卫：备份内的原生实例 idx 若已被任一 MAS 用户绑定为配置槽
            # （任何脚本、含本用户——恢复会整目录替换槽目录），中止并点名，
            # 避免把绑定槽内容覆盖成原生实例；原生注册表不在此列，恢复本就
            # 是把原生世界拉回该时点（恢复前已强制存底）
            backup_dir = get_onedragon_backup_dir(root, ts)
            if backup_dir is None:
                raise ValueError(f"备份不存在: {ts}")
            backup_idxs = {
                int(rel.split("/", 1)[0])
                for rel in _utils_config_archive.dir_files(backup_dir)
                if "/" in rel
                and rel.split("/", 1)[0].isascii()
                and rel.split("/", 1)[0].isdigit()
            }
            for bound_script in self.context.scripts.values():
                if not isinstance(bound_script, ZzzOdConfig):
                    continue
                for bound_uid, bound_cfg in bound_script.UserData.items():
                    bound_slot = int(bound_cfg.Info.SlotIdx or -1)
                    if bound_slot not in backup_idxs:
                        continue
                    if bound_uid == uid:
                        who = "本用户"
                    else:
                        who = f"脚本「{str(bound_script.Info.Name or '未知脚本')}」的用户「{str(bound_cfg.Info.Name or '未知用户')}」"
                    raise ValueError(
                        f"备份含原生实例 {bound_slot:02d}，已被{who}绑定为配置槽，"
                        "恢复会覆盖其内容，已中止"
                    )
            restore_onedragon_backup(root, ts, snapshot_current=not force)
            logger.info(f"ZZZ-OD 用户 {uid} 已把备份 {ts} 恢复到一条龙原生配置")
            return -1

        slot = int(user_cfg.Info.SlotIdx or -1)
        if slot <= 0:
            raise ValueError("该用户还没有生成过配置备份")
        backup_dir = get_mas_backup_dir(script_id, slot, ts)
        if backup_dir is None:
            raise ValueError(f"备份不存在: {ts}")
        # 写入现场或归档前先读完备份源文件；坏备份不能通过 force 放行。
        # 缺文件沿用读取器默认值，兼容旧备份。
        try:
            backup_account = read_game_account(backup_dir)
            read_game(backup_dir)
            backup_apps = normalize_app_group_entries(read_app_group(backup_dir))
            read_team_list(backup_dir)
            backup_info = _utils_io.read_dict_file(
                backup_dir / MAS_USER_INFO_FILE, allow_empty=True
            )
            # 旧归档的信息快照键是 Info.Mode（现 Info.Base），读入时归一
            if "Mode" in backup_info and "Base" not in backup_info:
                backup_info["Base"] = _utils_constants.normalize_base_source(
                    backup_info.pop("Mode")
                )
        except _utils_io.ConfigCorruptedError as exc:
            raise ValueError(f"备份内容已损坏，无法恢复：{exc}") from exc
        # 恢复守卫：目标槽必须仍归本用户或空闲，被其他实体占用则拦截并点名，
        # 避免把别人的槽内容覆盖掉（覆盖前也不归档他人内容）。注册表损坏时
        # 守卫读不了原生占用，未 force 抛给上层转 409；force 视为空闲放行
        # （用户已确认，覆盖前 restore_mas_backup 内部仍会强制存底）
        try:
            occupant = self.context.slot_occupant(root, script_id, uid, slot)
        except _utils_io.ConfigCorruptedError:
            if not force:
                raise
            occupant = None
        if occupant is not None:
            raise ValueError(
                f"目标槽 {slot:02d} 当前已被「{occupant}」占用，"
                "为避免覆盖他人配置已中止恢复，请先处理占用后再试"
            )
        slot_dir = instance_dir(root, slot)
        # 先读当前槽内会被读-改-写/整表覆盖的 YAML（game_account、game、
        # _group——materialize 的 write_app_group 会整表覆盖 _group.yml）。
        # 普通恢复遇到现场坏档要在任何物化/归档前保留 409；force 已获确认
        # 时跳过物化，随后由 restore_mas_backup 原样归档坏现场，再换入已
        # 预校验的好备份。
        materialize_current = True
        try:
            read_game_account(slot_dir)
            read_game(slot_dir)
            read_app_group(slot_dir)
        except _utils_io.ConfigCorruptedError:
            if not force:
                raise
            materialize_current = False
        # 恢复前先物化本页账号+编排进槽，再走 restore_mas_backup 内部「强制
        # 归档当前」——这份「恢复前存底」才能回到本页配置状态（否则缺账号，
        # 误恢复想找回时会把本页账号清空）。force 跳过坏现场物化以保留原始
        # 字节，归档仍由 restore_mas_backup 完成。
        if materialize_current:
            materialize_user_fields(slot_dir, user_cfg)
        restore_mas_backup(
            script_id,
            slot,
            ts,
            slot_dir,
            meta=collect_mas_user_info(user_cfg),
        )

        # 恢复后的槽内容 = 该时点的 MAS 配置；把 MAS 管理的字段全量回填本页
        account = backup_account
        # 任务编排整表回填（含未启用项原位保留顺序，运行侧只消费启用项）
        all_apps = backup_apps
        await user_cfg.update(
            type(user_cfg).model_validate(
                {"Game": {"GameRegion": str(account.get("game_region") or "cn")}}
            ),
            check_visibility=False,
        )
        await user_cfg.update(
            type(user_cfg).model_validate(
                {"Game": {"GamePath": str(account.get("game_path") or "")}}
            ),
            check_visibility=False,
        )
        await user_cfg.update(
            type(user_cfg).model_validate(
                {"Game": {"GameLanguage": str(account.get("game_language") or "cn")}}
            ),
            check_visibility=False,
        )
        await user_cfg.update(
            type(user_cfg).model_validate(
                {
                    "Game": {
                        "BilibiliAccountName": str(
                            account.get("bilibili_account_name") or ""
                        )
                    }
                }
            ),
            check_visibility=False,
        )
        await user_cfg.update(
            type(user_cfg).model_validate(
                {"Game": {"Account": str(account.get("account") or "")}}
            ),
            check_visibility=False,
        )
        await user_cfg.update(
            type(user_cfg).model_validate(
                {"Game": {"Password": str(account.get("password") or "")}}
            ),
            check_visibility=False,
        )
        await user_cfg.update(
            type(user_cfg).model_validate(
                {"OneDragon": {"AppList": json.dumps(all_apps, ensure_ascii=False)}}
            ),
            check_visibility=False,
        )
        # 信息字段回填（用户名/启用/base 来源/启动器/剩余天数/备注/节点详情推送）：
        # 旧备份可能没有该快照，缺失字段跳过，保持向前兼容
        for field in (
            "Name",
            "Status",
            "Base",
            "LauncherMode",
            "RemainedDay",
            "Notes",
        ):
            if field in backup_info:
                await user_cfg.update(
                    type(user_cfg).model_validate(
                        {"Info": {field: backup_info[field]}}
                    ),
                    check_visibility=False,
                )
        if "PushLogMode" in backup_info:
            await user_cfg.update(
                type(user_cfg).model_validate(
                    {"Notify": {"PushLogMode": backup_info["PushLogMode"]}}
                ),
                check_visibility=False,
            )
        await self.context.flush()
        logger.info(
            f"ZZZ-OD 用户 {uid} 已把备份 {ts} 恢复到 MAS 配置 "
            f"(槽 {slot:02d} + 字段回填, 任务 {len(all_apps)} 项)"
        )
        return slot

    async def import_config(
        self, script_id: str, user_id: str, instance_idx: int
    ) -> dict:
        """基于一条龙已有实例快速生成当前用户配置（账号信息 + 已启用任务编排 + 实例级配置）。

        覆盖前强制归档当前 MAS 槽配置（与「配置恢复」一致：即使内容与最近
        备份一致也生成新时间戳条目）——导入前的状态可在配置恢复中按 MAS
        配置找回。账号字段只回填来源实例的非空值（密码留空=沿用登录态），
        任务编排只取来源实例当前启用的应用（对齐 _group.yml 缺席=不加入）。
        实例级配置随导入对齐来源实例写入绑定槽：notify.yml（应用通知，
        zzz-od 默认开启，不搬会让「来源关着」变开着）、team.yml（预备编队）、
        game.yml（按键配置：键盘/手柄按键、后台模式、输入方式、HDR、启动
        参数、分辨率等，MAS 不托管、注入不触碰，只能靠导入对齐）、
        one_dragon/ 全部 per-app 配置（体力计划/咖啡店/随便观等任务级 yml）。
        """

        from app.task.ZzzOd.slots import (
            collect_used_slot_idxs,
            ensure_user_slot,
        )
        from app.task.ZzzOd.tools import (
            archive_mas_config_backup,
            collect_mas_user_info,
            instance_dir,
            normalize_app_group_entries,
            read_app_group,
            read_game_account,
            read_native_registry,
        )

        _, root, user_cfg, uid = self.context.user(script_id, user_id)
        slot = int(user_cfg.Info.SlotIdx or -1)
        # 来源校验必须先于存底物化：自身槽不能既作母版又被页面字段覆盖。
        if slot > 0 and int(instance_idx) == slot:
            raise ValueError("不能从当前用户绑定的 MAS 槽导入配置")
        instance = next(
            (
                item
                for item in read_native_registry(root).get("instance_list", [])
                if int(item["idx"]) == int(instance_idx)
            ),
            None,
        )
        if instance is None:
            raise ValueError(
                f"原生实例 {int(instance_idx):02d} 不存在，请重新选择导入来源"
            )
        source_dir = instance_dir(root, int(instance_idx))
        if slot > 0:
            slot_dir = root / "config" / f"{slot:02d}"
            if slot_dir.is_dir():
                # 覆盖前存底走统一入口（先物化再快照）：不物化的「导入前」
                # 备份缺账号，恢复它会把本页账号清空。导入是覆盖性操作，
                # 存底失败必须中止导入，否则覆盖前现场彻底丢失
                archive_mas_config_backup(
                    script_id,
                    slot,
                    slot_dir,
                    user_cfg,
                    force=True,
                    meta=collect_mas_user_info(user_cfg),
                    fail_on_snapshot_error=True,
                )

        game_account = read_game_account(source_dir)
        # 任务编排整表导入（含未启用项原位保留顺序，运行侧只消费启用项）
        all_apps = normalize_app_group_entries(read_app_group(source_dir))

        field_map = {
            "GameRegion": "game_region",
            "GamePath": "game_path",
            "GameLanguage": "game_language",
            "Account": "account",
            "Password": "password",
            "BilibiliAccountName": "bilibili_account_name",
            "Platform": "platform",
            "CustomWinTitle": "custom_win_title",
        }
        imported_accounts = 0
        for user_key, native_key in field_map.items():
            value = str(game_account.get(native_key) or "").strip()
            if not value:
                continue
            await user_cfg.update(
                type(user_cfg).model_validate({"Game": {user_key: value}}),
                check_visibility=False,
            )
            imported_accounts += 1
        if "use_custom_win_title" in game_account:
            await user_cfg.update(
                type(user_cfg).model_validate(
                    {
                        "Game": {
                            "UseCustomWinTitle": bool(
                                game_account.get("use_custom_win_title")
                            )
                        }
                    }
                ),
                check_visibility=False,
            )
            imported_accounts += 1

        await user_cfg.update(
            type(user_cfg).model_validate(
                {"OneDragon": {"AppList": json.dumps(all_apps, ensure_ascii=False)}}
            ),
            check_visibility=False,
        )

        # 实例级持久配置对齐来源实例：
        # - notify.yml（应用通知）在实例根
        # - team.yml（预备编队：名称 + 绑定配队方案 + 成员）在实例根
        # - game.yml（GameConfig 按键配置：键盘/手柄按键、后台模式、输入方式、
        #   HDR、启动参数、分辨率）在实例根——MAS 不托管该文件，注入运行也
        #   不触碰，导入不对齐会导致按键配置永远停留在 zzz-od 默认值
        # - one_dragon/ 全部 per-app 配置（charge_plan.yml 体力计划、coffee.yml
        #   咖啡店、suibian_temple.yml 随便观等）随导入整目录对齐
        # _group.yml 例外：任务编排走上面的 AppList 整表语义（含未启用项），不整搬。
        # 均不经 MAS 用户字段承载，直接对齐到绑定槽（注入运行的实例目录）；
        # 用户尚无绑定槽时按全局查重分配（语义与运行注入的 ensure_user_slot
        # 一致）。来源缺失的文件对齐为删除 = 沿用 zzz-od 默认
        slot = int(user_cfg.Info.SlotIdx or -1)
        if slot <= 0:
            slot = await ensure_user_slot(
                root,
                user_cfg,
                collect_used_slot_idxs(
                    root, exclude_uids={uid}, scripts=self.context.scripts
                ),
                script_id=script_id,
                owner_uid=str(uid),
            )
        target_dir = instance_dir(root, slot)
        target_dir.mkdir(parents=True, exist_ok=True)

        # 底层防御：路径别名也可能指向同一目录，整段同步均应跳过自复制。
        same_dir = source_dir.resolve() == target_dir.resolve()
        if not same_dir:

            def _align_yml(rel_parts: tuple[str, ...]) -> None:
                source_yml = source_dir.joinpath(*rel_parts)
                target_yml = target_dir.joinpath(*rel_parts)
                target_yml.parent.mkdir(parents=True, exist_ok=True)
                if source_yml.is_file():
                    shutil.copyfile(source_yml, target_yml)
                else:
                    target_yml.unlink(missing_ok=True)

            _align_yml(("notify.yml",))
            _align_yml(("team.yml",))
            _align_yml(("game.yml",))

            source_one_dragon = source_dir / "one_dragon"
            target_one_dragon = target_dir / "one_dragon"
            if target_one_dragon.is_dir():
                for target_yml in target_one_dragon.glob("*.yml"):
                    if (
                        target_yml.name != "_group.yml"
                        and not (source_one_dragon / target_yml.name).is_file()
                    ):
                        target_yml.unlink(missing_ok=True)
            if source_one_dragon.is_dir():
                target_one_dragon.mkdir(parents=True, exist_ok=True)
                for source_yml in source_one_dragon.glob("*.yml"):
                    if source_yml.name == "_group.yml":
                        continue
                    shutil.copyfile(source_yml, target_one_dragon / source_yml.name)

        await self.context.flush()
        align_note = (
            f"来源与槽 {slot:02d} 为同一目录，已跳过实例级对齐"
            if same_dir
            else f"应用通知/按键配置/体力计划已对齐槽 {slot:02d}"
        )
        logger.info(
            f"ZZZ-OD 用户 {uid} 已从实例 {int(instance_idx):02d} 导入配置"
            f"(账号字段 {imported_accounts} 项, 任务 {len(all_apps)} 项, "
            f"{align_note})"
        )
        return {
            "instanceIdx": int(instance_idx),
            "instanceName": str(instance.get("name", "")),
            "importedAccountCount": imported_accounts,
            "importedTaskCount": len(all_apps),
            "slot": slot,
        }

    async def _recycle_user_slot(
        self,
        script_id: str,
        script_config: ZzzOdConfig,
        user_uid: uuid.UUID,
        *,
        action: str,
        exclude_same_script: bool = False,
    ) -> None:
        """回收用户的绑定槽（del_script 循环用；del_user 走 _recycle_bound_slot）。"""

        if user_uid not in script_config.UserData:
            return
        user_cfg = script_config.UserData[user_uid]
        slot = int(user_cfg.Info.SlotIdx or -1)
        if slot <= 0:
            return
        name = str(user_cfg.Info.Name or "")
        await self._recycle_bound_slot(
            script_id,
            script_config,
            user_uid,
            slot,
            name,
            action=action,
            exclude_same_script=exclude_same_script,
        )

    async def _recycle_bound_slot(
        self,
        script_id: str,
        script_config: ZzzOdConfig,
        user_uid: uuid.UUID | None,
        slot: int,
        name: str,
        *,
        action: str,
        exclude_same_script: bool = False,
    ) -> None:
        """回收一个已知的绑定槽：归档进项目级回收池后删除槽目录（幂等）。

        槽目录是 MAS 分配在一条龙安装目录里的，注册表里没有它、GUI 看不见，
        直控删实例还受绑定保护，用户/脚本删除后没有任何出口能清掉——只能在
        删除动作里一并回收，否则永久残留并占着 idx。仍被原生实例或其他
        ZzzOd 用户占用时跳过（那是别人的槽）；安装目录失效、注册表不可读时
        也跳过。删除动作不因回收失败中断（每一步的失败都只告警）。

        槽的 MAS 备份池一并回收：mas 池按（脚本, 槽）分桶、没有用户维度，
        槽号分给新用户后留在原位会串到别人名下（见
        :func:`app.task.ZzzOd.tools.recycle_mas_backups`）。槽目录收走后该号
        同时移出分配台账（台账只记 MAS 手上还在用的号）。

        ``exclude_same_script``：删脚本时传 True——整个脚本都在移除，同脚本
        用户间的相互占用不挡回收（否则共享同一槽的两个用户会双双跳过，
        mas 池随后被 data/{script_id} 整删且未经归档，恢复历史丢失）。
        """

        from app.task.ZzzOd.slots import forget_allocated_slot
        from app.task.ZzzOd.tools import recycle_mas_backups, recycle_slot

        try:
            root = self.context.root(script_config)
        except Exception:
            return  # 安装目录没配好或已失效，无从回收
        try:
            occupant = self.context.slot_occupant(
                root, script_id, user_uid, slot, exclude_same_script=exclude_same_script
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"槽 {slot:02d} 占用判定失败，跳过回收: {e}"
            )
            return
        if occupant is not None:
            logger.warning(f"槽 {slot:02d} 仍被「{occupant}」占用，跳过回收")
            return
        reason = f"{action} {name}".strip()
        # 归档 + 删目录是阻塞 IO（拷贝槽目录），放线程里跑
        try:
            if await asyncio.to_thread(recycle_slot, root, slot, reason=reason):
                # 目录已收走，该号移出台账（与恢复路径同口径：台账只记「当前由
                # MAS 持有」的号；留着它，将来同号目录再出现会被自动回收当残留
                # 收走）。回收失败时目录还在，台账保留，仍受自动回收管辖
                forget_allocated_slot(root, slot)
            await asyncio.to_thread(
                recycle_mas_backups, root, script_id, slot, reason=reason
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"槽 {slot:02d} 回收失败，已跳过（不阻断删除）: {e}"
            )

    @staticmethod
    def _preview_account_fields(account: dict) -> list[dict]:
        """备份预览用的账号字段列表；密码一律掩码、不返回明文。

        预览是纯展示（恢复直接回写备份文件内容，不经此值），密码明文没有
        理由出现在响应里；其余字段缺失时合并默认值（无值前端兜底 ``—``）。
        自定义窗口标题两字段一并展示（``use_custom_win_title`` 转是否——
        ``custom_win_title`` 是启用时的标题，两行都显示，简单化）。
        mas 与 onedragon 两个预览分支共用。
        """

        from app.task.ZzzOd.tools.zzz_od_config import DEFAULT_GAME_ACCOUNT

        def _value(key: str) -> str:
            if key == "password" and account.get(key):
                return "••••••••"
            if key == "use_custom_win_title":
                return "是" if account.get(key) else "否"
            return str(
                account[key]
                if account.get(key) is not None
                else DEFAULT_GAME_ACCOUNT.get(key, "")
            )

        return [
            {"key": key, "value": _value(key)}
            for key in (
                "game_region",
                "game_path",
                "game_language",
                "account",
                "password",
                "bilibili_account_name",
                "use_custom_win_title",
                "custom_win_title",
            )
        ]

    def get_backup_preview(
        self, script_id: str, user_id: str, ts: str, target: str
    ) -> dict:
        """读取指定备份的配置摘要（纯读不恢复），供「预览配置」快速展示。

        - target="mas"：基本信息卡信息字段（用户名/启用/base 来源/启动器/剩余天数/
          备注/节点详情推送，来自备份内信息快照）+ 账号字段（缺失合并默认值，
          密码掩码）+ 任务编排（应用目录并入中文名）；
        - target="onedragon"：备份内 one_dragon.yml 注册表的实例列表。
        """

        from app.task.ZzzOd.tools import (
            MAS_USER_INFO_FILE,
            get_mas_backup_dir,
            get_onedragon_backup_dir,
            inspect_onedragon_backup,
            list_app_catalog,
            read_app_group,
            read_game,
            read_game_account,
            read_team_list,
        )

        # 脚本安装根目录（onedragon/mas 两条分支都要用：实例名书、槽目录）
        root = self.context.root(self.context.script_config(script_id))

        if target == "onedragon":
            backup = get_onedragon_backup_dir(root, ts)
            if backup is None:
                raise ValueError(f"备份不存在: {ts}")
            data, warnings = inspect_onedragon_backup(backup)
            warnings = list(warnings)
            name_book = {
                str(item.get("app_id")): str(item.get("app_name") or "")
                for item in list_app_catalog(root)
            }
            instances = []
            entries = data.get("instance_list")
            if not isinstance(entries, list):
                entries = []
            for item in entries:
                if not isinstance(item, dict):
                    continue
                raw_idx = item.get("idx")
                if not isinstance(raw_idx, int) or isinstance(raw_idx, bool):
                    continue
                idx = int(raw_idx)
                # 实例明细来自备份目录内的 {idx}/（备份按原生注册表逐 idx 归档，
                # 目录名不带零填充，与一条龙原生实例目录同构）
                backup_idx_dir = backup / str(idx)
                try:
                    account = read_game_account(backup_idx_dir)
                except _utils_io.ConfigCorruptedError as exc:
                    warnings.append(
                        f"原生备份实例 {idx:02d} 账号配置损坏，无法预览：{exc}"
                    )
                    account = {}
                account_fields = self._preview_account_fields(account)
                task_fields = []
                try:
                    app_group = read_app_group(backup_idx_dir)
                except _utils_io.ConfigCorruptedError as exc:
                    warnings.append(
                        f"原生备份实例 {idx:02d} 任务编排损坏，无法预览：{exc}"
                    )
                    app_group = []
                for task in app_group:
                    app_id = str(task.get("app_id") or "").strip()
                    if not app_id:
                        continue
                    task_fields.append(
                        {
                            "app_id": app_id,
                            "app_name": name_book.get(app_id) or app_id,
                            "enabled": bool(task.get("enabled")),
                        }
                    )
                instances.append(
                    {
                        "idx": idx,
                        "name": str(item.get("name", "")),
                        "active": bool(item.get("active")),
                        "active_in_od": bool(item.get("active_in_od")),
                        "account": account_fields,
                        "tasks": task_fields,
                    }
                )
            return {
                "time": ts,
                "target": target,
                "info": [],
                "account": [],
                "tasks": [],
                "instances": instances,
                "warnings": warnings,
                "restoreAllowed": not warnings,
            }

        _, root, user_cfg, _ = self.context.user(script_id, user_id)
        slot = int(user_cfg.Info.SlotIdx or -1)
        if slot <= 0:
            raise ValueError("该用户还没有生成过配置备份")
        backup = get_mas_backup_dir(script_id, slot, ts)
        if backup is None:
            raise ValueError(f"备份不存在: {ts}")

        # 预览把损坏文件降级为警示（与 onedragon 分支一致）：摘要照常返回，
        # restoreAllowed=False 锁住恢复；坏备份仍由恢复前预读统一拦截。
        warnings: list[str] = []
        info: dict = {}
        try:
            info = _utils_io.read_dict_file(
                backup / MAS_USER_INFO_FILE, allow_empty=True
            )
            # 旧归档的信息快照键是 Info.Mode（现 Info.Base），读入时归一
            if "Mode" in info and "Base" not in info:
                info["Base"] = _utils_constants.normalize_base_source(info.pop("Mode"))
        except _utils_io.ConfigCorruptedError as exc:
            warnings.append(f"备份信息快照损坏，无法恢复：{exc}")
        account: dict = {}
        try:
            account = read_game_account(backup)
        except _utils_io.ConfigCorruptedError as exc:
            warnings.append(f"备份账号配置损坏，无法恢复：{exc}")
        try:
            read_game(backup)
        except _utils_io.ConfigCorruptedError as exc:
            warnings.append(f"备份启动参数损坏，无法恢复：{exc}")
        try:
            read_team_list(backup)
        except _utils_io.ConfigCorruptedError as exc:
            warnings.append(f"备份编队配置损坏，无法恢复：{exc}")

        info_fields = []
        for key, field in (
            ("name", "Name"),
            ("status", "Status"),
            ("base", "Base"),
            ("launcher_mode", "LauncherMode"),
            ("remained_day", "RemainedDay"),
            ("notes", "Notes"),
            ("push_log_mode", "PushLogMode"),
        ):
            if field not in info:
                continue
            info_fields.append({"key": key, "value": str(info[field])})

        account_fields = self._preview_account_fields(account)

        name_book = {
            str(item.get("app_id")): str(item.get("app_name") or "")
            for item in list_app_catalog(root)
        }
        app_group: list = []
        try:
            app_group = read_app_group(backup)
        except _utils_io.ConfigCorruptedError as exc:
            warnings.append(f"备份任务编排损坏，无法恢复：{exc}")
        tasks = []
        for item in app_group:
            app_id = str(item.get("app_id") or "").strip()
            if not app_id:
                continue
            tasks.append(
                {
                    "app_id": app_id,
                    "app_name": name_book.get(app_id) or app_id,
                    "enabled": bool(item.get("enabled")),
                }
            )
        return {
            "time": ts,
            "target": target,
            "info": info_fields,
            "account": account_fields,
            "tasks": tasks,
            "instances": [],
            "warnings": warnings,
            "restoreAllowed": not warnings,
        }
