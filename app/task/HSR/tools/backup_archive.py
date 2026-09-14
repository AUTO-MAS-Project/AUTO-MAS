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

from app.utils import get_logger
from app.utils.config_archive import (
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
)

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


def collect_native_files(
    m7a_root: Path | None, sra_app_data: Path
) -> dict[str, Path]:
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


def restore_native_backup(
    m7a_root: Path | None, sra_app_data: Path, ts: str
) -> None:
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
        managed_rows.append(
            {"key": "托管覆盖", "value": "、".join(options) or "无"}
        )
    if managed_rows:
        sections.append(
            {"name": "managed", "label": "托管配置", "rows": managed_rows}
        )

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
    """native 池预览：文件粒度（M7A config.yaml + SRA settings/cache/configs）。

    不反读内部字段：M7A config.yaml 与 SRA 配置结构随引擎版本漂移、未经现场
    核实，按「不臆造」原则只做文件清单粒度展示（对齐 General）。
    """

    backup_dir = get_native_backup_dir(sra_app_data, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")
    rows = [
        {"key": rel, "value": f"{path.stat().st_size} B"}
        for rel, path in sorted(files.items())
    ]
    return {"sections": [{"name": "hsr", "label": "HSR 原生配置", "rows": rows}]}
