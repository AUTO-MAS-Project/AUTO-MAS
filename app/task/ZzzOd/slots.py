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

"""ZZZ-OD 槽分配、台账与回收；跨脚本查询显式接收配置集合。"""

import json
import shutil
import uuid
from pathlib import Path

from app.config import ConfigCollection, ConfigEntry
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.utils import constants as _utils_constants
from app.utils.common.config import archive as _utils_config_archive
from app.utils.common.log import logger as _utils_logger

from .tools import (
    MAS_SLOT_BASE,
    MAS_SLOT_MAX,
    archive_taken_slot,
    find_free_instance_idx,
    instance_dir,
    list_instances,
    mas_backup_root,
    recycle_orphan_slots,
)

logger = _utils_logger.get_logger("ZZZ-OD 自动代理")

_ALLOCATED_SLOT_LEDGER_DIR = "ZzzOdSlots"
"""槽分配台账的 MAS 数据目录：``data/ZzzOdSlots``（按安装根指纹分桶）"""


def _allocated_ledger_path(root: Path) -> Path:
    """安装根对应的槽分配台账文件：``data/ZzzOdSlots/{安装根指纹}.json``。"""

    return (
        Path.cwd()
        / "data"
        / _ALLOCATED_SLOT_LEDGER_DIR
        / f"{_utils_config_archive.config_root_key(root)}.json"
    )


def _allocated_slots(root: Path) -> dict[int, str | None]:
    """MAS 在本安装分配/绑定过的实例槽 → 归属用户 uid（台账）。

    台账是「这个号是 MAS 分的、归谁」的凭据，自动回收只收台账内 owner 已
    不存在的号：一条龙原生流程是「先建目录后写注册表」，用户在原生 GUI 新建
    实例的瞬间盘上已有目录、注册表尚未落盘，只看盘上目录会把它当残留删掉。
    台账缺失或损坏时返回空字典——自动回收退化为不收（残留由手动清理兜底），
    不会反向误删原生目录。

    owner 为 ``None`` 表示归属未知（旧格式台账，或调用方没给用户 uid）；
    这类号同样按「保留」处理，理由见 :func:`_recyclable_allocated_idxs`。
    """

    path = _allocated_ledger_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"槽分配台账不可读，本次按未分配处理: {e}")
        return {}
    slots = raw.get("slots") if isinstance(raw, dict) else None
    if isinstance(slots, list):
        # 旧格式（只有号、没有归属）：读成 owner 未知，下次写盘时升级
        return {
            int(i): None
            for i in slots
            if isinstance(i, int)
            and not isinstance(i, bool)
            and 0 < int(i) <= MAS_SLOT_MAX
        }
    if not isinstance(slots, dict):
        return {}
    ledger: dict[int, str | None] = {}
    for key, value in slots.items():
        try:
            slot = int(key)
        except (TypeError, ValueError):
            continue
        # 超出 MAS_SLOT_MAX 的号不是 MAS 槽（脏值）：写进 Info.SlotIdx 会被
        # RangeValidator 静默夹到上限，槽目录名与绑定号错位，一律当没有
        if slot <= 0 or slot > MAS_SLOT_MAX:
            continue
        # 归属必须是字符串：混进 bool/数字按未知处理，不让脏值决定保留与否
        ledger[slot] = value if isinstance(value, str) and value else None
    return ledger


def _save_allocated_slots(root: Path, slots: dict[int, str | None]) -> None:
    """落盘槽分配台账（写失败只告警：只影响后续自动回收范围，不该让运行失败）。"""

    path = _allocated_ledger_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"slots": {str(k): v for k, v in sorted(slots.items())}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"槽分配台账写入失败（不影响本次运行）: {e}")


def _record_allocated_slot(root: Path, slot_idx: int, owner: str | None = None) -> None:
    """把 MAS 分配/绑定的槽号与归属用户记进台账（幂等；无变化不写盘）。

    归属用于区分「用户还在、只是绑定号没回写」与「用户已删」两种无主形态，
    见 :func:`_recyclable_allocated_idxs`。
    """

    slot = int(slot_idx)
    if slot <= 0 or slot > MAS_SLOT_MAX:
        return
    owner = str(owner) if owner else None
    slots = _allocated_slots(root)
    if slot in slots and slots[slot] == owner:
        return
    slots[slot] = owner
    _save_allocated_slots(root, slots)


def forget_allocated_slot(root: Path, slot_idx: int) -> None:
    """把槽号移出台账（该号不再参与自动回收；幂等）。

    删除用户/脚本回收掉槽目录后调用：台账只记「MAS 手上还在用」的号，目录都
    没了就不该再占着。恢复快照走的是另一条路——它把内容恢复给某个用户并记上
    归属（见 :func:`app.task.ZzzOd.recovery.ZzzOdRecovery.restore_recycle`），不用
    本函数。手动清理不受台账限制。
    """

    slot = int(slot_idx)
    if slot <= 0:
        return
    slots = _allocated_slots(root)
    if slot not in slots:
        return
    del slots[slot]
    _save_allocated_slots(root, slots)


