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
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""IUpstreamConfigSurface 默认实现：上游安装目录三件套 + config.json 面。

黑箱边界（值经手、语义不过手）：
- 目录（步骤/字段/值域）从上游三件套**机械转换**——display=模板 description、
  枚举=setting_options/material 原文，MAS 发版永不管理字段定义；
- 物化写入键集派生自当前模板键集（上游加载时会删除模板外未知键，派生键集
  天然落在白名单内）；值按模板默认值类型回写（布尔字符串语义归一）；
- 快照/还原走通用 ``app/utils/config_archive.py`` 文件级原语，单一归档池。

上游事实（nikkigallery/Whimbox v3.0.5 源码）：
- 三件套随 wheel 分发于 ``site-packages/whimbox/assets/``：
  ``default_config.json``（9 节 60+ 键，叶子形如 {value, description}）、
  ``setting_options.json``（7 键值域枚举）、``material.json``（169 材料）；
- ``configs/config.json`` 相对安装根，加载时合并新增默认键、删除未知键
  （config/config.py:60-92）——写入方只能写模板中已存在的键；
- 布尔语义键的 value 存字符串 ``"true"/"false"``（get_bool 判真集合
  ``'true','1','yes','on'``）；``ability_plan`` 为 int，
  ``realm_target``/``mira_crown_award_target`` 为原生 list。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.task.Whimbox.contracts import (
    WhimboxCatalog,
    WhimboxOptionDecl,
    WhimboxTaskDecl,
)
from app.utils import get_logger
from app.utils.config_archive import (
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
)
from app.utils.io import atomic_write, read_dict_file

logger = get_logger("奇想盒 上游配置面")

# ── 上游安装布局（相对安装根；发行版目录结构属「允许依赖」白名单） ─────────

APP_EXE_NAME = "whimbox_app.exe"
"""奇想盒 Electron 壳主程序名（安装根哨兵之一）"""

REL_PYTHON_EXE = "python-embedded/python.exe"
"""后端嵌入式 Python 解释器（app 的 backend-manager 以它拉起后端）"""

REL_SITE_PACKAGES = "python-embedded/Lib/site-packages"
REL_ASSETS_DIR = "whimbox/assets"
REL_CONFIG_FILE = "configs/config.json"

TEMPLATE_FILE = "default_config.json"
SETTING_OPTIONS_FILE = "setting_options.json"
MATERIAL_FILE = "material.json"

STEPS_SECTION = "OneDragonDefaultSteps"
OPTIONS_SECTION = "OneDragon"

# 上游 OneDragon 节中不由目录动态托管的键（MAS 静态字段物化或 app 专属）：
#   auto_start       仅 app 拉起场景消费，无头 CLI 不需要，MAS 永不写入；
#   change_account   由静态字段 OneDragon.IfRunAllAccounts 物化；
#   auto_close_game  由适配层恒物化为 true（关闭游戏是后续脚本流程的前提，不设开关）。
_UNMANAGED_ONE_DRAGON_KEYS = frozenset(
    {"auto_start", "change_account", "auto_close_game"}
)

# 值域来自 material.json 的键（激化幻境消耗材料；材料条目 jihua=True 者可选）
_MATERIAL_DOMAIN_KEYS = ("jihua_cost", "jihua_cost_2", "jihua_cost_3")

# 上游 get_bool 判真集合（写入侧只产生 "true"/"false" 两种）
_TRUE_STRINGS = ("true", "1", "yes", "on")


def parse_override_map(raw: object) -> dict:
    """把覆盖集 JSON（字符串或已解对象）安全解为 dict（损坏按空集）。

    覆盖集以 map 为最小语义单元（单键粒度无意义），损坏值按空集处理而不抛错：
    读侧（物化、展示快照）遇到坏值走「没有覆盖」，不该被它拦下。这是 MAS 侧
    自己的存储（非上游文件），但静默丢配置同样不可接受——损坏必须留痕。
    """

    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        logger.warning(f"奇想盒覆盖集 JSON 损坏，按空集处理: {str(raw)[:200]}")
        return {}
    if not isinstance(data, dict):
        logger.warning(f"奇想盒覆盖集 JSON 非映射，按空集处理: {str(raw)[:200]}")
        return {}
    return data


