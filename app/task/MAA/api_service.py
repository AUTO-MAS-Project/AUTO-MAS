#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""MAA 专项的 API 业务实现。

app/api/scripts.py 中的 MAA 端点只做三件事：解析请求参数、调用本模块的一个函数、
把返回值装进响应模型；需要 MAA 领域知识的逻辑（配置来源判定、原生配置读写、排班表
解析、物品资源解析、森空岛绑定）都在这里实现。

依赖方向只能是 app.api → 本模块，本模块不得反向导入 app.api；对
app.task.MAA.tools 的导入留在各函数内惰性进行。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from app.core import Config
from app.models.config import (
    MaaConfig,
    infrast_format_problem,
    infrast_plan_state,
    load_infrast_plans,
    maa_scheme_name,
    maa_task_queue,
    read_maa_config,
)
from app.utils import get_logger
from app.utils.constants import MAA_DEPOT_EXCLUDED_ITEM_IDS, game_now
from app.utils.io import write_file

logger = get_logger("脚本管理 API")

# MAA 的 resource/item_index.json 约 220 KB，编辑页与预览每次都要用；
# 按文件 mtime 缓存解析结果，选择器与名称映射共用这一份
_item_index_cache: dict[Path, tuple[int, dict[str, Any]]] = {}


def _maa_script_config(script_id: str) -> MaaConfig:
    """解析 MAA 脚本配置并拒绝跨类型 ID 访问。"""

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, MaaConfig):
        raise TypeError(f"脚本 {script_id} 不是 MAA 脚本")
    return script_config


def _load_item_index(script_config: MaaConfig) -> dict[str, Any]:
    """读 MAA 物品资源表 resource/item_index.json（按文件 mtime 缓存）。"""

    path = Path(script_config.get("Info", "Path")) / "resource" / "item_index.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到 MAA 物品资源: {path}，请更新 MAA 后重试")
    mtime_ns = path.stat().st_mtime_ns
    cached = _item_index_cache.get(path)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, dict):
        raise ValueError(f"MAA 物品资源格式异常: {path}")
    _item_index_cache[path] = (mtime_ns, items)
    return items


async def set_infrastructure(script_id: str, user_id: str, jsonFile: str) -> None:
    logger.info(f"{script_id} - {user_id} 设置基建配置: {jsonFile}")

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)
    json_path = Path(jsonFile)

    if not json_path.exists():
        raise FileNotFoundError(f"文件未找到: {json_path}")

    if not isinstance(Config.ScriptConfig[script_uid], MaaConfig):
        raise TypeError(f"脚本 {script_id} 不是 MAA 脚本, 无法设置基建配置")

    try:
        infrast_data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError("排班表不是有效的 JSON") from e

    problem = infrast_format_problem(infrast_data)
    if problem is not None:
        raise ValueError(problem)

    # 如果标题为默认标题, 则使用文件名作为标题
    if infrast_data.get("title", "文件标题") == "文件标题":
        infrast_data["title"] = json_path.stem

    await (
        Config.ScriptConfig[script_uid]
        .UserData[user_uid]
        .set("Data", "CustomInfrast", json.dumps(infrast_data, ensure_ascii=False))
    )


def _infrast_config_dir(script_id: str, user_id: str) -> Path:
    """基建班次的事实源目录: 托管=配置来源存档, 直控=MAA 当前生效配置。

    与 AutoProxy._config_archive_dir 的来源判定对称; 直控不落存档,
    MAA 安装目录的现有配置即持久存储。
    """

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)
    script_config = Config.ScriptConfig[script_uid]
    if isinstance(script_config, MaaConfig) and user_uid in script_config.UserData:
        mode = script_config.UserData[user_uid].get("Info", "Mode")
        if mode == "脚本":
            return Path.cwd() / f"data/{script_id}/Default/ConfigFile"
        if mode == "直控":
            return Path(script_config.get("Info", "Path")) / "config"
    return Path.cwd() / f"data/{script_id}/{user_id}/ConfigFile"


