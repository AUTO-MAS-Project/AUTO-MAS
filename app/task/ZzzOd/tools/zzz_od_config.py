#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""绝区零一条龙（zzz-od）YAML 配置读写与实例槽备份恢复原语。

zzz-od 的 YAML 是唯一事实源，本模块只做最小封装（读-改-写 + 原子落盘），
不建平行配置模型：

- ``config/one_dragon.yml`` — 实例列表（= 账号）、活跃实例、运行范围
- ``config/{idx:02d}/`` — 实例目录：game_account.yml（区服/路径/账密）、
  game.yml、one_dragon/_group.yml（任务编排）、app_run_record/*.yml（运行记录）

MAS 用户配置（MaaEnd 式字段化）：账号/区服/任务编排存于
``ZzzOdUserConfig`` 的 ConfigItem 字段（web 直接编辑），运行时由字段生成
game_account.yml 与 one_dragon/_group.yml 写入当前活跃实例槽（备份 →
写入并清运行记录 → 恢复，MAS 不留痕迹）；「直控」模式全程不写槽。
"""

import shutil
import threading
from pathlib import Path
from typing import Any, Callable

from app.utils.io import read_file, replace_dir, write_file
from app.utils.logger import get_logger

logger = get_logger("绝区零一条龙配置")

# zzz-od game_account.yml 的 game_region 取值 → 中文展示
ZZZOD_GAME_REGION_LABELS = {
    "cn": "国服",
    "cn_b": "B服",
    "us": "美服",
    "eu": "欧服",
    "asia": "亚服",
    "twhkmo": "港澳台服",
}
"""区服取值（英文）到中文展示的映射"""

ZZZOD_GAME_LANGUAGE_LABELS = {"cn": "中文", "en": "英文"}
"""游戏语言取值到中文展示的映射"""

# zzz-od 运行记录 run_status 取值（AppRunRecord）
RUN_STATUS_NOT_RUN = 0
RUN_STATUS_SUCCESS = 1
RUN_STATUS_FAILED = 2
RUN_STATUS_RUNNING = 3

# 「全部实例」的 instance_run 原生取值；``--instance N`` 的临时实例索引仅在
# 「全部实例」分支生效（OneDragonApp.handle_init 只在该分支读 temp 列表），
# 因此注入运行前需临时落盘此值，结束后恢复原值。
# 「仅运行当前」= 只跑活跃实例：单槽注入时用它规避上游 wrap-around 对自己的
# 无意义登出/登录切换。
INSTANCE_RUN_ALL = "全部实例"
INSTANCE_RUN_CURRENT = "仅运行当前"

# zzz-od game_account.yml 的默认结构（与 GameAccountConfig 默认值一致）。
# zzz-od 只持久化非默认字段，读取侧合并此默认值即可得到完整配置。
# 注意 platform 的上游真实值为大写 'PC'（GamePlatformEnum.PC = ConfigItem('PC')，
# 单参构造 value=label），注入/导入必须写大写，小写会导致 init_controller
# 判断失败、controller 不创建（「未初始化控制器」整轮失败）。
DEFAULT_GAME_ACCOUNT: dict[str, Any] = {
    "platform": "PC",
    "game_region": "cn",
    "game_path": "",
    "game_language": "cn",
    "account": "",
    "password": "",
    "bilibili_account_name": "",
    "use_custom_win_title": False,
    "custom_win_title": "",
}

# 实例目录内的运行态目录：不属于配置包，注入/回读时排除、注入前清理
_RUN_RECORD_DIR = "app_run_record"

# 运行记录里的脏字节：一条龙用 non-atomic 写落盘，进程被杀/断电会在文件里留下
# NUL 填充；YAML 解析器遇到 NUL 直接抛 ReaderError。读侧只取 run_status，
# 丢掉这些不可见字符即可，不因一个坏文件让整个任务崩掉
_INVALID_YAML_CHARS = dict.fromkeys(range(0x20), None)

# 进程内读-改-写串行锁：write_file 只保证单次写原子，读-改-写整体在此串行，
# 避免切实例 / 写任务编排 / 写账号并发交错丢更新
_YAML_LOCK = threading.Lock()


def _one_dragon_file(root: Path) -> Path:
    return root / "config" / "one_dragon.yml"


def instance_dir(root: Path, idx: int) -> Path:
    """zzz-od 实例目录（config/{idx:02d}）。"""

    return root / "config" / f"{int(idx):02d}"


def validate_install(root: Path) -> None:
    """校验是 zzz-od 源码安装（``src`` 目录哨兵；不要求已初始化）。

    供安装目录判定与只读发现路径使用——``config/one_dragon.yml`` 由一条龙
    首次运行生成，全新安装尚未跑过一次时不存在，不应卡住启动器下拉、
    实例列表、任务目录等纯发现能力（读写路径自身会按需初始化）。

    Raises:
        ValueError: 目录不是有效的 zzz-od 源码安装。
    """

    if not (root / "src").is_dir():
        raise ValueError(
            f"{root} 下未找到 src 目录, 请确认是绝区零一条龙的源码安装目录"
        )


def validate_root(root: Path) -> None:
    """校验 zzz-od 源码安装目录已初始化（src 哨兵 + 实例配置存在）。

    Raises:
        ValueError: 目录不是有效的 zzz-od 源码安装，或一条龙尚未初始化。
    """

    validate_install(root)
    if not _one_dragon_file(root).is_file():
        raise ValueError(
            f"{root} 下未找到 config/one_dragon.yml, 请先运行一次一条龙本体完成初始化"
        )


def list_instances(root: Path) -> list[dict]:
    """读取实例（账号）列表，元素含 idx/name/active/active_in_od 等原生字段。"""

    data = read_file(_one_dragon_file(root)) or {}
    return [
        dict(item)
        for item in (data.get("instance_list") or [])
        if isinstance(item, dict)
    ]


def find_active_instance(root: Path) -> dict | None:
    """返回当前活跃实例；无实例或无 active 标志时返回 None。"""

    for item in list_instances(root):
        if item.get("active"):
            return item
    return None


def read_instance_run(root: Path) -> str | None:
    """读取 instance_run 原值（仅运行当前 / 全部实例）。"""

    data = read_file(_one_dragon_file(root)) or {}
    value = data.get("instance_run")
    return str(value) if value is not None else None


def write_instance_run(root: Path, value: str) -> None:
    """落盘 instance_run（配合 ``--instance`` 注入运行临时切换，结束后恢复）。"""

    with _YAML_LOCK:
        data = read_file(_one_dragon_file(root)) or {}
        data["instance_run"] = value
        write_file(_one_dragon_file(root), data)


def find_free_instance_idx(root: Path, used_idxs: set[int] | None = None) -> int:
    """返回最小空闲实例 idx。

    占位集合（按以下顺序合并，确保新槽不与任何已有槽冲突）：
    1. 原生 ``instance_list`` 的 idx
    2. 盘上 ``config/NN`` 目录（覆盖 finalize 失败导致 deepcopy 未回写、
       但实例目录已创建的情况——保证后续用户不会分配到同一槽）
    3. ``used_idxs``（本次会话内已分配 / 跨脚本 MAS 用户已绑定的槽）
    对齐 zzz-od ``create_new_instance`` 的最小正整数规则。
    """

    used: set[int] = set()
    used.update(int(item.get("idx", -1)) for item in list_instances(root))
    config_root = root / "config"
    if config_root.is_dir():
        for child in config_root.iterdir():
            if not child.is_dir() or not child.name.isdigit():
                continue
            used.add(int(child.name))
    if used_idxs:
        used |= {int(i) for i in used_idxs}
    idx = 1
    while idx in used:
        idx += 1
    return idx


def _registry_rmw(root: Path, mutator: Callable[[list[dict]], None]) -> None:
    """锁内读-改-写 one_dragon.yml 的 instance_list（保留其他原生字段）。"""

    with _YAML_LOCK:
        data = read_file(_one_dragon_file(root)) or {}
        entries = [
            dict(item)
            for item in (data.get("instance_list") or [])
            if isinstance(item, dict)
        ]
        mutator(entries)
        data["instance_list"] = entries
        write_file(_one_dragon_file(root), data)


def set_instance_active_in_od(root: Path, idx: int, value: bool) -> None:
    """切换实例是否参与「全部实例」运行模式（active_in_od），立即落盘。

    直控页实例管理用；只改目标实例的标志位，不触碰其他条目。
    """

    def mutate(entries: list[dict]) -> None:
        entry = next(
            (e for e in entries if int(e.get("idx", -1)) == int(idx)), None
        )
        if entry is None:
            raise ValueError(f"实例 {int(idx):02d} 不存在")
        entry["active_in_od"] = bool(value)

    _registry_rmw(root, mutate)


def set_instance_force_login(root: Path, idx: int, value: bool) -> None:
    """切换实例「运行前切换账号」（force_login_before_run），立即落盘。

    映射一条龙原生能力：开启后一条龙多账号运行到该实例前会强制登录其
    账号完成切换。MAS 不干涉，开关状态完全由一条龙自己消费。
    """

    def mutate(entries: list[dict]) -> None:
        entry = next(
            (e for e in entries if int(e.get("idx", -1)) == int(idx)), None
        )
        if entry is None:
            raise ValueError(f"实例 {int(idx):02d} 不存在")
        entry["force_login_before_run"] = bool(value)

    _registry_rmw(root, mutate)


def set_active_instance(root: Path, idx: int) -> None:
    """把指定实例设为当前活跃实例（active=True，其余清 False）。

    zzz-od 的「仅运行当前」跑的就是活跃实例；直控页选择实例后调用，
    让页面所选实例与实际运行实例保持一致。目标必须存在于原生注册表。
    """

    def mutate(entries: list[dict]) -> None:
        target = next(
            (e for e in entries if int(e.get("idx", -1)) == int(idx)), None
        )
        if target is None:
            raise ValueError(f"实例 {int(idx):02d} 不存在")
        for entry in entries:
            entry["active"] = entry is target

    _registry_rmw(root, mutate)


def rename_instance(root: Path, idx: int, name: str) -> None:
    """重命名实例（只改注册表 name，实例目录不变）。"""

    name = str(name).strip()
    if not name:
        raise ValueError("实例名称不能为空")

    def mutate(entries: list[dict]) -> None:
        entry = next(
            (e for e in entries if int(e.get("idx", -1)) == int(idx)), None
        )
        if entry is None:
            raise ValueError(f"实例 {int(idx):02d} 不存在")
        entry["name"] = name

    _registry_rmw(root, mutate)


def add_instance(
    root: Path, name: str, used_idxs: set[int] | None = None
) -> int:
    """新建实例：分配最小空闲槽并注册到 one_dragon.yml。

    - 槽分配避开原生注册表与 ``used_idxs``（跨脚本 MAS 已绑定槽）；
    - 创建实例目录与空 game_account.yml（仅持久化非默认字段，缺失即默认）；
    - 首个实例自动设为 active，新实例默认参与「全部实例」；
    - 返回新实例 idx，供调用方选中并加载。

    Raises:
        ValueError: 名称为空，或目标槽已被其他实例占用。
    """

    name = str(name).strip()
    if not name:
        raise ValueError("实例名称不能为空")
    idx = find_free_instance_idx(root, used_idxs)
    # 本轮已分配：写入 used_idxs 让后续同次会话的 add_instance / ensure_user_slot
    # 不会撞到本槽（find_free_instance_idx 也已扫盘 config/NN 双保险）
    if used_idxs is not None:
        used_idxs.add(idx)
    slot_dir = instance_dir(root, idx)
    slot_dir.mkdir(parents=True, exist_ok=True)
    if not (slot_dir / "game_account.yml").is_file():
        write_game_account(slot_dir, {})

    def mutate(entries: list[dict]) -> None:
        if any(int(e.get("idx", -1)) == idx for e in entries):
            raise ValueError(f"实例 {idx:02d} 已被占用")
        entries.append(
            {
                "idx": idx,
                "name": name,
                "active": not entries,  # 首个实例默认活跃
                "active_in_od": True,
            }
        )

    _registry_rmw(root, mutate)
    return idx


def remove_instance(
    root: Path, idx: int, protected_idxs: set[int] | None = None
) -> None:
    """删除实例：先从注册表移除，再删除实例目录（幂等）。

    保护：至少保留一个实例；``protected_idxs``（MAS 用户已绑定槽）不可删；
    被删实例为当前活跃时把剩余首个实例设为 active。

    Raises:
        ValueError: 目标实例不存在 / 是最后一个实例 / 被 MAS 用户绑定。
    """

    protected = {int(i) for i in (protected_idxs or set())}

    def mutate(entries: list[dict]) -> None:
        if len(entries) <= 1:
            raise ValueError("至少保留一个实例")
        entry = next(
            (e for e in entries if int(e.get("idx", -1)) == int(idx)), None
        )
        if entry is None:
            raise ValueError(f"实例 {int(idx):02d} 不存在")
        if idx in protected:
            raise ValueError(f"实例 {int(idx):02d} 已被 MAS 用户绑定，不能删除")
        remaining = [e for e in entries if int(e.get("idx", -1)) != idx]
        if entry.get("active") and remaining:
            remaining[0]["active"] = True
        entries[:] = remaining

    _registry_rmw(root, mutate)
    shutil.rmtree(instance_dir(root, idx), ignore_errors=True)


# ── 合成注册表视图（MAS 运行/配置会话期间临时替换 one_dragon.yml）──
#
# zzz-od 的实例注册表是安装级全局命名空间：持久注册会让 MAS 实例混进原生
# 世界（GUI 混排、原生「仅运行当前」可能误跑、跨脚本槽串号）。改为视图：
# 运行/会话窗口内把 one_dragon.yml 替换为「仅本脚本用户槽」的合成内容，
# 窗口结束恢复原生内容——原生 zzz-od 任何时候（窗口外）看到的都是自己的
# 实例。one_dragon.yml 进程启动读一次、之后纯内存（one_dragon_app 仅
# switch_instance 时落盘 active 标志），替换窗口对启动器安全。

_VIEW_SIDECAR_SUFFIX = ".mas-view.bak"


def _view_sidecar_path(root: Path) -> Path:
    return root / "config" / f"one_dragon.yml{_VIEW_SIDECAR_SUFFIX}"


def write_instance_view(
    root: Path,
    slots: list[tuple[int, str]],
    active_idx: int | None = None,
    instance_run: str = INSTANCE_RUN_ALL,
    force_login: bool = False,
) -> None:
    """把 one_dragon.yml 替换为合成视图（仅含给定 MAS 槽）。

    - 首次替换前把原生内容备份到 sidecar（已存在则不覆盖，保留最早的原生
      现场，保证崩溃后仍可完全还原）；
    - 视图内槽条目 ``active_in_od=True``（视图就是一条龙的全部世界），
      ``active`` 指向 ``active_idx``（缺省首个槽）；
    - ``instance_run``：多槽注入用「全部实例」（``--instance`` 列表在该分支
      生效）；单槽注入用「仅运行当前」——规避上游 wrap-around 对自己的
      无意义登出/登录切换；
    - ``force_login``：视图内槽条目 ``force_login_before_run=True``（单实例
      切换模式下用户配置了账号时置位，进入游戏前强制账密登录，避免沿用
      游戏当前登录态串号）；
    - 槽目录（config/{idx:02d}）不受影响，配队等复杂配置持久保留。
    """

    sidecar = _view_sidecar_path(root)
    original = _one_dragon_file(root)
    if not sidecar.exists():
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, sidecar)

    entries = [
        {
            "idx": int(idx),
            "name": str(name),
            "active": (active_idx if active_idx is not None else slots[0][0])
            == int(idx),
            "active_in_od": True,
            "force_login_before_run": bool(force_login),
        }
        for idx, name in slots
    ]
    with _YAML_LOCK:
        write_file(
            original,
            {"instance_list": entries, "instance_run": instance_run},
        )


def restore_instance_view(root: Path) -> None:
    """从 sidecar 恢复原生 one_dragon.yml（幂等；无 sidecar 时不动）。"""

    sidecar = _view_sidecar_path(root)
    if not sidecar.exists():
        return
    with _YAML_LOCK:
        shutil.copyfile(sidecar, _one_dragon_file(root))
        sidecar.unlink()


# ── 配置包读写（game_account.yml / one_dragon/_group.yml，目录参数化）──
# 参数既可是 zzz-od 实例目录，也可是 MAS 配置包目录（两者结构同构）。


def read_game_account(config_dir: Path) -> dict:
    """读取账号配置（区服/游戏路径/账密/语言）。"""

    data = read_file(config_dir / "game_account.yml") or {}
    return dict(data)


def write_game_account(config_dir: Path, patch: dict) -> dict:
    """按 patch 更新账号配置（读-改-写，保留未知字段），返回更新后的完整配置。"""

    path = config_dir / "game_account.yml"
    with _YAML_LOCK:
        data = read_file(path) or {}
        data.update(patch)
        write_file(path, data)
        return data


def user_field_patch(user_config) -> dict[str, Any]:
    """MAS 用户字段 → ``game_account.yml`` patch（仅非空字段，其余保留槽值）。

    与 :func:`write_game_account` 配套：注入/物化共用同一份「本页配置为事实源」
    的转换，字段缺省不落盘、槽内既有值保持。
    """

    patch: dict[str, Any] = {}
    for yaml_key, section, field in (
        ("game_region", "Game", "GameRegion"),
        ("game_path", "Game", "GamePath"),
        ("game_language", "Game", "GameLanguage"),
        ("account", "Game", "Account"),
        ("password", "Game", "Password"),
        ("bilibili_account_name", "Game", "BilibiliAccountName"),
        ("platform", "Game", "Platform"),
    ):
        value = str(user_config.get(section, field) or "").strip()
        if value:
            patch[yaml_key] = value
    # 布尔字段原样写入（YAML 布尔而非字符串）：MAS 字段是事实源，False 也下发
    patch["use_custom_win_title"] = bool(
        user_config.get("Game", "UseCustomWinTitle")
    )
    title = str(user_config.get("Game", "CustomWinTitle") or "").strip()
    if title:
        patch["custom_win_title"] = title
    return patch


def normalize_app_group_entries(items: list) -> list[dict]:
    """把任务编排条目归一化为 ``{"app_id": str, "enabled": bool}``（剔空）。

    ``_group.yml`` 写盘与 AppList 整表回填共用的同一套规则。
    """

    return [
        {"app_id": str(item["app_id"]), "enabled": bool(item.get("enabled"))}
        for item in items
        if isinstance(item, dict) and str(item.get("app_id") or "").strip()
    ]


def read_app_group(config_dir: Path) -> list[dict]:
    """读取一条龙任务编排（app_list，顺序即执行顺序，元素含 app_id/enabled）。"""

    data = read_file(config_dir / "one_dragon" / "_group.yml") or {}
    return [
        dict(item) for item in (data.get("app_list") or []) if isinstance(item, dict)
    ]


def write_app_group(config_dir: Path, app_list: list[dict]) -> None:
    """整表写回一条龙任务编排（app_id + enabled，顺序即执行顺序）。"""

    write_file(
        config_dir / "one_dragon" / "_group.yml",
        {"app_list": normalize_app_group_entries(app_list)},
    )


def read_team_list(config_dir: Path) -> list[dict]:
    """读取预备编队原始持久化条目（team.yml 的 team_list）。"""

    data = read_file(config_dir / "team.yml") or {}
    return [
        dict(item) for item in (data.get("team_list") or []) if isinstance(item, dict)
    ]


# 预备编队固定数量（与上游 TeamConfig.team_list 一致：缺失项补默认编队）
TEAM_LIST_SIZE = 20


def expand_team_list(config_dir: Path) -> list[dict]:
    """展开为固定 20 个编队的完整列表（与上游 ``TeamConfig.team_list`` 同规则）。

    已持久化条目原样返回（成员缺失补 unknown 占位），其后补
    「编队N / 全配队通用 / 无成员」默认项直至 20 个。
    """

    raw = read_team_list(config_dir)
    expanded: list[dict] = []
    for i, item in enumerate(raw):
        agents = item.get("agent_id_list")
        expanded.append(
            {
                "idx": i,
                "name": str(item.get("name") or f"编队{i + 1}"),
                "auto_battle": str(item.get("auto_battle") or "全配队通用"),
                "agent_id_list": (
                    [str(a) for a in agents]
                    if isinstance(agents, list) and agents
                    else ["unknown", "unknown", "unknown"]
                ),
            }
        )
    for i in range(len(raw), TEAM_LIST_SIZE):
        expanded.append(
            {
                "idx": i,
                "name": f"编队{i + 1}",
                "auto_battle": "全配队通用",
                "agent_id_list": [],
            }
        )
    return expanded


def write_team_list(config_dir: Path, teams: list[dict]) -> list[dict]:
    """整表写回预备编队（名称 + 绑定配队方案；成员按行保留既有值）。

    成员取值优先级：传入行自带的 agent_id_list（外部全量写回场景）> 既有行
    同下标成员 > unknown 占位（与上游 PredefinedTeamInfo 补齐规则一致）。
    """

    existing = read_team_list(config_dir)
    normalized: list[dict] = []
    for i, item in enumerate(teams):
        if str(item.get("name") or "").strip() == "" and i >= len(existing):
            continue
        # 配队方案字段前端发 autoBattle、磁盘/上游均用 auto_battle：两键兼容
        auto_battle = (
            str(item.get("auto_battle") or item.get("autoBattle") or "全配队通用")
        )
        incoming_agents = item.get("agent_id_list")
        prev_agents = existing[i].get("agent_id_list") if i < len(existing) else None
        agents_src = (
            incoming_agents
            if isinstance(incoming_agents, list) and incoming_agents
            else (prev_agents if isinstance(prev_agents, list) and prev_agents else None)
        )
        agents = (
            [str(a) for a in agents_src] if agents_src else ["unknown", "unknown", "unknown"]
        )
        normalized.append(
            {
                "name": str(item.get("name") or f"编队{i + 1}"),
                "auto_battle": auto_battle,
                "agent_id_list": agents,
            }
        )
    write_file(config_dir / "team.yml", {"team_list": normalized})
    return normalized


def predefined_team_options(config_dir: Path) -> list[dict]:
    """预备编队选项（对齐上游体力计划 GUI 的下拉构造）。

    「游戏内配队」(-1) 前置 + 全部 20 个编队（expand_team_list 补默认名）；
    value 为编队下标（-1=不指定，沿用配队方案），供 predefined_team_idx
    类字段/列作为动态选项。
    """

    return [{"label": "游戏内配队", "value": -1}] + [
        {"label": str(item["name"]), "value": int(item["idx"])}
        for item in expand_team_list(config_dir)
    ]


# ── 运行记录（结果权威来源）──


def snapshot_run_records(root: Path, idx: int) -> dict[str, int]:
    """快照当前实例全部任务的运行状态（app_id → run_status）。"""

    record_dir = instance_dir(root, idx) / _RUN_RECORD_DIR
    result: dict[str, int] = {}
    if not record_dir.is_dir():
        return result
    for path in sorted(record_dir.glob("*.yml")):
        try:
            data = read_file(path, format=".sanitized.yaml") or {}
        except Exception as exc:  # noqa: BLE001 - 单个坏记录不应中断整个任务
            logger.warning(f"运行记录读取失败，按未跑处理：{path.name}：{exc}")
            data = {}
        try:
            result[path.stem] = int(data.get("run_status", 0) or 0)
        except (TypeError, ValueError):
            result[path.stem] = 0
    return result


def diff_run_records(
    before: dict[str, int], after: dict[str, int]
) -> list[tuple[str, int, int]]:
    """对比运行前后快照，返回发生变化的 (app_id, 运行前状态, 运行后状态)。

    运行中（3）的任务不计入——等终态后的最终快照再比；
    前后一致的任务不计入（调用方按「已完成且未重跑」另行判定跳过）。
    """

    diffs: list[tuple[str, int, int]] = []
    for app_id, new_status in after.items():
        if new_status == RUN_STATUS_RUNNING:
            continue
        old_status = int(before.get(app_id, 0))
        if old_status == new_status:
            continue
        diffs.append((app_id, old_status, new_status))
    return diffs


def clear_run_records(root: Path, idx: int) -> None:
    """清空实例运行记录，让 zzz-od 把所有任务视为未完成（每用户独立跑）。

    注入用户配置后调用：清空后快照即为全零基准，跑完 diff 出的即本用户
    本次结果。
    """

    shutil.rmtree(instance_dir(root, idx) / _RUN_RECORD_DIR, ignore_errors=True)


# ── 实例槽备份 / 恢复（运行与配置会话的现场保护）──


def _atomic_copytree(source: Path, target: Path) -> None:
    """目录整体替换, 覆盖目标已有内容（先清后拷, 不再走 tmp + rename）。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    replace_dir(source, target)


def backup_instance(root: Path, idx: int, backup_dir: Path) -> None:
    """把实例目录整体备份（注入前调用，供 restore_instance 原样恢复）。"""

    shutil.rmtree(backup_dir, ignore_errors=True)
    backup_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(instance_dir(root, idx), backup_dir)


def restore_instance(root: Path, idx: int, backup_dir: Path) -> None:
    """把备份的实例目录原样恢复（幂等，恢复后由调用方清理备份）。"""

    _atomic_copytree(backup_dir, instance_dir(root, idx))