def _owner_alive(
    root: Path, owner: str, *, scripts: ConfigCollection[ConfigEntry]
) -> bool:
    """归属用户是否仍存在于指向同一份安装的任一 ZzzOd 脚本（按 uid 比对）。"""

    key = _utils_config_archive.config_root_key(root)
    for script_config in scripts.values():
        if not isinstance(script_config, ZzzOdConfig):
            continue
        script_root = str(script_config.Info.RootPath or "").strip()
        if not script_root or _utils_config_archive.config_root_key(script_root) != key:
            continue
        if any(str(uid) == owner for uid in script_config.UserData.keys()):
            return True
    return False


def _recyclable_allocated_idxs(
    root: Path, *, scripts: ConfigCollection[ConfigEntry]
) -> set[int]:
    """自动回收可收的台账号：归属用户已不存在的号。

    归属仍存在的号一律保留。运行/会话期用的是独立用户配置副本、绑定号要到
    ``final_task`` 才回写，崩溃或强杀会让槽呈「有目录、有台账、持久绑定查不到」
    的形态——只按持久绑定判定会把它当残留收走，而槽里还有用户在原生 GUI 里
    维护的配队。归属未知（``None``）同样保留：无法证明它无主时宁可不收。
    """

    return {
        slot
        for slot, owner in _allocated_slots(root).items()
        if owner is not None and not _owner_alive(root, owner, scripts=scripts)
    }


def _follow_mas_backups(script_id: str, old_slot: int, new_slot: int) -> None:
    """改绑后把该槽的 MAS 备份池挪到新槽号（用户的「配置恢复」历史跟着人走）。

    池按 ``(脚本, 槽)`` 分桶；留在旧号会让用户在新槽的「配置恢复」里看不到
    自己的历史，而旧号 MAS 已不再使用、池也不会再被清理。目标已存在时不动
    ——那是别人的历史，不能混在一起。
    """

    old_pool = mas_backup_root(script_id, old_slot)
    if not old_pool.is_dir():
        return
    new_pool = mas_backup_root(script_id, new_slot)
    if new_pool.exists():
        logger.warning(
            f"槽 {new_slot:02d} 已有 MAS 备份池，槽 {old_slot:02d} 的历史原地保留"
        )
        return
    try:
        shutil.move(str(old_pool), str(new_pool))
    except OSError as e:
        logger.opt(exception=True).warning(
            f"槽 {old_slot:02d} 的 MAS 备份池迁移到槽 {new_slot:02d} 失败: {e}"
        )


def _reclaim_own_slot(
    root: Path,
    owner_uid: str | None,
    native_idxs: set[int],
    used_idxs: set[int],
) -> int | None:
    """绑定号缺失时，认领回台账里属于本用户的高位段槽（中断现场恢复）。

    上次运行/会话被崩溃、断电或强杀打断时，绑定号只写在运行期副本里、没回写
    持久配置，用户下次运行会被当成「未分配」另拿一个新号——上一个槽里他在原生
    GUI 维护的配队就再也回不来了。这里优先认领台账里归本用户、且当前没被原生
    实例或其他用户占用的号（盘上有目录的优先，那里才有上次的配队），让配队
    跟着人走。没有任何候选时返回 ``None``，由调用方按常规分配新号。
    """

    if not owner_uid:
        return None
    owner = str(owner_uid)
    candidates = [
        slot
        for slot, slot_owner in _allocated_slots(root).items()
        if slot_owner == owner and slot not in native_idxs and slot not in used_idxs
    ]
    if not candidates:
        return None
    # 盘上有目录的优先（上次的配队在那里）；同为有目录时取号更大的那个——
    # 改绑只会往更大的号走，最大的最接近用户最后一次实际使用的槽
    with_dir = [slot for slot in candidates if instance_dir(root, slot).is_dir()]
    return max(with_dir or candidates)