def _infrast_plans(script_id: str, user_id: str) -> tuple[list[dict], str | None, str]:
    """生效排班表 (plans, problem, state), 与运行时使用的那份同源。

    直控且关闭快速配置时 set_maa 跳过注入, 运行时直接用 MAA 原生配置,
    排班表只存在原生的 Infrast 任务里(InfrastPlan 不落盘, 事实源是
    Filename 指向的排班文件); 其余组合(托管 / 直控+快速配置)都由 MAS
    注入存档排班表。若不加区分地对直控读 MAS 存档, 直控用户的班次会被
    空存档误拒; 反过来在直控+快速配置下读原生配置, 又会与运行时不一致。
    """

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    user_config = script_config.UserData[uuid.UUID(user_id)]
    if user_config.get("Info", "Mode") != "直控" or user_config.get(
        "Info", "IfQuickConfig"
    ):
        raw = user_config.get("Data", "CustomInfrast")
        plans, problem = load_infrast_plans(raw)
        return plans, problem, infrast_plan_state(raw)

    config_dir = _infrast_config_dir(script_id, user_id)
    data = read_maa_config(config_dir / "gui.new.json")
    if data is None:
        return [], "未找到或无法读取 MAA 原生配置", "empty"
    queue = maa_task_queue(data, maa_scheme_name(config_dir, data))
    if not isinstance(queue, list):
        return [], "MAA 原生配置缺少任务队列", "empty"
    for task in queue:
        if not isinstance(task, dict) or task.get("TaskType") != "Infrast":
            continue
        if task.get("Mode") != "Custom":
            return [], "MAA 原生配置未启用自定义基建", "empty"
        filename = task.get("Filename")
        if not isinstance(filename, str) or not filename.strip():
            return [], "MAA 原生配置没有指定排班文件", "empty"
        path = Path(filename.strip())
        if not path.is_file():
            return [], f"MAA 原生排班文件不存在: {path.name}", "empty"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.opt(exception=True).warning(f"读取 MAA 原生排班文件失败: {path}")
            return [], f"MAA 原生排班文件无法读取: {path.name}", "empty"
        plans, problem = load_infrast_plans(text)
        return plans, problem, infrast_plan_state(text)
    return [], "MAA 原生配置中没有基建任务", "empty"


def _infrast_plan_owned_by_mas(script_id: str, user_id: str) -> bool:
    """班次指针是否由 MAS 用户字段管理, 与 set_maa 的注入判定同源。

    快速配置开着时 MAS 注入排班表, 班次由 MAS 决定: 带时段表一律交 MAA 按
    时段选班, 无时段表注入用户自己的 ``Data.InfrastPlanIndex``。关着时 MAS
    不注入, MAA 跑的是来源配置自己的队列, 班次仍在那份配置的 PlanSelect 里。
    """

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    user_config = script_config.UserData[uuid.UUID(user_id)]
    return bool(user_config.get("Info", "IfQuickConfig"))