def _is_bool_string_template(default: object) -> bool:
    """模板默认值是否为布尔语义（bool 原生或 "true"/"false" 字符串）。"""

    if isinstance(default, bool):
        return True
    return isinstance(default, str) and default.strip().lower() in ("true", "false")


def _normalize_bool(default: object) -> bool:
    """把模板布尔语义默认值归一为 bool。"""

    if isinstance(default, bool):
        return default
    return str(default).strip().lower() in _TRUE_STRINGS


def _coerce_value(value: object, default: object) -> object:
    """把用户值按模板默认值类型回写（布尔字符串语义归一，其余原样透传）。"""

    if _is_bool_string_template(default):
        return "true" if bool(value) else "false"
    if isinstance(default, bool):
        return bool(value)
    return value


def _infer_field_type(default: object, options: tuple[str, ...]) -> str:
    """由模板默认值类型 + 值域有无机械推断前端控件类型。"""

    if _is_bool_string_template(default) or isinstance(default, bool):
        return "bool"
    if isinstance(default, list):
        return "multi_select"
    if isinstance(default, int) and not isinstance(default, bool):
        return "int"
    return "select" if options else "text"


def _write_config_or_hint(path: Path, payload: bytes) -> None:
    """原子写上游 config.json；目录不可写时给可操作的报错。

    上游默认装在 ``C:\\Program Files\\...`` 之类的受保护目录，普通用户只读：MAS 自身
    未提权时写 config.json 必然 ``PermissionError``（写临时文件那一步就失败）。这属
    「运行环境没准备好」而不是上游行为变化，报错必须直接给出出路——**脚本设置里的
    「以管理员运行」只提权奇想盒进程，不提权 MAS**，用户在那上面绕不出来。
    """

    try:
        atomic_write(path, payload)
    except PermissionError as e:
        raise RuntimeError(
            f"奇想盒配置目录不可写（{path.parent}）：请以管理员身份运行 AUTO-MAS 后重试；"
            "或把配置来源切到「直控」，配置全部在奇想盒 app 内维护（MAS 不写入）"
        ) from e