async def ensure_user_slot(
    root: Path,
    user_config: ZzzOdUserConfig,
    used_idxs: set[int],
    *,
    script_id: str | None = None,
    owner_uid: str | None = None,
) -> int:
    """解析/分配用户的绑定实例槽（纯分配，不触碰注册表——注册表由合成视图提供）。

    绑定下标存于用户配置 ``Info.SlotIdx``：有效 = 不与原生实例、其他 MAS
    用户已绑定槽冲突；无效则优先认领台账里属于本用户的高位段槽（见
    :func:`_reclaim_own_slot`，用于上次没跑完的中断现场），没有则分配最小
    空闲 idx（全局查重）并把绑定落回用户配置。槽目录持久保留（配队等复杂
    配置），注册表只在运行/会话窗口内以合成视图出现。分配结果连同归属用户
    记进槽分配台账（含沿用旧绑定——一次运行即可把存量用户的绑定补进台账），
    供自动回收判定「这个号是 MAS 分的、还归不归活着的用户」。

    新槽从 :data:`MAS_SLOT_BASE` 起分配——一条龙的「新增实例」只按自己的
    注册表找最小空号、看不见 MAS 槽，低号段随时可能被抢，退到高位段让它
    够不到。绑定号已经被原生实例抢走时，先把残留内容存底进回收池、再把该
    槽的 MAS 备份池挪到新号（配队与「配置恢复」历史都跟着用户走）；此时
    槽目录已归原生实例，只存底不删。

    Args:
        root: 一条龙安装目录。
        user_config: 用户配置对象（绑定号读写在 ``Info.SlotIdx``）。
        used_idxs: 本次批量已分配的槽号集合，就地更新。
        script_id: 所属脚本 ID，仅用于搬迁该脚本的 MAS 备份池；缺省跳过。
        owner_uid: 用户 uid，写进台账作为该槽的归属；缺省则归属未知。
    """

    bound = int(user_config.Info.SlotIdx or -1)
    native_idxs = {
        int(item.get("idx", -1))
        for item in list_instances(root)
        if isinstance(item, dict)
    }
    if bound > 0 and bound not in native_idxs and bound not in used_idxs:
        slot = bound
    else:
        taken = bound > 0 and bound in native_idxs
        # 绑定号缺失（首跑，或上次崩溃没回写）时先认领自己名下的旧槽；
        # 被原生实例抢走是「绑定号还在」的另一回事，走下面的撞号兜底
        reclaimed = (
            None
            if taken
            else _reclaim_own_slot(root, owner_uid, native_idxs, used_idxs)
        )
        slot = (
            reclaimed
            if reclaimed is not None
            else find_free_instance_idx(
                root, used_idxs, base=MAS_SLOT_BASE, limit=MAS_SLOT_MAX
            )
        )
        if taken:
            user_name = str(user_config.Info.Name or "未知用户")
            archive_taken_slot(
                root,
                bound,
                reason=f"槽号已被原生实例占用，用户「{user_name}」改绑高位段",
            )
            if script_id:
                _follow_mas_backups(script_id, bound, slot)
    used_idxs.add(slot)
    if slot != bound:
        user_config.Info.SlotIdx = slot
        await user_config.commit()
    _record_allocated_slot(root, slot, owner_uid)
    return slot


def collect_used_slot_idxs(
    root: Path,
    exclude_uids: set[uuid.UUID] | None = None,
    *,
    scripts: ConfigCollection[ConfigEntry],
) -> set[int]:
    """收集指向同一份安装的 ZzzOd 脚本用户已绑定的实例槽 idx（分配查重用）。

    槽目录挂在某一份安装的 ``config/`` 下，占用判定必须按安装分桶：指向别的
    安装的脚本用户不该挤占本安装的号（旧口径跨全部 ZzzOd 脚本一起去重，
    多脚本各指一份安装时会把号白白占掉，新用户只能被挤到更大的 idx）。
    ``root`` 用 :func:`_utils_config_archive.config_root_key` 归一比对。本次要注入/会话的用户经
    ``exclude_uids`` 排除——它们通过自身 SlotIdx 重认领绑定。
    """

    key = _utils_config_archive.config_root_key(root)
    used: set[int] = set()
    excluded = exclude_uids or set()
    for script_config in scripts.values():
        if not isinstance(script_config, ZzzOdConfig):
            continue
        script_root = str(script_config.Info.RootPath or "").strip()
        if not script_root or _utils_config_archive.config_root_key(script_root) != key:
            continue
        for uid, cfg in script_config.UserData.items():
            if uid in excluded:
                continue
            bound = int(cfg.Info.SlotIdx or -1)
            if bound > 0:
                used.add(bound)
    return used


