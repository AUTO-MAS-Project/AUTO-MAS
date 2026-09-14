#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""HSR 配置备份归档：MAS 用户字段侧车 / M7A+SRA 两引擎原生配置。

HSR 是唯一一对多专项（一个 ScriptType 编排 M7A 与 SRA 两个上游程序）。
备份时机（MAS「动手前」）：

- 任务启动（manager ``prepare``）：``native`` 归档 M7A ``config.yaml`` +
  SRA ``settings.json``/``cache.json``/``configs/``——运行会把托管字段写进
  这些文件、任务结束按运行期备份清单还原，崩溃残留会污染原生配置，持久
  归档提供跨会话找回；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``、退出时归档
  ``mas``（编辑会话包络的 MAS 侧终态）。

``mas`` 池是**纯字段侧车**（HSR 无 per-user 目录，用户配置是字段）：
Info.Mode（仅预览）+ Managed.TaskMapping/Options（托管覆盖值，运行时物化
进原生）+ Direct.*ImportedAt/Source（直控快照元数据）。**不收录**：
Direct.SRAConfig/M7AConfig（加密快照内容，API 不外泄）、账号密码、
IfQuickConfig（HSR 不支持快速配置，死开关）。恢复即字段回填。

``native`` 池 = M7A ``config.yaml`` + SRA ``settings.json``/``cache.json``/
``configs/``，按 **SRA appdata 根的指纹分桶**（SRA appdata 是多脚本共享
目录，必须 config_root_key 分桶跨脚本共享、不随脚本删除——M7A config.yaml
随 SRA 池一并归档，HSR 脚本通常成对配两引擎）。

时间戳快照、指纹去重、保留清理与文件/目录恢复由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
HSR 特有的两引擎目标解析、侧车、恢复语义（恢复前强制归档当前）与预览。
"""

import json
import tempfile
from pathlib import Path

import yaml

from app.utils import get_logger
from app.utils.config_archive import (
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
)

from .managed_config import SRA_REWARD_LABELS
from .sra_runtime import build_sra_tasklist_description

logger = get_logger("HSR 配置备份")

# ══════════════════ MAS 用户字段侧车（纯侧车，无目录） ══════════════════

_OVERLAY_SIDECAR_NAME = "_mas_overlay.json"
"""页面核心字段侧车文件名（归档内唯一文件；恢复时读出回填，不落任何目录）"""

_OVERLAY_INFO_KEYS = ("Mode",)
"""配置来源（仅预览不回填：决定运行方式）"""

_OVERLAY_MANAGED_KEYS = ("TaskMapping", "Options")
"""托管覆盖值（UserData.Managed，运行时物化进 M7A/SRA 原生配置）"""

_OVERLAY_DIRECT_KEYS = (
    "SRAImportedAt",
    "M7AImportedAt",
    "SRASource",
    "M7ASource",
)
"""直控快照元数据（UserData.Direct；不含加密快照内容）"""

_OVERLAY_KEY_GROUPS = {
    "Info": _OVERLAY_INFO_KEYS,
    "Managed": _OVERLAY_MANAGED_KEYS,
    "Direct": _OVERLAY_DIRECT_KEYS,
}
"""侧车字段的配置段归属（键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置来源决定运行方式，恢复时以当前值为准"""

_OVERLAY_FIELD_LABELS = {
    "Mode": "配置来源",
    "TaskMapping": "任务映射",
    "Options": "托管覆盖",
    "SRAImportedAt": "SRA 快照导入时间",
    "M7AImportedAt": "M7A 快照导入时间",
    "SRASource": "SRA 快照来源",
    "M7ASource": "M7A 快照来源",
}
"""侧车字段中文标签（对齐 HSR 编辑页词表）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 MAS 页面核心字段（鸭子类型，仅需 ``get(group, key)``）。

    值为 ``None``（配置项不存在）的键不纳入侧车。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := config.get(group, key)) is not None:
                values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段按配置段分组（恢复回填 HSRUserConfig 用）。

    仅预览字段（配置来源）不回填：回填旧来源会静默翻转脚本态/用户态/直控。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Managed"), {})[key] = value
    return grouped