async def set_infrast_plan_select(script_id: str, user_id: str, index: int) -> int:
    """把用户选定的基建班次写入该用户的事实源。

    index 与 MAA 原生语义一致: -1=自动, 0..n-1=从该班开始顺序轮换。MAS 注入
    的组合下事实源是用户配置的 ``Data.InfrastPlanIndex``(每用户一份, 推进由
    MAS 在基建换班完成后做), 带时段表只接受 -1; 直控且关快速配置时写 MAA
    原生配置。写不进去时抛异常(而不是返回入参假装成功), 由接口层转成错误响应。
    """

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, MaaConfig):
        raise TypeError(f"脚本 {script_id} 不是 MAA 脚本, 无法设置基建班次")
    if index < -1:
        raise ValueError("基建班次索引不能小于 -1")
    if user_uid not in script_config.UserData:
        raise ValueError(f"脚本 {script_id} 下不存在用户 {user_id}")

    # 显式班次要落在 -1..班次数-1 内: MAA 侧只会把越界值静默修正成第一班
    # 或直接报错, 与其静默改掉用户的选择不如在入口拒绝; -1 是默认值无需校验
    plans, problem, state = _infrast_plans(script_id, user_id)
    if index >= 0:
        if problem is not None:
            raise ValueError(f"自定义基建排班不可用, 无法设置基建班次: {problem}")
        if index >= len(plans):
            raise ValueError(
                f"基建班次索引 {index} 超出排班表范围, 该排班表共 {len(plans)} 个班次"
            )

    if _infrast_plan_owned_by_mas(script_id, user_id):
        if state == "period":
            if index >= 0:
                raise ValueError(
                    "带时间段的排班表由 MAA 按时段自动换班, 不支持手选班次"
                )
            return -1
        # 无时段表: -1(自动)即从第一班起, 指针只存 0..n-1
        next_index = max(index, 0)
        await script_config.UserData[user_uid].set(
            "Data", "InfrastPlanIndex", next_index
        )
        return next_index

    config_dir = _infrast_config_dir(script_id, user_id)
    data = read_maa_config(config_dir / "gui.new.json")
    if data is None:
        raise ValueError("未找到或无法读取该用户的 MAA 配置, 无法设置基建班次")
    scheme = maa_scheme_name(config_dir, data)
    queue = maa_task_queue(data, scheme)
    if not isinstance(queue, list):
        raise ValueError(f"MAA 配置的方案「{scheme}」缺少任务队列, 无法设置基建班次")
    tasks = [
        task
        for task in queue
        if isinstance(task, dict) and task.get("TaskType") == "Infrast"
    ]
    if not tasks:
        raise ValueError(f"MAA 配置的方案「{scheme}」中没有基建任务, 无法设置基建班次")
    if all(task.get("PlanSelect") == index for task in tasks):
        return index
    for task in tasks:
        task["PlanSelect"] = index
    write_file(config_dir / "gui.new.json", data)
    return index


async def get_infrast_plan_select(script_id: str, user_id: str) -> int:
    """读取当前基建班次索引; 带时段表 / 未设置过时返回 -1(自动)。

    MAS 注入的组合下, 无时段表返回用户字段里的指针(下次从该班开始);
    直控且关快速配置时读 MAA 原生配置。
    """

    script_uid = uuid.UUID(script_id)
    if script_uid not in Config.ScriptConfig:
        return -1
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, MaaConfig):
        return -1
    user_uid = uuid.UUID(user_id)
    if user_uid not in script_config.UserData:
        return -1
    if _infrast_plan_owned_by_mas(script_id, user_id):
        plans, problem, state = _infrast_plans(script_id, user_id)
        if problem is not None or state != "rotate":
            return -1
        return int(
            script_config.UserData[user_uid].get("Data", "InfrastPlanIndex")
        ) % len(plans)
    config_dir = _infrast_config_dir(script_id, user_id)
    data = read_maa_config(config_dir / "gui.new.json")
    if data is None:
        return -1
    queue = maa_task_queue(data, maa_scheme_name(config_dir, data))
    if not isinstance(queue, list):
        return -1
    for task in queue:
        if isinstance(task, dict) and task.get("TaskType") == "Infrast":
            plan_select = task.get("PlanSelect")
            return int(plan_select) if isinstance(plan_select, int) else -1
    return -1


async def get_user_combox_infrastructure(script_id: str, user_id: str) -> dict:
    logger.info(f"获取用户自定义基建排班下拉框信息: {script_id} - {user_id}")

    script_uid = uuid.UUID(script_id)
    user_uid = uuid.UUID(user_id)

    script_config = Config.ScriptConfig[script_uid]

    # 根据脚本类型选择添加对应用户配置
    if not isinstance(script_config, MaaConfig):
        raise TypeError(f"不支持的脚本配置类型: {type(script_config)}")

    logger.info("开始获取用户自定义基建排班下拉框信息")

    user_config = script_config.UserData[user_uid]
    plans, problem, state = _infrast_plans(script_id, user_id)
    # 仅自定义模式下不可用才值得提醒; 普通模式空排班表是正常状态
    if problem is not None and user_config.get("Info", "InfrastMode") == "Custom":
        logger.warning(f"自定义基建排班不可用, 下拉选项按空返回: {problem}")
    data = []
    for i, plan in enumerate(plans):
        ranges = plan.get("period")
        period = ""
        if isinstance(ranges, list):
            period = ", ".join(
                f"{r[0]}-{r[1]}" for r in ranges if isinstance(r, list) and len(r) >= 2
            )
        data.append(
            {
                "label": plan.get("name", f"排班 {i + 1}"),
                "value": str(i),
                "period": period or None,
            }
        )

    logger.success("用户自定义基建排班下拉框信息获取成功")

    return {"state": state, "data": data}