def collect_slot_owners(
    root: Path, *, scripts: ConfigCollection[ConfigEntry]
) -> dict[int, list[dict]]:
    """按安装根分桶收集槽的 MAS 归属（idx → 归属列表）。

    与 :func:`collect_used_slot_idxs` 同口径（只算指向同一份安装的脚本），
    但带出脚本/用户名与配置来源，供实例槽总览展示「这个号被谁占着」。
    **绑定但盘上无目录的槽也要能列出来**——那正是「槽目录数与用户数对不上」
    时最需要看到的一行（没跑过的用户只有绑定号、没有目录）。
    """

    key = _utils_config_archive.config_root_key(root)
    owners: dict[int, list[dict]] = {}
    for script_uid, script_config in scripts.items():
        if not isinstance(script_config, ZzzOdConfig):
            continue
        script_root = str(script_config.Info.RootPath or "").strip()
        if not script_root or _utils_config_archive.config_root_key(script_root) != key:
            continue
        script_name = str(script_config.Info.Name or "")
        for uid, cfg in script_config.UserData.items():
            bound = int(cfg.Info.SlotIdx or -1)
            if bound <= 0:
                continue
            owners.setdefault(bound, []).append(
                {
                    "scriptId": str(script_uid),
                    "userId": str(uid),
                    "scriptName": script_name,
                    "userName": str(cfg.Info.Name or ""),
                    "base": str(cfg.Info.Base or _utils_constants.BASE_INDEPENDENT),
                }
            )
    return owners


def running_zzzod_scripts(
    root: Path,
    exclude_script_id: str | None = None,
    *,
    scripts: ConfigCollection[ConfigEntry],
) -> list[str]:
    """指向同一份安装、且正在运行/开会话的 ZzzOd 脚本名（``exclude_script_id`` 排除自己）。

    槽目录跨脚本共享同一份安装，而运行/会话期用的是**独立用户配置副本**
    （manager ``prepare`` 提取、``final_task`` 才回写），在跑脚本的在用槽在
    持久配置里查不到绑定——别的脚本此时回收孤儿槽会把它们当残留收走，拆掉
    正在跑的现场。自动回收据此跳过本轮（见 :func:`recycle_unbound_slots`）。
    """

    key = _utils_config_archive.config_root_key(root)
    running: list[str] = []
    for script_uid, script_config in scripts.items():
        if not isinstance(script_config, ZzzOdConfig) or not script_config.is_locked:
            continue
        if exclude_script_id and str(script_uid) == str(exclude_script_id):
            continue
        script_root = str(script_config.Info.RootPath or "").strip()
        if script_root and _utils_config_archive.config_root_key(script_root) == key:
            running.append(str(script_config.Info.Name or script_uid))
    return running


def recycle_unbound_slots(
    root: Path,
    *,
    scripts: ConfigCollection[ConfigEntry],
    only_allocated: bool = True,
    swallow: bool = True,
    exclude_script_id: str | None = None,
) -> list[int]:
    """回收盘上无人绑定的实例槽（运行/会话前自动回收与手动清理共用）。

    绑定集合取全部 ZzzOd 用户（**不排除**本次要注入/会话的用户）：排除会把
    它们正在用的槽当孤儿回收，槽里的配队等随即丢失。在 ``ensure_user_slot``
    之前调用时，腾出的号本轮即可复用。原生态不自动调用——原生态是纯原生裸跑，
    MAS 不往安装目录里删东西；手动清理是用户显式发起的动作，不受此限。
    同安装另有 ZzzOd 脚本在跑时整体跳过：它在用槽的绑定号尚未回写，收了会
    拆掉它的现场（残留交手动清理兜底）。

    Args:
        root: 一条龙安装目录。
        only_allocated: 自动路径默认只收台账里归属用户已不存在的号（见
            :func:`_recyclable_allocated_idxs`）；手动清理传 ``False`` 连来路
            不明的残留一起收。
        swallow: 默认失败只告警，不阻断运行/会话；手动清理传 ``False``，
            让注册表缺失/损坏等原因抛到界面。
        exclude_script_id: 调用方自己的脚本 ID——自动路径的调用方本身处于
            锁定态，判定同安装在跑脚本时必须排除自己。

    Returns:
        实际回收的槽下标。

    Raises:
        ValueError: 注册表缺失且 ``swallow=False``。
        ConfigCorruptedError: 注册表不可读且 ``swallow=False``。
        RuntimeError: 同安装有别的 ZzzOd 脚本在跑且 ``swallow=False``。
    """

    running = running_zzzod_scripts(root, exclude_script_id, scripts=scripts)
    if running:
        message = (
            f"同安装的「{'、'.join(running)}」正在运行，本轮跳过无主槽回收"
            "（其在用槽的绑定号尚未回写，收了会拆掉在跑的现场）"
        )
        if not swallow:
            raise RuntimeError(message)
        logger.warning(message)
        return []
    allocated = (
        _recyclable_allocated_idxs(root, scripts=scripts) if only_allocated else None
    )
    try:
        removed = recycle_orphan_slots(
            root,
            collect_used_slot_idxs(root, scripts=scripts),
            allocated_idxs=allocated,
            swallow=swallow,
        )
    except Exception as e:
        if not swallow:
            raise
        logger.opt(exception=True).warning(f"孤儿实例槽回收失败: {e}")
        return []
    if removed:
        logger.info(f"已回收 {len(removed)} 个未绑定的实例槽: {removed}")
    return removed
