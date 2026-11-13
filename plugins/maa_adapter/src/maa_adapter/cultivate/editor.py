import json
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from auto_mas_core.host.core import Config
from auto_mas_core.host.utils import get_logger

from maa_adapter.config.access import _maa_script_config
from maa_adapter.config.script import MaaConfig
from maa_adapter.constants import game_now
from maa_adapter.cultivate.inventory import _item_names

logger = get_logger("MAA")


async def refresh_cultivate_data(script_id: str) -> None:
    """刷新共享养成数据与托管内已绑定角色的练度，练度失败沿用旧快照。"""

    from maa_adapter.cultivate.skland import SklandAccountRef, fetch_skland_progression
    from maa_adapter.cultivate.yituliu import refresh_data

    script_config = _maa_script_config(script_id)
    await refresh_data(Config.config_path, Config.proxy)
    bindings = {
        binding
        for user_id in script_config.UserData.keys()
        if (binding := _cultivate_skland_ref(script_config, str(user_id))) is not None
    }
    load_credential, save_credential = _cultivate_skland_callbacks()
    for account_uid, game_uid in bindings:
        await fetch_skland_progression(
            SklandAccountRef(account_uid=account_uid, game_uid=game_uid),
            load_credential=load_credential,
            save_credential=save_credential,
            proxy=Config.proxy,
            force=True,
            fallback_to_cached=True,
        )


async def get_cultivate_operators(
    script_id: str, user_id: str
) -> list[dict[str, object]]:
    """获取干员养成选择器目录（一图流全量表兜底，方案决策 11/38）。

    goal-aware 过滤：技能等级未观测或未满时保留，绑定后按
    "精英化、技能等级、专精与模组均已满"剔除；skills/modules 为目标编辑行
    展示用名称目录（仅 UI 消费，不进内核契约）。
    """

    from maa_adapter.cultivate import depot_cultivate_service, parse_cultivate_targets

    script_config = _maa_script_config(script_id)

    skland = await get_cultivate_skland_progression(script_id, user_id)
    archive_dir = Path.cwd() / f"data/{uuid.UUID(script_id)}/{uuid.UUID(user_id)}"
    # 已存目标引用的干员一律保留在选择器目录里：目录同时是编辑行的名称
    # 来源，被过滤掉的干员会让已存目标显示成内部 ID（决策 40）
    try:
        raw_targets = json.loads(
            script_config.UserData[uuid.UUID(user_id)].Task.CultivateTargets or "[]"
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


async def parse_cultivate_import(script_id: str, content: str) -> dict[str, Any]:
    """转换剪贴板目标，不写账号配置；完整目录避免过滤掉已满级干员。"""

    from maa_adapter.cultivate import (
        depot_cultivate_service,
        dump_cultivate_targets,
        parse_clipboard_targets,
    )

    _maa_script_config(script_id)
    catalog = await depot_cultivate_service.operator_catalog(
        config_path=Config.config_path, proxy=Config.proxy
    )
    targets, skipped = parse_clipboard_targets(content, catalog)
    imported_ids = {target.operator_id for target in targets}
    return {
        "targets": json.dumps(dump_cultivate_targets(targets), ensure_ascii=False),
        "data": [entry for entry in catalog if entry["value"] in imported_ids],
        "skipped": [
            {"error": item.reason, "index": item.index, "name": item.name}
            for item in skipped
        ],
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
        """从已绑定的签到账号读取森空岛凭据，账号不存在或未保存凭据时返回空值。"""
        try:
            account = Config.ToolsConfig.GameSign_Accounts[uuid.UUID(account_uid)]
        except (KeyError, ValueError):
            return None
        raw = account.GameSignAccount.SklandToken
        return str(raw) if raw else None

    async def save_credential(account_uid: str, serialized: str) -> None:
        """将刷新后的森空岛凭据保存回仍存在的绑定账号。"""
        try:
            account = Config.ToolsConfig.GameSign_Accounts[uuid.UUID(account_uid)]
        except (KeyError, ValueError):
            return
        await account.update(
            type(account).model_validate(
                {"GameSignAccount": {"SklandToken": serialized}}
            ),
            check_visibility=False,
        )

    return load_credential, save_credential


def _cultivate_skland_ref(
    script_config: MaaConfig, user_id: str
) -> tuple[str, str] | None:
    """读用户配置的森空岛绑定；未绑定时返回 None。"""

    user_config = script_config.UserData[uuid.UUID(user_id)]
    account_uid = str(user_config.Task.CultivateSklandAccount or "").strip()
    game_uid = str(user_config.Task.CultivateSklandUid or "").strip()
    if not account_uid or not game_uid:
        return None
    return account_uid, game_uid


async def get_cultivate_skland_progression(
    script_id: str, user_id: str, *, force: bool = False
) -> tuple[Mapping[str, Any], int] | None:
    """取当前账号绑定的森空岛练度快照（带 TTL 缓存）；未绑定返回 None。

    预览走缓存（force=False），注入前强刷（force=True，决策 38）；
    拉取失败由驱动层降级为 None，绝不影响注入/预览主流程。
    """

    from maa_adapter.cultivate.skland import SklandAccountRef, fetch_skland_progression

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

    from maa_adapter.cultivate.skland import fetch_skland_role_entries

    load_credential, save_credential = _cultivate_skland_callbacks()
    candidates: list[str] = []
    for account_uid, account in Config.ToolsConfig.GameSign_Accounts.items():
        raw = str(account.GameSignAccount.SklandToken or "")
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
) -> dict[str, Any]:
    """养成计划预览（纯计算不落库，方案 §4.3）。

    与注入同一管线；编排逻辑在 tools.cultivate.service，本方法
    只做脚本/档案定位与解析，保持对外契约。
    """

    from maa_adapter.cultivate import depot_cultivate_service, parse_cultivate_targets

    script_config = _maa_script_config(script_id)

    try:
        raw_targets = json.loads(targets)
    except (TypeError, ValueError):
        raw_targets = []

    archive_dir = Path.cwd() / f"data/{uuid.UUID(script_id)}/{uuid.UUID(user_id)}"
    # 森空岛练度走 TTL 缓存（预览不打网络；决策 38），未绑定/失败降级 None
    skland = await get_cultivate_skland_progression(script_id, user_id)
    plan, availability, progressions = await depot_cultivate_service.preview_cultivate(
        targets=parse_cultivate_targets(raw_targets),
        maa_data_dir=archive_dir,
        config_path=Config.config_path,
        proxy=Config.proxy,
        today=game_now(script_config.UserData[uuid.UUID(user_id)].Info.Server).date(),
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
            "skillLevel": snapshot.data.skill_level,
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
        """为养成材料条目补充名称、数量及可选关卡和理智信息，生成预览展示数据。"""
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