class WheelAssetsConfigSurface:
    """IUpstreamConfigSurface 默认实现（wheel 安装版资产布局）。

    Args:
        root_path: 奇想盒安装根（whimbox_app.exe 所在目录）。
    """

    def __init__(self, root_path: Path) -> None:
        self.root_path = Path(root_path)
        self.assets_dir = self.root_path / REL_SITE_PACKAGES / REL_ASSETS_DIR
        self.config_path = self.root_path / REL_CONFIG_FILE
        # 目录缓存：同一实例内重复读取命中（三件套共几十 KB）；surface 由调用方
        # 逐次新建（API 每次请求、每用户轮次），跨请求不共享此缓存
        self._catalog_cache: tuple[tuple, WhimboxCatalog] | None = None

    # ── 安装哨兵 ───────────────────────────────────────────────────────

    def check_install(self) -> str | None:
        """安装哨兵三件检查；报错分场景、用户可操作（覆盖首启未完成场景）。"""

        if not self.root_path.is_dir() or not (self.root_path / APP_EXE_NAME).is_file():
            return "请先安装奇想盒，并在脚本设置中填入 whimbox_app.exe 所在目录"
        if not (self.root_path / REL_PYTHON_EXE).is_file():
            return "奇想盒安装不完整（缺少 python-embedded 运行时），请重新安装奇想盒"
        if not (self.root_path / REL_SITE_PACKAGES / "whimbox").is_dir():
            return (
                "请先完整运行一次奇想盒 app 完成初始化（首启会自动下载安装后端；"
                "若下载失败请检查网络/代理后重新打开 app）"
            )
        return None

    def upstream_version(self) -> str:
        """读 site-packages 的 whimbox-*.dist-info 版本（仅提示用，不做硬门）。"""

        try:
            site_packages = self.root_path / REL_SITE_PACKAGES
            for entry in site_packages.iterdir():
                m = re.match(r"^whimbox-(.+)\.dist-info$", entry.name)
                if entry.is_dir() and m:
                    return m.group(1)
        except OSError as e:
            logger.warning(f"读取奇想盒后端版本失败: {e}")
        return "未知"

    # ── 三件套读取与目录转换（机械转换，非自建声明） ───────────────────

    def _read_assets(self) -> tuple[dict, dict, dict] | None:
        """读取三件套；任一缺失/损坏返回 None。"""

        try:
            template = json.loads(
                (self.assets_dir / TEMPLATE_FILE).read_text(encoding="utf-8")
            )
            setting_options = json.loads(
                (self.assets_dir / SETTING_OPTIONS_FILE).read_text(encoding="utf-8")
            )
            material = json.loads(
                (self.assets_dir / MATERIAL_FILE).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"读取奇想盒配置三件套失败: {e}")
            return None
        return template, setting_options, material

    def _assets_fingerprint(self) -> tuple | None:
        """三件套的 (mtime_ns, size) 指纹；文件不可读返回 None。"""

        stamp = []
        for name in (TEMPLATE_FILE, SETTING_OPTIONS_FILE, MATERIAL_FILE):
            try:
                stat = (self.assets_dir / name).stat()
            except OSError:
                return None
            stamp.append((name, stat.st_mtime_ns, stat.st_size))
        return tuple(stamp)

    def read_catalog(self) -> WhimboxCatalog:
        """读取任务目录：步骤开关 + 参数字段（上游三件套机械转换，mtime 缓存）。"""

        fingerprint = self._assets_fingerprint()
        if self._catalog_cache is not None and self._catalog_cache[0] == fingerprint:
            return self._catalog_cache[1]

        assets = self._read_assets()
        if assets is None or fingerprint is None:
            # 三件套不可读属内容损坏：响亮失败（不静默返回空目录），由 API 层
            # 转成可操作报错——空目录会把「读不到」伪装成「上游没有这些字段」，
            # 用户在编辑页看不出是坏了。
            raise RuntimeError(
                f"奇想盒配置三件套不可读（{self.assets_dir}），"
                "请先完整运行一次奇想盒 app 完成初始化"
            )

        template, setting_options, material = assets

        steps = []
        for key, item in (template.get(STEPS_SECTION) or {}).items():
            if not isinstance(item, dict):
                continue
            steps.append(
                WhimboxTaskDecl(
                    key=key,
                    display=str(item.get("description") or key),
                    section=STEPS_SECTION,
                )
            )

        # 材料值域：jihua=True 的材料名即显示名（零转换）
        jihua_materials = tuple(
            sorted(
                name
                for name, meta in material.items()
                if isinstance(meta, dict) and meta.get("jihua")
            )
        )

        options = []
        for key, item in (template.get(OPTIONS_SECTION) or {}).items():
            if key in _UNMANAGED_ONE_DRAGON_KEYS or not isinstance(item, dict):
                continue
            default = item.get("value")
            if key in _MATERIAL_DOMAIN_KEYS:
                domain: tuple[str, ...] = jihua_materials
            else:
                raw_domain = setting_options.get(key)
                domain = (
                    tuple(str(v) for v in raw_domain)
                    if isinstance(raw_domain, list)
                    else ()
                )
            normalized_default: object = (
                _normalize_bool(default)
                if _is_bool_string_template(default)
                else default
            )
            options.append(
                WhimboxOptionDecl(
                    key=key,
                    display=str(item.get("description") or key),
                    section=OPTIONS_SECTION,
                    field_type=_infer_field_type(default, domain),
                    options=domain,
                    default=normalized_default,
                )
            )

        catalog = WhimboxCatalog(
            steps=tuple(steps),
            options=tuple(options),
            upstream_version=self.upstream_version(),
        )
        self._catalog_cache = (fingerprint, catalog)
        return catalog

    # ── config.json 读取/物化（透传：值经手、语义不过手） ──────────────

    def _load_current_config(self, template: dict) -> dict:
        """读当前 config.json；文件缺失或内容为空映射时回退整体模板副本。

        解析失败 / 根节点非映射属**内容损坏**：``read_dict_file`` 抛
        ``ConfigCorruptedError``（带文件路径），本层原样上抛——由任务异常路径带
        路径上报（任务状态 + WS 通知），用户可在编辑页用配置恢复还原损坏前的版本。
        静默拿模板副本顶上会把「读到的现场是坏的」伪装成「按默认配置合并」，用户
        看不出上游配置已损坏（读取失败 OSError 同样原样上抛）。

        文件缺失不算损坏：上游首启会从同一模板播种，这里提前按模板播种，保证物化
        写入结构完整；``read_dict_file`` 对缺失与合法空映射 ``{}`` 都返回 ``{}``，
        两者在此同口径处理（空配置本就等价于全默认值）。
        """

        current = read_dict_file(self.config_path)
        if current:
            return current
        return json.loads(json.dumps(template))

    def _read_template_only(self) -> dict | None:
        """只读 default_config.json（目录读取之外的轻量路径）。"""

        try:
            data = json.loads(
                (self.assets_dir / TEMPLATE_FILE).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"读取奇想盒配置模板失败: {e}")
            return None
        return data if isinstance(data, dict) else None

    def config_file_exists(self) -> bool:
        """上游 config.json 是否存在（运行前快照语义的分叉输入）。"""

        return self.config_path.is_file()

    def _write_item(
        self, config: dict, template: dict, section: str, key: str, value: object
    ) -> None:
        """按模板结构合成 {value, description} 并写入（键必在模板内的白名单）。"""

        section_map = config.setdefault(section, {})
        template_item = (template.get(section) or {}).get(key)
        if not isinstance(template_item, dict):
            # 模板里没有的键：上游加载时会删除未知键，写了也静默失效，直接跳过
            return
        # description 优先沿用现值（上游 set() 同款行为），否则取模板默认
        description = template_item.get("description")
        existing = section_map.get(key)
        if isinstance(existing, dict) and existing.get("description"):
            description = existing["description"]
        default = template_item.get("value")
        section_map[key] = {
            "value": _coerce_value(value, default),
            "description": description,
        }

    def materialize_overrides(
        self,
        tasks: dict[str, bool],
        options: dict[str, object],
        *,
        run_all_accounts: bool,
    ) -> None:
        """把用户覆盖集按当前模板键集过滤后原子合并写入上游 config.json。

        Args:
            tasks: 步骤开关覆盖集 {步骤键: bool}（未知键被模板键集过滤）。
            options: 参数覆盖集 {键: 值}（同上过滤）。
            run_all_accounts: 物化为上游 OneDragon.change_account。
        """

        template = self._read_template_only()
        if template is None:
            raise RuntimeError("奇想盒配置模板不可读，请先完整运行一次奇想盒 app")

        config = self._load_current_config(template)

        step_keys = {
            key for key in (template.get(STEPS_SECTION) or {}) if isinstance(key, str)
        }
        for key, value in (tasks or {}).items():
            if key in step_keys:
                self._write_item(config, template, STEPS_SECTION, key, bool(value))

        option_keys = {
            key
            for key in (template.get(OPTIONS_SECTION) or {})
            if isinstance(key, str) and key not in _UNMANAGED_ONE_DRAGON_KEYS
        }
        for key, value in (options or {}).items():
            if key in option_keys:
                self._write_item(config, template, OPTIONS_SECTION, key, value)

        # 静态语义字段落两个流程级开关（模板键集过滤同款白名单）；
        # auto_close_game 恒为 true——关闭游戏是后续脚本流程的前提，不设用户开关
        if "change_account" in (template.get(OPTIONS_SECTION) or {}):
            self._write_item(
                config, template, OPTIONS_SECTION, "change_account", run_all_accounts
            )
        if "auto_close_game" in (template.get(OPTIONS_SECTION) or {}):
            self._write_item(
                config,
                template,
                OPTIONS_SECTION,
                "auto_close_game",
                True,
            )

        # 原子写走通用原语（fsync + 进程内写锁 + 失败清残留）；序列化保持上游的
        # indent=4，避免把用户的上游配置文件整篇重排
        _write_config_or_hint(
            self.config_path,
            json.dumps(config, ensure_ascii=False, indent=4).encode("utf-8"),
        )
        logger.info(
            f"已物化奇想盒一条龙配置: {len(tasks or {})} 个步骤开关, "
            f"{len(options or {})} 个参数覆盖"
        )

    # ── 快照/还原（通用 config_archive 原语，单一归档池） ──────────────

    def backup_root(self) -> Path:
        """归档池根：按 config.json 物理路径指纹分桶（项目级，跨脚本共享同池）。"""

        return (
            Path.cwd()
            / "data"
            / "WhimboxBackups"
            / "native"
            / config_root_key(self.config_path)
        )

    def snapshot_pre_run(self) -> str | None:
        """运行前强制归档 config.json。

        Returns:
            归档锚点时间戳；指纹与最近一份相同（未新建目录）时返回最新条目；
            config.json 本不存在返回 None（还原阶段按会话期新建清理）。
        """

        if not self.config_file_exists():
            return None
        created = self.archive_config()
        if created is not None:
            return created
        times = list_times(self.backup_root())
        return times[0] if times else None

    def archive_config(self, force: bool = False) -> str | None:
        """归档当前 config.json；返回新条目时间戳，指纹去重命中返回 None。"""

        if not self.config_file_exists():
            return None
        dest = archive_files(
            {self.config_path.name: self.config_path}, self.backup_root(), force=force
        )
        return dest.name if dest is not None else None

    def restore_pre_run(self, ts: str | None) -> None:
        """还原运行前归档条目；ts=None 表示运行前无 config.json，删除会话期新建文件。"""

        if ts is None:
            try:
                self.config_path.unlink(missing_ok=True)
            except OSError as e:
                # 删不掉不阻断收口，但不能谎报成功（文件还在，下次运行会读到它）
                logger.warning(f"删除会话期新建的奇想盒 config.json 失败: {e}")
                return
            logger.info("奇想盒 config.json 为会话期新建，已按运行前状态删除")
            return

        backup_dir = get_backup_dir(self.backup_root(), ts)
        if backup_dir is None:
            raise ValueError(f"奇想盒配置备份不存在: {ts}")
        src = backup_dir / self.config_path.name
        if not src.is_file():
            raise ValueError(f"奇想盒配置备份缺文件: {src}")
        _write_config_or_hint(self.config_path, src.read_bytes())
        logger.info(f"已还原奇想盒 config.json（运行前归档 {ts}）")

    # ── 恢复池用的同族函数（供 tools/restore_service.py 复用同池原语） ──

    def backup_dir_files(self, ts: str) -> dict[str, Path]:
        """归档条目内的文件集（预览用；目录式布局同 dir_files）。"""

        backup_dir = get_backup_dir(self.backup_root(), ts)
        if backup_dir is None:
            raise ValueError(f"奇想盒配置备份不存在: {ts}")
        return dir_files(backup_dir)

    def snapshot_entry(self, force: bool = False) -> str | None:
        """归档当前 config.json（恢复池 snapshot 用；force=True 恢复前存底）。"""

        return self.archive_config(force=force)

    def restore_entry(self, ts: str) -> None:
        """恢复池 restore 用：先 force 存底再还原（通用组件覆盖前强制归档语义）。"""

        self.snapshot_entry(force=True)
        self.restore_pre_run(ts)
