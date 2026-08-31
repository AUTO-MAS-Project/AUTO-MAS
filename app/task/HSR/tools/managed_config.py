"""从 SRA/M7A 原生配置发现 MAS 托管表单。

这里不复制一份固定的脚本配置 schema：字段和值均来自用户当前安装的
``config.json``/``config.yaml``，而 ``Managed.Options`` 只保存用户覆盖值。
因此老 dev 没有新字段时仍返回空表单，已有旧配置执行路径不受影响。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .m7a_config import (
    load_m7a_native_config,
    managed_modules_for_key,
    resolve_managed_options,
)
from .native_control import _script_path
from .sra_runtime import (
    discover_sra_managed_options,
    load_sra_native_config,
    resolve_sra_managed_options,
)


@dataclass(frozen=True, slots=True)
class HSRManagedFieldOption:
    value: Any
    label: str

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HSRManagedField:
    key: str
    label: str
    type: str
    value: Any
    description: str = ""
    options: tuple[HSRManagedFieldOption, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    readonly: bool = False

    def asdict(self) -> dict[str, Any]:
        data = asdict(self)
        data["options"] = [item.asdict() for item in self.options]
        return data


@dataclass(frozen=True, slots=True)
class HSRManagedModule:
    key: str
    engine: str
    fields: tuple[HSRManagedField, ...]
    source: str
    warnings: tuple[str, ...] = ()

    def asdict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fields"] = [item.asdict() for item in self.fields]
        return data


def _field_type(value: Any, options: tuple[HSRManagedFieldOption, ...]) -> str:
    if options:
        return "select"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (list, dict)):
        return "json"
    return "string"


def _field(
    key: str,
    native_value: Any,
    value: Any,
    *,
    label: str | None = None,
    description: str = "",
    options: tuple[HSRManagedFieldOption, ...] = (),
    minimum: float | None = None,
    maximum: float | None = None,
) -> HSRManagedField:
    return HSRManagedField(
        key=key,
        label=label or key,
        type=_field_type(native_value, options),
        value=value,
        description=description,
        options=options,
        minimum=minimum,
        maximum=maximum,
    )


_SRA_LABELS = {
    "replenish.enabled": "使用开拓力补充",
    "replenish.times": "补充次数",
    "replenish.way": "补充方式",
    "useAssistant": "使用支援角色",
    "useBuildTarget": "使用培养目标",
    "activity.enabled": "体力活动检测",
    "activity.gardenOfPlenty.level1": "花藏繁生：拟造花萼（金）",
    "activity.gardenOfPlenty.level2": "花藏繁生：拟造花萼（赤）",
    "activity.planarFissure.level": "位面分裂：饰品提取",
    "activity.realmOfTheStrange.level": "异器盈界：侵蚀隧洞",
    "redeemCodes": "兑换码",
    "pointRewards.enabled": "领取积分奖励",
    "divergentUniverse.mode": "演算类别",
    "divergentUniverse.runtimes": "运行次数",
    "divergentUniverse.useTechnique": "使用秘技",
    "currencyWars.mode": "博弈类别",
    "currencyWars.difficulty": "难度",
    "currencyWars.policy": "策略来源",
    "currencyWars.reroll.bossAffixes": "首领词条重开条件",
    "currencyWars.reroll.bossNames": "首领名称重开条件",
    "currencyWars.reroll.investEnvironments": "投资环境重开条件",
    "currencyWars.reroll.investStrategies": "投资策略重开条件",
    "currencyWars.runtimes": "运行次数",
    "currencyWars.strategy": "策略文件",
    "currencyWars.strategyIndex": "策略序号",
    "currencyWars.username": "开拓者名称",
}
_SRA_REWARD_LABELS = (
    "签证（支援）奖励",
    "委托奖励",
    "邮件奖励",
    "每日实训奖励",
    "无名勋礼奖励",
    "巡星之礼",
    "兑换码奖励",
)
_SRA_SELECTS = {
    "replenish.way": (
        HSRManagedFieldOption(0, "燃料"),
        HSRManagedFieldOption(1, "星琼"),
    ),
    "divergentUniverse.mode": (
        HSRManagedFieldOption(0, "常规演算"),
        HSRManagedFieldOption(1, "周期演算"),
    ),
    "currencyWars.mode": (
        HSRManagedFieldOption(0, "标准博弈"),
        HSRManagedFieldOption(1, "超频博弈"),
    ),
    "currencyWars.difficulty": (
        HSRManagedFieldOption(0, "最低难度"),
        HSRManagedFieldOption(1, "最高难度"),
    ),
}

_SRA_ACTIVITY_STAGE_CATEGORIES = {
    "activity.gardenOfPlenty.level1": "calyx_golden",
    "activity.gardenOfPlenty.level2": "calyx_crimson",
    "activity.planarFissure.level": "ornament_extraction",
    "activity.realmOfTheStrange.level": "caver_of_corrosion",
}
_SRA_ACTIVITY_STAGE_DESCRIPTION = (
    "检测到对应双倍活动时使用的 SRA 原生关卡；选择‘不刷’则跳过这一类活动副本。"
)


def _sra_activity_stage_options(
    script_config: Any,
) -> dict[str, tuple[HSRManagedFieldOption, ...]]:
    """把已安装 SRA 的动态关卡表转成活动配置下拉选项。"""

    try:
        from .stage_provider import get_sra_stage_options

        payload = get_sra_stage_options(script_config)
    except (FileNotFoundError, OSError, RuntimeError, ValueError, TypeError):
        return {}

    categories = payload.get("categories") if isinstance(payload, dict) else None
    category_by_key = {
        str(category.get("categoryKey")): category
        for category in categories or ()
        if isinstance(category, dict)
    }
    result: dict[str, tuple[HSRManagedFieldOption, ...]] = {}
    for field_key, category_key in _SRA_ACTIVITY_STAGE_CATEGORIES.items():
        options = [HSRManagedFieldOption(0, "不刷")]
        category = category_by_key.get(category_key)
        raw_options = category.get("options") if category else ()
        for option in raw_options or ():
            if not isinstance(option, dict):
                continue
            native = option.get("sra")
            if not isinstance(native, dict):
                continue
            try:
                level = int(native.get("level"))
            except (TypeError, ValueError):
                continue
            label = str(option.get("label") or level)
            detail = str(option.get("detail") or "").strip()
            if detail:
                label = f"{label}｜{detail}"
            options.append(HSRManagedFieldOption(level, label))
        result[field_key] = tuple(options)
    return result


def list_sra_managed_modules(
    script_config: Any, user_config: Any | None = None
) -> tuple[HSRManagedModule, ...]:
    source, _payload = load_sra_native_config(script_config)
    activity_stage_options = _sra_activity_stage_options(script_config)
    result: list[HSRManagedModule] = []
    for module_key in ("Daily", "ReceiveRewards", "DivergentUniverse", "CurrencyWars"):
        values, _section_name = discover_sra_managed_options(module_key, script_config)
        effective = resolve_sra_managed_options(module_key, script_config, user_config)
        fields = tuple(
            _field(
                key,
                value,
                effective.get(key, value),
                label=(
                    _SRA_REWARD_LABELS[int(key.removeprefix("rewards."))]
                    if key.startswith("rewards.")
                    and key.removeprefix("rewards.").isdigit()
                    and int(key.removeprefix("rewards.")) < len(_SRA_REWARD_LABELS)
                    else _SRA_LABELS.get(key, key)
                ),
                description=(
                    _SRA_ACTIVITY_STAGE_DESCRIPTION
                    if key in _SRA_ACTIVITY_STAGE_CATEGORIES
                    else ""
                ),
                options=activity_stage_options.get(
                    key,
                    _SRA_SELECTS.get(key, ()),
                ),
            )
            for key, value in values.items()
        )
        result.append(HSRManagedModule(module_key, "SRA", fields, str(source)))
    return tuple(result)


_M7A_LABEL_FALLBACKS = {
    "instance_teams": "指定副本队伍",
    "borrow_friends": "支援好友列表",
}
_M7A_SELECTS = {
    "build_target_scheme": (
        HSRManagedFieldOption("instance", "按副本名称识别"),
        HSRManagedFieldOption("drop", "按副本素材识别"),
    ),
    "weekly_divergent_type": (
        HSRManagedFieldOption("normal", "常规演算"),
        HSRManagedFieldOption("cycle", "周期演算"),
    ),
    "currencywars_type": (
        HSRManagedFieldOption("normal", "标准博弈"),
        HSRManagedFieldOption("overclock", "超频博弈"),
    ),
    "currencywars_rank_difficulty": (
        HSRManagedFieldOption("lowest", "最低职级"),
        HSRManagedFieldOption("current", "当前职级"),
        HSRManagedFieldOption("highest", "最高职级"),
    ),
    "currencywars_strategy": (
        HSRManagedFieldOption("default", "默认策略"),
        HSRManagedFieldOption("aglaea", "阿格莱雅策略"),
        HSRManagedFieldOption("seele", "希儿策略"),
    ),
}
_M7A_RANGES: dict[str, tuple[float | None, float | None]] = {
    "build_target_ornament_weekly_count": (0, 7),
    "weekly_divergent_level": (1, 6),
}


def _load_m7a_comments(path: Path) -> dict[str, str]:
    """读取同行或紧邻前置注释中的 M7A 原生字段说明。"""

    if not path.is_file():
        return {}
    comments: dict[str, str] = {}
    pending: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            text = stripped.removeprefix("#").strip()
            if text:
                pending.append(text)
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*):.*?(?:#\s*(.+))?$", stripped)
        if match:
            inline = str(match.group(2) or "").strip()
            comments[match.group(1)] = inline or " ".join(pending)
        pending = []
    return comments


def _m7a_label(key: str, comment: str) -> str:
    label = _M7A_LABEL_FALLBACKS.get(key)
    if label:
        return label
    first = re.split(r"[。；]", comment, maxsplit=1)[0].strip()
    first = re.sub(r"^是否", "", first)
    return first or key


def list_m7a_managed_modules(
    script_config: Any, user_config: Any | None = None
) -> tuple[HSRManagedModule, ...]:
    raw_root = _script_path(script_config, "M7A")
    if not raw_root:
        raise FileNotFoundError("请先设置 M7A 路径")
    root = Path(raw_root)
    source = root / "config.yaml"
    if not source.is_file():
        raise FileNotFoundError(f"三月七助手原生配置不存在：{source}")
    payload = load_m7a_native_config(script_config)
    comments = _load_m7a_comments(root / "assets" / "config" / "config.example.yaml")
    buckets: dict[str, list[HSRManagedField]] = {
        key: []
        for key in ("Daily", "ReceiveRewards", "DivergentUniverse", "CurrencyWars")
    }
    effective_by_module = {
        module_key: resolve_managed_options(payload, user_config, module_key)
        for module_key in buckets
    }
    for key, value in payload.items():
        modules = managed_modules_for_key(str(key))
        for module_key in modules:
            effective = effective_by_module[module_key]
            buckets[module_key].append(
                _field(
                    str(key),
                    value,
                    effective.get(str(key), value),
                    label=_m7a_label(str(key), comments.get(str(key), "")),
                    description=comments.get(str(key), ""),
                    options=_M7A_SELECTS.get(str(key), ()),
                    minimum=_M7A_RANGES.get(str(key), (None, None))[0],
                    maximum=_M7A_RANGES.get(str(key), (None, None))[1],
                )
            )
    return tuple(
        HSRManagedModule(key, "M7A", tuple(fields), str(source))
        for key, fields in buckets.items()
    )


def list_managed_modules(
    engine: str, script_config: Any, user_config: Any | None = None
) -> tuple[HSRManagedModule, ...]:
    normalized = str(engine or "").strip().upper()
    if normalized == "SRA":
        return list_sra_managed_modules(script_config, user_config)
    if normalized == "M7A":
        return list_m7a_managed_modules(script_config, user_config)
    raise ValueError(f"不支持的 HSR 托管引擎：{engine!r}")


def redeem_code_fingerprint(engine: str, script_config: Any) -> str:
    """Return a stable hash of an engine's native redeem-code payload only."""

    normalized = str(engine or "").strip().upper()
    if normalized == "SRA":
        _source, payload = load_sra_native_config(script_config)
        value = (payload.get("receiveRewards") or {}).get("redeemCodes")
    elif normalized == "M7A":
        raw_root = _script_path(script_config, "M7A")
        source = Path(raw_root) / "config.yaml"
        payload = load_m7a_native_config(script_config)
        value = payload.get("redemption_code")
    else:
        raise ValueError(f"不支持的 HSR 兑换码引擎：{engine!r}")
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "HSRManagedField",
    "HSRManagedFieldOption",
    "HSRManagedModule",
    "list_managed_modules",
    "list_m7a_managed_modules",
    "list_sra_managed_modules",
    "redeem_code_fingerprint",
]