def _sidecar_temp_file(overlay: dict) -> Path:
    """把页面核心字段写到临时文件（参与归档指纹，归档后即删）。"""

    fd = tempfile.NamedTemporaryFile(
        "w", suffix=f"{_OVERLAY_SIDECAR_NAME}.tmp", delete=False, encoding="utf-8"
    )
    json.dump(overlay, fd, ensure_ascii=False, indent=2)
    fd.close()
    return Path(fd.name)


def read_overlay_sidecar(backup_dir: Path) -> dict | None:
    """读取归档内的页面核心字段侧车；不存在（旧版备份）或损坏返回 ``None``。"""

    sidecar = Path(backup_dir) / _OVERLAY_SIDECAR_NAME
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/HSRBackups/mas/{user_id}``（恒按用户）。"""

    return Path.cwd() / "data" / script_id / "HSRBackups" / "mas" / user_id


def archive_mas_backup(
    script_id: str, user_id: str, overlay: dict | None, force: bool = False
) -> Path | None:
    """归档页面核心字段侧车到用户池（指纹去重，无变化跳过）。"""

    if not overlay:
        return None
    temp_sidecar = _sidecar_temp_file(overlay)
    try:
        dest = archive_files(
            {_OVERLAY_SIDECAR_NAME: temp_sidecar},
            mas_backup_root(script_id, user_id),
            force=force,
        )
    finally:
        temp_sidecar.unlink(missing_ok=True)
    if dest is None:
        logger.info("MAS 配置无变化，跳过归档")
        return None
    logger.info(f"用户 {user_id} 的 MAS 配置已归档: {dest.name}")
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    """用户池的全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取用户池指定时间戳的归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(script_id: str, user_id: str, ts: str) -> dict | None:
    """读取用户池归档的侧车（供调用方回填 HSRUserConfig）；无目录目标。"""

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    return read_overlay_sidecar(backup_dir)


def archive_mas_runtime_backup(script_id: str, user_id: str, overlay: dict) -> None:
    """运行物化前归档本用户字段侧车（物化会写原生配置，字段本身先存底）。"""

    archive_mas_backup(script_id, user_id, overlay)


# ══════════════════ M7A + SRA 原生配置（两引擎） ══════════════════

_M7A_CONFIG_FILE = "M7A/config.yaml"
"""归档内 M7A 配置的相对键"""

_SRA_SETTINGS_FILE = "SRA/settings.json"
_SRA_CACHE_FILE = "SRA/cache.json"
_SRA_CONFIGS_DIR = "SRA/configs"
"""归档内 SRA 配置的相对键"""


def native_backup_root(sra_app_data: str | Path) -> Path:
    """HSR 原生配置的项目级归档根：``data/HSRBackups/native/{key}``。

    ``key`` 是 **SRA appdata 根**的指纹（:func:`config_root_key`）——SRA
    appdata 是多脚本共享目录，按物理根分桶、跨脚本共享、不随脚本删除；
    M7A config.yaml 随 SRA 池一并归档（HSR 脚本通常成对配两引擎）。
    """

    return Path.cwd() / "data" / "HSRBackups" / "native" / config_root_key(sra_app_data)


def collect_native_files(m7a_root: Path | None, sra_app_data: Path) -> dict[str, Path]:
    """收集两引擎原生配置文件集（相对键 → 文件路径；缺失项跳过）。

    - ``M7A/config.yaml``：M7A 安装根下的配置文件；
    - ``SRA/settings.json`` / ``SRA/cache.json`` / ``SRA/configs/``：SRA
      appdata 共享目录下的配置（configs 为目录，整目录归档）。
    """

    files: dict[str, Path] = {}
    if m7a_root is not None:
        m7a_config = Path(m7a_root) / "config.yaml"
        if m7a_config.is_file():
            files[_M7A_CONFIG_FILE] = m7a_config
    sra_settings = sra_app_data / "settings.json"
    if sra_settings.is_file():
        files[_SRA_SETTINGS_FILE] = sra_settings
    sra_cache = sra_app_data / "cache.json"
    if sra_cache.is_file():
        files[_SRA_CACHE_FILE] = sra_cache
    sra_configs = sra_app_data / "configs"
    if sra_configs.is_dir():
        for rel, path in dir_files(sra_configs).items():
            files[f"{_SRA_CONFIGS_DIR}/{rel}"] = path
    return files