async def get_depot_items(script_id: str) -> list[dict[str, str]]:
    """获取 MAA 库存保持物品选项。"""

    items = _load_item_index(_maa_script_config(script_id))
    return [
        {"label": item.get("name") or item_id, "value": item_id}
        for item_id, item in sorted(
            (
                (item_id, item)
                for item_id, item in items.items()
                if item_id.isdigit()
                and item_id not in MAA_DEPOT_EXCLUDED_ITEM_IDS
                and isinstance(item, dict)
            ),
            key=lambda entry: int(entry[0]),
        )
    ]


async def get_depot_stage_candidates(
    script_id: str, item_id: str
) -> list[dict[str, str]]:
    """获取掉落指定材料的关卡候选（按单件期望理智升序，即 xx 理智/件）。

    编排逻辑在 tools.cultivate.service；本函数只做脚本定位与转发，
    保持既有对外契约不变。
    """

    _maa_script_config(script_id)

    from app.task.MAA.tools.cultivate import depot_cultivate_service

    return await depot_cultivate_service.stage_candidates(
        config_path=Config.config_path,
        item_id=item_id,
        proxy=Config.proxy,
    )


async def get_depot_inventory(
    script_id: str, user_id: str
) -> tuple[list[dict[str, str]], str | None]:
    """获取当前用户档案的仓库库存（label=数量，value=物品ID）与识别时间。

    查询链只读用户档案（决策 31）：多用户共用 MAA 安装时不再可能读到
    他人数字；档案由运行期识别采集写入（T1.17），缺失 = 该用户未识别。
    """

    _maa_script_config(script_id)

    from app.task.MAA.tools.cultivate import depot_cultivate_service

    archive_dir = Path.cwd() / f"data/{uuid.UUID(script_id)}/{uuid.UUID(user_id)}"
    result = await depot_cultivate_service.inventory(maa_data_dir=archive_dir)
    if result is None:
        raise FileNotFoundError(
            f"未找到用户识别档案: {archive_dir / 'DepotData.json'}，"
            "请先运行一次代理完成仓库识别"
        )
    inventory, recognized_at = result
    recognized_iso = (
        datetime.fromtimestamp(recognized_at).isoformat(timespec="seconds")
        if recognized_at > 0
        else None
    )
    items = [
        {"label": str(count), "value": item_id}
        for item_id, count in sorted(inventory.items())
    ]
    return items, recognized_iso


async def get_cultivate_operators(
    script_id: str, user_id: str
) -> list[dict[str, object]]:
    """获取干员养成选择器目录（一图流全量表兜底，方案决策 11/38）。

    goal-aware 过滤：无森空岛快照时退化"剔已精 2"，绑定后按
    "精2 ∧ 专精全满 ∧ 模组全满"剔除；skills/modules 为目标编辑行
    展示用名称目录（仅 UI 消费，不进内核契约）。
    """

    from app.task.MAA.tools.cultivate import (
        depot_cultivate_service,
        parse_cultivate_targets,
    )

    script_config = _maa_script_config(script_id)

    skland = await get_cultivate_skland_progression(script_id, user_id)
    archive_dir = Path.cwd() / f"data/{uuid.UUID(script_id)}/{uuid.UUID(user_id)}"
    # 已存目标引用的干员一律保留在选择器目录里：目录同时是编辑行的名称
    # 来源，被过滤掉的干员会让已存目标显示成内部 ID（决策 40）
    try:
        raw_targets = json.loads(
            script_config.UserData[uuid.UUID(user_id)].get("Task", "CultivateTargets")
            or "[]"
        )
    except (KeyError, TypeError, ValueError):
        raw_targets = []
    keep_ids = [target.operator_id for target in parse_cultivate_targets(raw_targets)]
    catalog = await depot_cultivate_service.operator_catalog(
        config_path=Config.config_path,
        proxy=Config.proxy,
        maa_data_dir=archive_dir,
        skland=skland,
        keep_ids=keep_ids,
    )
    return [item for item in catalog if item.get("label") and item.get("value")]


