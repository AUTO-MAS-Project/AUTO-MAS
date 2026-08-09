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

import yaml

from .m7a_config import managed_modules_for_key
from .native_control import _config_value, _script_path
from .sra_runtime import resolve_sra_profile


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


def _parse_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _user_overrides(user_config: Any, engine: str, module_key: str) -> dict[str, Any]:
    raw = _parse_mapping(_config_value(user_config, "Managed", "Options", {}))
    per_engine = raw.get(engine)
    if not isinstance(per_engine, dict):
        return {}
    module = per_engine.get(module_key)
    return dict(module) if isinstance(module, dict) else {}


def _same_kind(value: Any, reference: Any) -> bool:
    if isinstance(reference, bool):
        return isinstance(value, bool)
    if isinstance(reference, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(reference, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(reference, list):
        return isinstance(value, list)
    if isinstance(reference, dict):
        return isinstance(value, dict)
    if isinstance(reference, str):
        return isinstance(value, str)
    return True


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
    overrides: dict[str, Any],
    *,
    label: str | None = None,
    description: str = "",
    options: tuple[HSRManagedFieldOption, ...] = (),
    minimum: float | None = None,
    maximum: float | None = None,
) -> HSRManagedField:
    value = overrides.get(key, native_value)
    if key in overrides and not _same_kind(value, native_value):
        raise ValueError(f"{key} 的托管值类型与原生配置不一致")
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
    "replenish.way": (HSRManagedFieldOption(0, "燃料"), HSRManagedFieldOption(1, "星琼")),
    "divergentUniverse.mode": (HSRManagedFieldOption(0, "常规演算"), HSRManagedFieldOption(1, "周期演算")),
    "currencyWars.mode": (HSRManagedFieldOption(0, "标准博弈"), HSRManagedFieldOption(1, "超频博弈")),
    "currencyWars.difficulty": (HSRManagedFieldOption(0, "最低难度"), HSRManagedFieldOption(1, "最高难度")),
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


def _load_sra_native(script_config: Any) -> tuple[Path, dict[str, Any]]:
    _selected_id, path = resolve_sra_profile(script_config)
    if not path.is_file():
        raise FileNotFoundError(f"SRA 原生配置不存在：{path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"SRA 原生配置顶层必须是对象：{path}")
    return path, data


def list_sra_managed_modules(script_config: Any, user_config: Any | None = None) -> tuple[HSRManagedModule, ...]:
    source, payload = _load_sra_native(script_config)
    activity_stage_options = _sra_activity_stage_options(script_config)
    sections = {
        "Daily": ("trailblazePower", lambda key: key not in {"enabled", "tasklist"}),
        "ReceiveRewards": ("receiveRewards", lambda key: key not in {"enabled", "redeemCodes"}),
        "DivergentUniverse": (
            "cosmicStrife",
            lambda key: (
                key == "pointRewards.enabled"
                or (
                    key.startswith("divergentUniverse.")
                    and key != "divergentUniverse.enabled"
                )
            ),
        ),
        "CurrencyWars": (
            "cosmicStrife",
            lambda key: key.startswith("currencyWars.") and key != "currencyWars.enabled",
        ),
    }
    result: list[HSRManagedModule] = []
    for module_key, (section_name, predicate) in sections.items():
        section = payload.get(section_name)
        section = section if isinstance(section, dict) else {}
        values: dict[str, Any] = {}
        for key, value in section.items():
            if key == "rewards" and isinstance(value, list):
                values.update({f"rewards.{index}": item for index, item in enumerate(value)})
            elif predicate(str(key)):
                values[str(key)] = value
        overrides = _user_overrides(user_config, "SRA", module_key)
        unknown = sorted(set(overrides).difference(values))
        if unknown:
            raise ValueError(f"SRA {module_key} 包含当前原生配置不支持的字段：{'、'.join(unknown)}")
        fields = tuple(
            _field(
                key,
                value,
                overrides,
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


_M7A_LABELS = {
    "power_enable": "清体力总开关",
    "power_plan": "体力计划",
    "instance_type": "副本类型",
    "instance_names": "各类副本",
    "instance_names_challenge_count": "连续挑战次数",
    "instance_teams": "指定副本队伍",
    "build_target_enable": "启用培养目标",
    "build_target_scheme": "培养目标识别方案",
    "build_target_ornament_weekly_count": "饰品提取周次数",
    "build_target_use_user_instance_when_only_erosion_and_ornament": "仅遗器目标时使用手动副本",
    "activity_enable": "活动检测总开关",
    "activity_dailycheckin_enable": "活动每日签到",
    "activity_gardenofplenty_enable": "花藏繁生体力活动",
    "activity_gardenofplenty_instance_type": "花藏繁生副本类型",
    "activity_realmofthestrange_enable": "异器盈界体力活动",
    "activity_planarfissure_enable": "位面分裂体力活动",
    "borrow_friends": "支援好友列表",
    "reward_enable": "奖励领取总开关",
    "reward_redemption_code_enable": "兑换码奖励",
    "weekly_divergent_type": "演算类别",
    "weekly_divergent_level": "难度等级",
    "weekly_divergent_bonus_enable": "自动饰品提取",
    "weekly_divergent_stable_mode": "低性能兼容模式",
    "currencywars_type": "博弈类别",
    "currencywars_rank_difficulty": "职级难度",
    "currencywars_strategy": "货币战争策略",
    "currencywars_bonus_enable": "自动位面饰品提取",
    "currencywars_fast_mode": "速通模式",
    "currencywars_remembrance_trailblazer_name": "开拓者·记忆名称",
    "currencywars_strategy_restart_on_special_tags": "特定词条接受重开",
}
_M7A_SELECTS = {
    "build_target_scheme": (
        HSRManagedFieldOption("instance", "按副本名称识别"),
        HSRManagedFieldOption("drop", "按副本素材识别"),
    ),
    "weekly_divergent_type": (HSRManagedFieldOption("normal", "常规演算"), HSRManagedFieldOption("cycle", "周期演算")),
    "currencywars_type": (HSRManagedFieldOption("normal", "标准博弈"), HSRManagedFieldOption("overclock", "超频博弈")),
    "currencywars_rank_difficulty": (HSRManagedFieldOption("lowest", "最低职级"), HSRManagedFieldOption("current", "当前职级"), HSRManagedFieldOption("highest", "最高职级")),
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
    """读取 M7A config.example.yaml 的原生字段说明。"""

    if not path.is_file():
        return {}
    comments: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*):.*?#\s*(.+)$", line)
        if match:
            comments[match.group(1)] = match.group(2).strip()
    return comments


def _m7a_label(key: str, comment: str) -> str:
    label = _M7A_LABELS.get(key)
    if label:
        return label
    first = re.split(r"[。；]", comment, maxsplit=1)[0].strip()
    first = re.sub(r"^是否", "", first)
    return first or key


def list_m7a_managed_modules(script_config: Any, user_config: Any | None = None) -> tuple[HSRManagedModule, ...]:
    root = Path(_script_path(script_config, "M7A"))
    source = root / "config.yaml"
    if not source.is_file():
        raise FileNotFoundError(f"三月七助手原生配置不存在：{source}")
    payload = yaml.safe_load(source.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"三月七助手 config.yaml 顶层必须是对象：{source}")
    comments = _load_m7a_comments(root / "assets" / "config" / "config.example.yaml")
    buckets: dict[str, list[HSRManagedField]] = {key: [] for key in ("Daily", "ReceiveRewards", "DivergentUniverse", "CurrencyWars")}
    for key, value in payload.items():
        modules = managed_modules_for_key(str(key))
        for module_key in modules:
            overrides = _user_overrides(user_config, "M7A", module_key)
            buckets[module_key].append(
                _field(
                    str(key),
                    value,
                    overrides,
                    label=_m7a_label(str(key), comments.get(str(key), "")),
                    description=comments.get(str(key), ""),
                    options=_M7A_SELECTS.get(str(key), ()),
                    minimum=_M7A_RANGES.get(str(key), (None, None))[0],
                    maximum=_M7A_RANGES.get(str(key), (None, None))[1],
                )
            )
    return tuple(HSRManagedModule(key, "M7A", tuple(fields), str(source)) for key, fields in buckets.items())


def list_managed_modules(engine: str, script_config: Any, user_config: Any | None = None) -> tuple[HSRManagedModule, ...]:
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
        _source, payload = _load_sra_native(script_config)
        value = (payload.get("receiveRewards") or {}).get("redeemCodes")
    elif normalized == "M7A":
        source = Path(_script_path(script_config, "M7A")) / "config.yaml"
        payload = yaml.safe_load(source.read_text(encoding="utf-8-sig")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"三月七助手 config.yaml 顶层必须是对象：{source}")
        value = payload.get("redemption_code")
    else:
        raise ValueError(f"不支持的 HSR 兑换码引擎：{engine!r}")
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