def archive_native_backup(
    m7a_root: Path | None, sra_app_data: Path, force: bool = False
) -> Path | None:
    """归档两引擎原生配置（指纹去重，无变化跳过）。全缺失时返回 ``None``。"""

    files = collect_native_files(m7a_root, sra_app_data)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(sra_app_data), force=force)
    if dest is None:
        logger.info("HSR 原生配置无变化，跳过归档")
        return None
    logger.info(f"HSR 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(sra_app_data: str | Path) -> list[str]:
    """HSR 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(sra_app_data))


def get_native_backup_dir(sra_app_data: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(sra_app_data), ts)


def restore_native_backup(m7a_root: Path | None, sra_app_data: Path, ts: str) -> None:
    """把归档恢复到两引擎原生位置（恢复前自动归档当前，误恢复可找回）。

    按归档内相对键写回：``M7A/*`` → M7A 安装根、``SRA/*`` → SRA appdata；
    只覆盖归档内包含的文件。
    """

    backup_dir = get_native_backup_dir(sra_app_data, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")
    archive_native_backup(m7a_root, sra_app_data, force=True)
    for rel, path in files.items():
        if rel.startswith("M7A/"):
            if m7a_root is None:
                continue
            target = Path(m7a_root) / rel[len("M7A/") :]
        else:
            target = sra_app_data / rel[len("SRA/") :]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    logger.info(f"HSR 原生配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""


def _summary_text(value) -> str:
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _format_bool(value) -> str:
    return "开启" if bool(value) else "关闭"


def _parse_json_dict(raw) -> dict:
    """解析 JSON 对象字符串字段（TaskMapping/Options），非法返回空 dict。"""

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except Exception:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def build_overlay_preview(overlay: dict) -> dict:
    """mas 池预览：分区行（MAS 独有 = 配置来源；托管配置 = 任务映射/覆盖）。"""

    sections: list[dict] = []

    mas_rows: list[dict] = []
    if "Mode" in overlay:
        mas_rows.append({"key": "配置来源", "value": _summary_text(overlay["Mode"])})
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    managed_rows: list[dict] = []
    if "TaskMapping" in overlay:
        mapping = _parse_json_dict(overlay["TaskMapping"])
        managed_rows.append(
            {
                "key": "任务映射",
                "value": "、".join(f"{k}→{v}" for k, v in mapping.items()) or "无",
            }
        )
    if "Options" in overlay:
        options = _parse_json_dict(overlay["Options"])
        managed_rows.append({"key": "托管覆盖", "value": "、".join(options) or "无"})
    if managed_rows:
        sections.append({"name": "managed", "label": "托管配置", "rows": managed_rows})

    direct_rows: list[dict] = []
    for key in _OVERLAY_DIRECT_KEYS:
        if key in overlay and str(overlay[key]).strip():
            direct_rows.append(
                {
                    "key": _OVERLAY_FIELD_LABELS[key],
                    "value": _summary_text(overlay[key]),
                }
            )
    if direct_rows:
        sections.append({"name": "direct", "label": "直控快照", "rows": direct_rows})

    return {"sections": sections}


def build_native_preview(sra_app_data: str | Path, ts: str) -> dict:
    """native 池预览：两引擎常用配置反读 + 文件清单。

    反读范围只限 **MAS 侧有对应概念的常用字段**（托管表单/patch 白名单覆盖的
    键，词表固化、零本体运行时依赖）：

    - M7A ``config.yaml``：清体力/副本/历战余响/体力补充/培养目标/每日实训/
      领取奖励/兑换码/差分宇宙/货币战争/云游戏（键名以 MAS 托管白名单为准）；
    - SRA ``configs/*.json``：每档案一节——游戏渠道/清体力/任务清单/补充
      开拓力/领取奖励/差分宇宙/货币战争/完成后动作（键形为顶层 camelCase 段
      + 段内平铺点号键，见 SRA ``SRACore/models/tasks_config.py``，与 MAS
      ``_build_sra_base_config`` 写出口径一致；奖励开关兼容索引式与命名键）；
    - ``settings.json``/``cache.json`` 结构未经现场核实（后者为运行缓存），
      **不反读内容**，只在文件清单节展示。
    """

    backup_dir = get_native_backup_dir(sra_app_data, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")

    sections: list[dict] = []

    m7a_payload = _load_yaml_dict(backup_dir / "M7A" / "config.yaml")
    m7a_rows = _m7a_preview_rows(m7a_payload) if m7a_payload else []
    if m7a_rows:
        sections.append({"name": "m7a", "label": "M7A（三月七助手）", "rows": m7a_rows})

    for rel in sorted(files):
        if not rel.startswith(f"{_SRA_CONFIGS_DIR}/") or not rel.endswith(".json"):
            continue
        profile = _load_json_dict(files[rel])
        rows = _sra_profile_rows(profile) if profile else []
        if rows:
            stem = rel[len(_SRA_CONFIGS_DIR) + 1 : -len(".json")]
            sections.append(
                {"name": f"sra:{stem}", "label": f"SRA 配置档案 · {stem}", "rows": rows}
            )

    sections.append(
        {
            "name": "files",
            "label": "备份文件",
            "rows": [
                {"key": rel, "value": f"{path.stat().st_size} B"}
                for rel, path in sorted(files.items())
            ],
        }
    )
    return {"sections": sections}


# ── 反读词表（固化，零本体运行时依赖；出处见行内注释）──────────────────

_M7A_PREVIEW_KEYS: tuple[tuple[str, str], ...] = (
    ("power_enable", "清体力"),
    ("build_target_enable", "培养目标"),
    ("daily_enable", "每日实训"),
    ("cloud_game_enable", "云游戏"),
)
"""M7A 平铺布尔键 → 行标签（键均在 MAS 托管白名单内，含义取自
config.example.yaml 行内注释）"""

_M7A_REWARD_SUB_LABELS: tuple[tuple[str, str], ...] = (
    ("reward_dispatch_enable", "委托"),
    ("reward_mail_enable", "邮件"),
    ("reward_assist_enable", "支援"),
    ("reward_quest_enable", "每日实训"),
    ("reward_srpass_enable", "无名勋礼"),
    ("reward_redemption_code_enable", "兑换码"),
    ("reward_achievement_enable", "成就"),
    ("reward_message_enable", "短信"),
)
"""M7A 领取奖励子开关 → 短标签（config.example.yaml 行内注释原文去尾）"""

_M7A_DIVERGENT_TYPE_LABELS = {"normal": "常规演算", "cycle": "周期演算"}
"""M7A weekly_divergent_type 取值（config.example.yaml：normal/cycle）"""

_M7A_CURRENCY_WARS_TYPE_LABELS = {"normal": "标准博弈", "overclock": "超频博弈"}
"""M7A currencywars_type 取值（config.example.yaml：normal/overclock）"""

_SRA_CHANNEL_LABELS = {0: "国服", 1: "B服", 2: "国际服"}
"""SRA startGame.game.channel 取值（SRA tasks/StartGameTask._game_channel：
0=cn、1=bl、2=gb）"""

_SRA_REPLENISH_WAY_LABELS = {0: "后备开拓力", 1: "燃料", 2: "星琼"}
"""SRA trailblazePower.replenish.way 取值（与托管表单 _SRA_SELECTS 同口径，
SRA TrailblazePowerTask.replenish）"""

_SRA_DIVERGENT_MODE_LABELS = {0: "常规演算", 1: "周期演算"}
"""SRA cosmicStrife.divergentUniverse.mode 取值（与托管表单 _SRA_SELECTS 同口径）"""

_SRA_CURRENCY_WARS_MODE_LABELS = {0: "标准博弈", 1: "超频博弈", 2: "刷开局"}
"""SRA cosmicStrife.currencyWars.mode 取值（与托管表单 _SRA_SELECTS 同口径）"""

_SRA_REWARD_KEY_ORDER = (
    "trailblazeProfile",
    "assignments",
    "mail",
    "dailyTraining",
    "namelessHonor",
    "giftOfOdyssey",
    "redeemCode",
)
"""SRA 命名式奖励开关的顺序（SRA ReceiveRewardsConfig，与
SRA_REWARD_LABELS 一一对应；索引式 rewards 列表按同序兼容读取）"""

_SRA_FINISH_ACTION_LABELS: tuple[tuple[str, str], ...] = (
    ("exitGame", "退出游戏"),
    ("logout", "登出"),
    ("shutdown", "关机"),
    ("sleep", "睡眠"),
    ("exitApp", "退出 SRA"),
)
"""SRA missionAccomplished 完成后动作开关 → 短标签（TasksConfig 键名直译）"""


def _load_json_dict(path: Path) -> dict | None:
    """容错读取 JSON 对象文件；缺失/损坏/非对象返回 ``None``。"""

    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_yaml_dict(path: Path) -> dict | None:
    """容错读取 YAML 对象文件；缺失/损坏/非对象返回 ``None``。"""

    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _join_bool_labels(payload: dict, pairs: tuple[tuple[str, str], ...]) -> str:
    """把启用的布尔子开关连成短标签串；全关返回「无」。"""

    enabled = [label for key, label in pairs if payload.get(key) is True]
    return "、".join(enabled) if enabled else "无"


def _m7a_preview_rows(payload: dict) -> list[dict]:
    """M7A config.yaml 常用字段行（只收录 MAS 白名单概念内的键）。"""

    rows: list[dict] = []

    def present(key: str) -> bool:
        return payload.get(key) is not None

    for key, label in _M7A_PREVIEW_KEYS:
        if present(key):
            rows.append({"key": label, "value": _format_bool(payload[key])})

    instance_type = payload.get("instance_type")
    if instance_type is not None:
        instance_names = payload.get("instance_names")
        name = (
            instance_names.get(instance_type, "")
            if isinstance(instance_names, dict)
            else ""
        )
        value = _summary_text(instance_type)
        if name and name != "无":
            value = f"{instance_type} · {name}"
        rows.append({"key": "副本", "value": value})

    if present("echo_of_war_enable"):
        value = _format_bool(payload["echo_of_war_enable"])
        instance_names = payload.get("instance_names")
        eow_name = (
            instance_names.get("历战余响", "")
            if isinstance(instance_names, dict)
            else ""
        )
        if payload.get("echo_of_war_enable") and eow_name and eow_name != "无":
            value = f"开启 · {eow_name}"
        rows.append({"key": "历战余响", "value": value})

    if present("use_reserved_trailblaze_power") or present("use_fuel"):
        supplements = []
        if payload.get("use_reserved_trailblaze_power"):
            supplements.append("后备开拓力")
        if payload.get("use_fuel"):
            supplements.append("燃料")
        rows.append(
            {
                "key": "体力补充",
                "value": "、".join(supplements) if supplements else "无",
            }
        )

    if present("reward_enable"):
        value = _format_bool(payload["reward_enable"])
        if payload.get("reward_enable"):
            subs = {
                key: payload.get(key)
                for key, _label in _M7A_REWARD_SUB_LABELS
                if payload.get(key) is not None
            }
            if subs:
                value = _join_bool_labels(subs, _M7A_REWARD_SUB_LABELS)
        rows.append({"key": "领取奖励", "value": value})

    codes = payload.get("redemption_code")
    if isinstance(codes, list):
        rows.append({"key": "兑换码", "value": f"{len(codes)} 个" if codes else "无"})

    if present("weekly_divergent_enable"):
        value = _format_bool(payload["weekly_divergent_enable"])
        if payload.get("weekly_divergent_enable"):
            parts = [
                _M7A_DIVERGENT_TYPE_LABELS.get(
                    str(payload.get("weekly_divergent_type"))
                )
                or str(payload.get("weekly_divergent_type") or "")
            ]
            if payload.get("weekly_divergent_level") is not None:
                parts.append(f"难度{payload['weekly_divergent_level']}")
            value = " · ".join(part for part in parts if part) or "开启"
        rows.append({"key": "差分宇宙", "value": value})

    if present("currencywars_enable"):
        value = _format_bool(payload["currencywars_enable"])
        if payload.get("currencywars_enable"):
            value = (
                _M7A_CURRENCY_WARS_TYPE_LABELS.get(
                    str(payload.get("currencywars_type"))
                )
                or "开启"
            )
        rows.append({"key": "货币战争", "value": value})

    return rows


def _sra_profile_rows(payload: dict) -> list[dict]:
    """SRA 档案常用字段行（顶层 camelCase 段 + 平铺点号键）。"""

    rows: list[dict] = []

    start_game = payload.get("startGame")
    if isinstance(start_game, dict) and start_game.get("game.channel") is not None:
        channel = start_game.get("game.channel")
        rows.append(
            {
                "key": "游戏渠道",
                "value": _SRA_CHANNEL_LABELS.get(channel, str(channel)),
            }
        )

    trailblaze = payload.get("trailblazePower")
    if isinstance(trailblaze, dict):
        if trailblaze.get("enabled") is not None:
            rows.append({"key": "清体力", "value": _format_bool(trailblaze["enabled"])})
        tasklist = trailblaze.get("tasklist")
        if isinstance(tasklist, list):
            description = build_sra_tasklist_description(tasklist) if tasklist else "无"
            rows.append(
                {
                    "key": "清体力任务清单",
                    "value": _summary_text(description),
                }
            )
        if trailblaze.get("replenish.enabled") is not None:
            value = "关闭"
            if trailblaze.get("replenish.enabled"):
                way = trailblaze.get("replenish.way")
                way_label = _SRA_REPLENISH_WAY_LABELS.get(
                    way, str(way if way is not None else "")
                )
                value = way_label or "开启"
                times = trailblaze.get("replenish.times")
                if isinstance(times, int) and times > 0:
                    value = f"{value} ×{times}"
            rows.append({"key": "补充开拓力", "value": value})

    rewards_section = payload.get("receiveRewards")
    if isinstance(rewards_section, dict):
        reward_values = _sra_reward_values(rewards_section)
        if reward_values is not None:
            enabled = [
                SRA_REWARD_LABELS[index]
                for index, flag in enumerate(reward_values)
                if flag
            ]
            rows.append(
                {"key": "领取奖励", "value": "、".join(enabled) if enabled else "无"}
            )

    cosmic = payload.get("cosmicStrife")
    if isinstance(cosmic, dict):
        if cosmic.get("divergentUniverse.enabled") is not None:
            value = "关闭"
            if cosmic.get("divergentUniverse.enabled"):
                mode = cosmic.get("divergentUniverse.mode")
                mode_label = _SRA_DIVERGENT_MODE_LABELS.get(
                    mode, str(mode if mode is not None else "")
                )
                value = mode_label or "开启"
                runtimes = cosmic.get("divergentUniverse.runtimes")
                if isinstance(runtimes, int) and runtimes > 0:
                    value = f"{value} ×{runtimes}"
            rows.append({"key": "差分宇宙", "value": value})
        if cosmic.get("currencyWars.enabled") is not None:
            value = "关闭"
            if cosmic.get("currencyWars.enabled"):
                mode = cosmic.get("currencyWars.mode")
                mode_label = _SRA_CURRENCY_WARS_MODE_LABELS.get(
                    mode, str(mode if mode is not None else "")
                )
                value = mode_label or "开启"
                runtimes = cosmic.get("currencyWars.runtimes")
                if isinstance(runtimes, int) and runtimes > 0:
                    value = f"{value} ×{runtimes}"
            rows.append({"key": "货币战争", "value": value})

    finish = payload.get("missionAccomplished")
    if isinstance(finish, dict):
        rows.append(
            {
                "key": "完成后动作",
                "value": _join_bool_labels(finish, _SRA_FINISH_ACTION_LABELS),
            }
        )

    return rows


def _sra_reward_values(section: dict) -> list[bool] | None:
    """读 SRA 奖励开关为布尔列表（SRA_REWARD_LABELS 顺序）。

    命名键（``rewards.<name>``）优先，缺失项回退索引式 ``rewards`` 列表——
    与 SRA ``ReceiveRewardsConfig.from_dict`` 的兼容口径一致。两类键都
    不存在时返回 ``None``（不渲染该行）。
    """

    legacy = section.get("rewards")
    legacy_values = (
        [bool(item) for item in legacy] if isinstance(legacy, list) else None
    )
    if legacy_values is not None:
        # 索引式按 SRA 语义补齐到定长：被改短的尾部按默认关闭处理
        legacy_values += [False] * (len(_SRA_REWARD_KEY_ORDER) - len(legacy_values))
    values: list[bool] = []
    has_named = False
    for index, name in enumerate(_SRA_REWARD_KEY_ORDER):
        named = section.get(f"rewards.{name}")
        if named is not None:
            has_named = True
            values.append(bool(named))
            continue
        if legacy_values is not None and len(legacy_values) > index:
            values.append(legacy_values[index])
        else:
            values.append(False)
    if has_named:
        return values
    return legacy_values