async def _item_names(script_id: str) -> dict[str, str]:
    """MAA 物品 id→名称全量映射（不受选择器排除规则影响，预览展示用）。"""

    items = _load_item_index(_maa_script_config(script_id))
    return {
        item_id: str(entry.get("name") or item_id)
        for item_id, entry in items.items()
        if isinstance(entry, dict)
    }


def _cultivate_skland_callbacks() -> tuple[
    Callable[[str], Awaitable[str | None]],
    Callable[[str, str], Awaitable[None]],
]:
    """构造森空岛凭据的读/写回调（签名 token 本体只存签到域，决策 38）。

    读走 EncryptValidator 的自动解密，写走 set 时的自动加密；账号组
    不存在时读返回 None、写静默跳过（绑定引用失效的降级口径）。
    """

    async def load_credential(account_uid: str) -> str | None:
        try:
            account = Config.ToolsConfig.GameSign_Accounts[uuid.UUID(account_uid)]
        except (KeyError, ValueError):
            return None
        raw = account.get("GameSignAccount", "SklandToken")
        return str(raw) if raw else None

    async def save_credential(account_uid: str, serialized: str) -> None:
        try:
            account = Config.ToolsConfig.GameSign_Accounts[uuid.UUID(account_uid)]
        except (KeyError, ValueError):
            return
        await account.set("GameSignAccount", "SklandToken", serialized)

    return load_credential, save_credential


def _cultivate_skland_ref(
    script_config: MaaConfig, user_id: str
) -> tuple[str, str] | None:
    """读用户配置的森空岛绑定；未绑定时返回 None。"""

    user_config = script_config.UserData[uuid.UUID(user_id)]
    account_uid = str(user_config.get("Task", "CultivateSklandAccount") or "").strip()
    game_uid = str(user_config.get("Task", "CultivateSklandUid") or "").strip()
    if not account_uid or not game_uid:
        return None
    return account_uid, game_uid


async def get_cultivate_skland_progression(
    script_id: str, user_id: str, *, force: bool = False
) -> tuple[Mapping[str, Any], int] | None:
    """取当前用户绑定的森空岛练度快照（带 TTL 缓存）；未绑定返回 None。

    预览走缓存（force=False），注入前强刷（force=True，决策 38）；
    拉取失败由驱动层降级为 None，绝不影响注入/预览主流程。
    """

    from app.task.MAA.tools.cultivate.skland import (
        SklandAccountRef,
        fetch_skland_progression,
    )

    script_config = _maa_script_config(script_id)
    ref = _cultivate_skland_ref(script_config, user_id)
    if ref is None:
        return None
    load_credential, save_credential = _cultivate_skland_callbacks()
    return await fetch_skland_progression(
        SklandAccountRef(account_uid=ref[0], game_uid=ref[1]),
        load_credential=load_credential,
        save_credential=save_credential,
        proxy=Config.proxy,
        force=force,
    )


async def get_cultivate_skland_bindings() -> list[dict[str, str]]:
    """列出所有已配置森空岛凭据的账号组的明日方舟角色（绑定下拉用）。

    账号级遍历而非读取用户绑定——角色列表正是绑定的来源。选项 value
    为 "账号组UUID|游戏uid" 复合值，保存时由前端拆回两个字段；同名
    角色（同号重复入组）按 uid 去重；单账号组失败跳过不阻塞其他组。
    未配置任何森空岛凭据或没拉到角色时抛错，由路由统一转错误响应。
    """

    from app.task.MAA.tools.cultivate.skland import fetch_skland_role_entries

    load_credential, save_credential = _cultivate_skland_callbacks()
    candidates: list[str] = []
    for account_uid, account in Config.ToolsConfig.GameSign_Accounts.items():
        raw = str(account.get("GameSignAccount", "SklandToken") or "")
        if raw:
            candidates.append(str(account_uid))
    if not candidates:
        raise ValueError("签到设置中尚未配置森空岛凭据，请先在签到设置中添加")

    options: list[dict[str, str]] = []
    seen_roles: set[str] = set()
    for account_uid in candidates:
        try:
            roles = await fetch_skland_role_entries(
                account_uid,
                load_credential=load_credential,
                save_credential=save_credential,
                proxy=Config.proxy,
            )
        except Exception as e:
            logger.warning(f"账号组 {account_uid} 的森空岛角色拉取失败，已跳过: {e}")
            continue
        for role in roles:
            uid = str(role.role_uid or "").strip()
            if not uid or uid in seen_roles:
                continue
            seen_roles.add(uid)
            name = role.role_name or uid
            options.append({"label": name, "value": f"{account_uid}|{uid}"})
    if not options:
        raise ValueError(
            "未在签到账号组中找到明日方舟角色，请确认森空岛账号已绑定游戏角色"
        )
    return options


async def get_cultivate_preview(
    script_id: str, user_id: str, targets: str
) -> dict[str, object]:
    """养成计划预览（纯计算不落库，方案 §4.3）。

    与注入同一管线；编排逻辑在 tools.cultivate.service，本方法
    只做脚本/档案定位与解析，保持对外契约。
    """

    from app.task.MAA.tools.cultivate import (
        depot_cultivate_service,
        parse_cultivate_targets,
    )

    script_config = _maa_script_config(script_id)

    try:
        raw_targets = json.loads(targets)
    except (TypeError, ValueError):
        raw_targets = []

    archive_dir = Path.cwd() / f"data/{uuid.UUID(script_id)}/{uuid.UUID(user_id)}"
    # 森空岛练度走 TTL 缓存（预览不打网络；决策 38），未绑定/失败降级 None
    skland = await get_cultivate_skland_progression(script_id, user_id)
    (
        plan,
        availability,
        progressions,
    ) = await depot_cultivate_service.preview_cultivate(
        targets=parse_cultivate_targets(raw_targets),
        maa_data_dir=archive_dir,
        config_path=Config.config_path,
        proxy=Config.proxy,
        today=game_now(
            script_config.UserData[uuid.UUID(user_id)].get("Info", "Server")
        ).date(),
        skland=skland,
    )
    # 目标干员当前练度（编辑器"当前等级 → 目标等级"展示用）；
    # source=default 表示无实测数据，前端按"？"展示
    progression_out = [
        {
            "operatorId": operator_id,
            "source": snapshot.source,
            "elite": snapshot.data.elite,
            "level": snapshot.data.level,
            "masteries": dict(snapshot.data.masteries),
            "modules": dict(snapshot.data.modules),
        }
        for operator_id, snapshot in progressions.items()
    ]
    if plan is None:
        # 空计划先短路：物品索引读不出来也不该把空预览变 500
        return {
            "stages": [],
            "demands": [],
            "unobtainable": [],
            "progressions": progression_out,
            "availability": availability,
        }
    # 物品名从 item_index 全量取（双芯片等选择器排除项也有名称）
    names = await _item_names(script_id)

    def named(
        item_id: str,
        count: int,
        stage: str | None = None,
        expected_sanity: float | None = None,
    ) -> dict[str, object]:
        item: dict[str, object] = {
            "itemId": item_id,
            "name": names.get(item_id, item_id),
            "count": count,
        }
        if stage is not None:
            item["stage"] = stage
        if expected_sanity is not None:
            item["expectedSanity"] = expected_sanity
        return item

    # 固定产出关（龙门币 ← CE-6 等）单次产量未知，内核保持 0.0 中性值，
    # 展示层按"不可估算"处理（None），不计入合计
    computable_sanity = [
        entry.expected_sanity for entry in plan.entries if entry.expected_sanity > 0
    ]

    return {
        "stages": [
            named(
                entry.item_id,
                entry.amount,
                entry.stage_code,
                entry.expected_sanity or None,
            )
            for entry in plan.entries
        ],
        "demands": [named(req.item_id, req.amount) for req in plan.demands],
        "unobtainable": [named(req.item_id, req.amount) for req in plan.unobtainable],
        "totalExpectedSanity": (
            round(sum(computable_sanity), 1) if computable_sanity else None
        ),
        "progressions": progression_out,
        "availability": availability,
    }
