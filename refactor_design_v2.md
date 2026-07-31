# AUTO-MAS 重构设计文档（终稿）

> 版本：v3.7（2026-07-30）— **配置全量切流完成（1C + 2A）**
> 基于原 config_framework_v2 + 9 份设计草稿 + 多轮评审
> v3.1–v3.4：见版本注记与 §11–§12
> v3.5：Collection 开放 Entry 类型集为框架一等能力
> v3.6：P6 切流注记
> **v3.7：框架已迁入 `app/config/`；Global/Scripts/Games/Plan/Queue/Tools 全量 ConfigEntry；API/`AppConfig` 走新门面；ok_* 经 `automas.plugins` + `ScriptAdapterPlugin`；旧 ConfigBase 领域权威已废弃（仅留兼容别名/残桩）。首页与工具插件化仍不做。**

---

## 0. 设计说明

本次重构包含两项任务：

**配置基类**：现位于 `app/config/`（由原 `config_framework_v2` 迁入），含包结构、功能扩展与领域 definitions。

**插件系统**：基于新的设计思路重新设计插件系统。旧 `app/plugins/` 中事件总线、生命周期钩子、Schema 工具等已退出主启动；运行时以 `app/plugin` + `auto_mas_core` 为准。

几个关键决定：
- **预设字段统一放在 `types.py`**，新增字段与现有的放同一文件
- **UI 提示作为 Entry 的虚拟字段**：`ConfigEntry` 上挂载 `_ui.__ui_hints__`
- **select 是注解标记**：与 `encrypted()` 同级
- **取消 int 命名别名**，手写 `Field(ge=..., le=...)`
- **配置基类位于 `app/config/`**（原 `config_framework_v2` 已迁入），按应用层级组织；可直接使用 `app/utils`
- **本轮不做**首页组件插件化、工具页插件化（§5.10.2 / §5.10.4 / §6.4 仅保留草案，实施搁置）
- **开放 Collection 的 Entry 类型集是配置基类能力**；插件增删/热重载必须调用 Collection API
- **配置权威已全量切流**：`AppConfig` 根为 `setting/scripts/games/plans/queues/tools`；落盘 TOML；JSON→TOML 由 `app.config.migrate` 负责

---

## 1. 配置基类调整

### 1.1 包结构

```
app/config/
├── __init__.py
├── core/                  # 运行时核心
│   ├── node.py            # ConfigNode + NodeState
│   ├── entry.py           # ConfigEntry（含 __ui_hints__）
│   ├── group.py, collection.py, manager.py, staging.py
│   └── ...
├── fields/                # ref / encrypted / hints / select / legacy
├── definitions/           # Global / Scripts / Games / Plan / Queue / Tools
├── migrate.py
├── types.py, wire.py, errors.py, signals.py, shortcuts.py
└── tests/
```

### 1.2 support 与应用内组织

配置基类**不是**独立发布框架，而是 AUTO-MAS 应用代码的一部分。包结构调整与 `app/utils` 复用按**应用层级**优化，`app.config` 直接引用 `app.utils`。

| 旧文件 | 改造方式 |
|--------|---------|
| `support/constants.py` | 删除。常量移入 `types.py` 末尾、`fields/encrypted.py` |
| `support/logger.py` | 删除，直接 `from app.utils.logger import get_logger` |
| `support/security.py` | 删除，`encrypted.py` 直接 `from app.utils.security import ...` |
| 落盘 IO | `app/utils/io.py` 提供 `read_toml`/`write_toml`（原子写、2 空格缩进）；配置根与插件配置宿主调用之；`wire.py` 只保留 dict↔模型形状 |

### 1.3 预设字段补充

原则：**只补主程序 `ConfigBase` 校验器已在用、且迁移后仍需要的类型**；不为「将来可能用」发明校验器。Wire 形态统一为 **`str`（路径也是 str）**，非法纠正回退 **空字符串**（覆盖当前 v2 `FilePath→Path`/`DEFAULT_FILE_PATH` 语义，以兼容 TOML 与旧配置）。

**路径类**（对齐 `FileValidator`/`FolderValidator`/`ScriptRootPathValidator`/`EmulatorPathValidator`）：
- `FilePath`：已存在文件。展开 `~`/`%ENV%`、解析 `.lnk`、禁止工作目录及 `FORBIDDEN_*`。非法→`""`。
- `FolderPath`：已存在目录。同上，要求 `is_dir()`。非法→`""`。
- `ScriptRootPath`：脚本根目录；**放行工作目录**。非法→`""`。
- `EmulatorPath`：模拟器/游戏管理程序路径（对齐现 `EmulatorPathValidator`）。非法→`""`。
- `LoosePath`：可不存在；仅展开与格式清洗。非法→`""`。

**字符串/其它（有现成校验器依据）**：
- 保留：`UrlString`、`HHMMString`、`YmdString`、`YmdHmString`、`YmdHmsString`、`JsonDictString`、`JsonListString`、`KeyboardKeyString`
- 新增：`WindowsNameString`（←`UserNameValidator`）、`CliArgumentString`（←`ArgumentValidator`）、`CliArgumentListString`（←`AdvancedArgumentValidator`）

**不新增独立类型**（现配置多为裸 `str`，UI 用 `format`/`Select` 即可）：`ProxyUrlString`、`EmailString`、`CronString`、`VersionString`。代理地址继续 `str` 或复用 `UrlString`；邮箱用 `format="email"` 提示。

**删除**：`NonNegativeInt`、`PositiveInt`、`DayCount`（文档旧称 PortInt 仓库中不存在），统一手写 `Field(ge=..., le=...)`。

### 1.4 旧字段迁移：`legacy()` 注解

字段位置变更时用 `legacy()` 标记旧位置，激活时值回退：

```python
class MyConfig(ConfigEntry):
    class Data(ConfigGroup):
        username: Annotated[str, legacy(group="info", name="name")] = ""
```

在 `entry.py` 的 `_activate_from_payload()` 中检查带 `LegacyMarker` 的字段，旧位置有值则使用并写入新位置。

### 1.5 Collection 开放 Entry 类型集（框架一等能力）

插件会动态增删/重载集合允许的 Entry 类。这是 **`ConfigCollection` 的运行时 API**，不是插件系统私有逻辑。完整规格写入 `配置基类.md` §5.3；此处给应用侧结论。

#### 1.5.1 两种模式

| 模式 | ClassVar | 含义 | 典型 |
|------|----------|------|------|
| **closed** | `_entry_type_mode = "closed"`（默认） | 构造时 `_entry_types` 固定；禁止运行时改类型表 | 队列项、固定结构嵌套 |
| **open** | `_entry_type_mode = "open"` | `ACTIVE` 且集合**未锁**时可 `register` / `unregister` / `reload` | `scripts` / `games` |

#### 1.5.2 运行时 API（仅 open + ACTIVE + 集合未锁）

```python
async def register_entry_type(
    self, entry_cls: type[TEntry], *, owner: str
) -> None:
    """新增可选类型。类名已存在且 owner 不同 → CapabilityConflictError。
    类名已存在且 owner 相同 → 转交 reload_entry_type（禁止静默覆盖）。"""

async def unregister_entry_type(
    self, type_name: str, *, owner: str
) -> None:
    """删除可选类型。该类型仍有成员实例 → EntryTypeInUseError（阻止插件卸载）。
    owner 不匹配 → 拒绝。"""

async def reload_entry_type(
    self, entry_cls: type[TEntry], *, owner: str
) -> None:
    """同名类型原地换类并重载该类型全部成员配置。
    任一该类型成员 is_locked → EntryTypeLockedError。
    成功：同 uid rematerialize；失败整单回滚。"""
```

守卫（缺一不可）：

1. `activation_state == ACTIVE`
2. `not collection.is_locked`
3. `unregister`：`count(type_name) == 0`
4. `reload`：该类型每个成员 `not entry.is_locked`
5. `entry_cls` 必须是 Generic 上界 `TEntry` 的子类（运行时 `issubclass` + 静态见下）

`INITIALIZING` / `INACTIVE`：**禁止**改类型表（激活前类型集只能来自构造/`_default_entry_types`）。

#### 1.5.3 静态检查如何声明

Python 无法在类型系统里表达「运行时集合 {A,B,C} 可变」。折中：

**① 域公共基类作 Generic 上界（推荐）**

```python
class ScriptEntry(ConfigEntry):
    """所有脚本适配 Entry 的静态上界。"""
    # 仅放跨类型稳定字段；各插件子类扩展自己的 Group
    ...

class ScriptCollection(ConfigCollection[ScriptEntry]):
    _entry_type_mode: ClassVar[Literal["open"]] = "open"
    _default_entry_types: ClassVar[tuple[type, ...]] = ()  # 启动时由插件 register

class MaaScriptConfig(ScriptEntry):  # 插件提供
    ...
```

- `col[uid]` / `values()` 静态类型为 `ScriptEntry`（pyright 满意）。
- `register_entry_type` 标注为 `type[TEntry]` → 插件传入非子类会在检查期报错。
- 需要具体字段时：`cast` / `isinstance` / 窄化辅助：

```python
def require(self, uid: UUID, typ: type[T]) -> T:  # T bound ScriptEntry
    e = self[uid]
    if not isinstance(e, typ):
        raise TypeError(...)
    return e
```

**② closed 集合继续精确 Generic**

```python
items: ConfigCollection[ExampleQueueItem] = collection(ExampleQueueItem)
# _entry_type_mode 默认 closed；register_* 直接 TypeError
```

**③ 禁止** `ConfigCollection[Any]` 或无上界的裸 `ConfigEntry` 开放域——域集合必须有业务基类，否则静态与 `issubclass` 守卫都失去意义。

**④ 插件侧声明**

```python
class ScriptAdapterPlugin(ExtensionPlugin):
    def script_config_class(self) -> type[ScriptEntry]:  # 返回上界子类
        ...
    async def on_start(self) -> None:
        await Config.scripts.register_entry_type(
            self.script_config_class(), owner=self.plugin_name)
```

pyright 对 `-> type[ScriptEntry]` 会检查返回的类是否兼容。

#### 1.5.4 与锁定、重载的关系

| 操作 | Collection 锁 | 成员 Entry 锁 | 成员是否存在 |
|------|---------------|---------------|--------------|
| register 新类型 D | 须未锁 | — | — |
| unregister 类型 C | 须未锁 | — | **必须为 0** |
| reload 类型 C | 须未锁 | **该类型全部未锁** | 可有实例（会 rematerialize） |

插件系统 **只调用上述 API**；不得直接改 `_entry_types`，不得在未满足守卫时强行 rematerialize。

---

## 2. UI 组件提示机制

### 2.1 概述

`ConfigEntry` 上有一个固定虚拟字段 `_ui.__ui_hints__`，当 `entry.model_dump(include_reactive=True)` 时自动计算并输出：

```
entry.model_dump(→ 前端) → {
    "info": { "enabled": true, "name": "脚本名称" },
    "_ui": { "__ui_hints__": { "info": [ { "field": "enabled", "component": "switch" }, ... ] } }
}
```

### 2.2 实现

```python
class ConfigEntry(ConfigNode):
    _cfg_ui_hints: ClassVar[dict[str, list[ComponentHint]]] = {}
    class _Ui(ConfigGroup):
        __ui_hints__: Virtual[dict] = None

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs):
        super().__pydantic_init_subclass__(**kwargs)
        cls._cfg_ui_hints = build_ui_hints(cls)

    @virtual_field("_ui.__ui_hints__")
    def _get_ui_hints(self) -> dict:
        return type(self)._cfg_ui_hints
```

推导优先级：Annotated 标记 → 框架特殊标记（`TriggerDecl`→`button`、`VirtualDecl`→只读、`RefField`→`ref-select`、`EncryptedMarker`→密码）→ Python 类型推导（`bool`→`switch`、`int`→`number`、`str`→`input`）→ 预设类型推导（`HHMMString`→`time`、`FilePath`→`path`）→ 兜底→`input`。

### 2.3 ComponentHint 结构

```python
class ComponentHint(TypedDict, total=False):
    field: str
    component: str           # switch|number|input|select|path|time|button|ref-select|tags|...
    secret: bool
    readonly: bool
    format: str | None       # password|url|email|textarea|cron — 形态提示，非展示文案
    path_kind: str | None    # file|folder
    min: float | None
    max: float | None
    options: list[OptionHint] | None  # 见下
    multiple: bool
    ordered: bool
    endpoint: str | None     # 形式③：相对 API 路径
    deps: list[str] | None   # 显隐/选项依赖的字段路径（如 "info.game_type"）
    widget: str | None       # 覆盖组件（如 tags）
```

**禁止出现在 hint 中的项**（目标 3）：
- 任何 label/help/placeholder/description 文案
- 任何 width/span/size/栅格列数

**布局契约（前端独占）**：
- 宽屏：组内按 Ant Design 24 栅格排布；**每组宽度比例由前端按组名预定义**；单组件放不下则换行。
- 窄屏：每行固定 1 个组件。
- 后端 `__ui_hints__` 只保证组内字段顺序；不参与宽度计算。

`OptionHint`：`{"value": str}` 即可（展示文案前端用 i18n：`cfg.<类名>.<组>.<字段>.option.<value>`）。形式② ref 在运行时由前端或选项端点补 `label`（来自目标 Entry 的 `_display_name`），**不**把固定中文写入 hint。Trigger 字段 → `component: "button"`。

### 2.4 select 三种形式

select 是与 `encrypted()` 同级的注解标记。选项来源自动推导，是否多选由字段类型决定（`str` 单选、`list[str]` 多选）：

```python
@dataclass(frozen=True)
class Select:
    endpoint: str | None = None     # 形式③：HTTP 端点路径
    ordered: bool = False           # 多选顺序（仅 list[str] 时有效）
```

**形式①：Literal 值列表**。直接从 `Literal[]` 提取 value，前端查 i18n：
```python
class Game(ConfigGroup):
    type: Literal["mumu", "ldplayer", "general"] = "mumu"
```
输出 `{"field":"type","component":"select","options":[{"value":"mumu"}],"multiple":false}`

**形式②：ref 引用**。识别 `RefField` 标记，实际值是 UUID，展示值从目标 Entry 的 `_display_name` 读取，同时输出 `{label, value}`：
```python
class Data(ConfigGroup):
    script_ref: Annotated[str, ref("scripts")] = "-"
```

**形式③：HTTP 端点**。`Select(endpoint="...")` 标记端路径，前端直接访问获取 `[{label,value},...]`：
```python
class Data(ConfigGroup):
    emulator: Annotated[str, Select(endpoint="/api/plugins/xx/emulator-options")] = ""
```

### 2.5 tag 标签字段

```python
class Status(ConfigGroup):
    user_tags: Annotated[Virtual[list[dict]], ui(widget="tags")] = None
```

`__ui_hints__` 输出 `widget="tags"`，前端渲染为标签列表。

### 2.6 i18n 方案

主程序 i18n 在 `res/i18n/`，插件 i18n 在 `src/locales/`。插件激活时合并到全局字典，通过 WS 触发前端热重载。key 约定：
```
cfg.<类名>.<组名>.<字段名>.label|help
plugin.<插件名>.<widget|tool>.<id>.label|help
```

---

## 3. 文件 IO 统一

`app/utils/io.py`，统一 TOML 缩进（2 空格），提供原子写：

```python
def read_toml(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    with path.open("rb") as fp: return tomllib.load(fp)

def write_toml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(tomli_w.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)
```

`wire.py` 只保留数据类型定义，IO 统一走 `app/utils/io.py`。

---

## 4. 主程序配置管理

### 4.1 配置声明

```python
# app/config/definitions.py

class GlobalConfig(ConfigEntry):
    """全局设置，对应 config/setting.toml。"""
    class General(ConfigGroup):
        language: Literal["zh_CN", "en_US"] = "zh_CN"
        history_retention_days: int = 30
    class Update(ConfigGroup):
        auto_check: bool = True
        channel: Literal["stable", "beta"] = "stable"
    class Notify(ConfigGroup):
        enabled: bool = True
        server_chan_key: Annotated[str, encrypted()] = ""

class ScriptCollection(ConfigCollection[ScriptEntry]):
    """开放脚本集合。Entry 上界 ScriptEntry；运行时由插件 register/reload/unregister。"""
    _entry_type_mode = "open"
    _default_entry_types = ()

class GamesCollection(ConfigCollection[GameEntry]):
    """开放游戏集合。Entry 上界 GameEntry；运行时由插件 register/reload/unregister。"""
    _entry_type_mode = "open"
    _default_entry_types = ()
```

> 须先声明域基类 `ScriptEntry` / `GameEntry`（§1.5.3）。closed 集合（如队列项）保持精确 Generic，禁止运行时改类型表。

### 4.2 AppConfig 全局入口

```python
# app/core/config.py

from app.config.definitions import GlobalConfig, ScriptCollection, GamesCollection
from config_framework_v2 import config_manager


class AppConfig:
    """主程序配置总入口。"""

    setting: GlobalConfig
    scripts: ScriptCollection
    games: GamesCollection

    def __init__(self):
        self.setting = GlobalConfig(file=Path("config/setting.toml"))
        self.scripts = ScriptCollection(file=Path("config/scripts.toml"))
        self.games = GamesCollection(file=Path("config/games.toml"))

    async def load(self):
        await self.setting.activate()
        config_manager.register_root(self.setting)
        await self.scripts.activate()
        config_manager.register_collection("scripts", self.scripts)
        await self.games.activate()
        config_manager.register_collection("games", self.games)
        Path("config/plugins").mkdir(exist_ok=True)


Config = AppConfig()  # 全局单例
```

### 4.3 使用方式

所有模块统一通过 `Config` 访问配置：

```python
if Config.setting.general.language == "zh_CN": ...
for uid, script in Config.scripts.items(): ...
```

插件通过 `ctx.app_config` 指向 `Config` 单例。

---

## 5. 插件系统重设计

### 5.1 架构

```
app/
├── core/                  # 核心模块
│   ├── config.py          # AppConfig + Config 全局单例
│   ├── history.py         # 历史记录模块
│   ├── game_manager.py    # 游戏管理组件
│   └── script_types.py    # 脚本类型注册表
├── plugin/                # 插件运行时
│   ├── loader.py, context.py, config_host.py, services.py
│   ├── signals.py, versions.py, hmr.py
└── ...

plugins/auto_mas_core/      # 核心插件（不发 PyPI，版本号=主程序版本号）
└── src/auto_mas_core/
    ├── plugin.py            # BasePlugin, ExtensionPlugin
    ├── adapters/script.py, game.py
    └── signals.py
    # adapters/home.py、tool.py —— 本轮不做，后续再加
```

### 5.2 插件发现（双源）

插件是标准 PyPI 包：`pyproject.toml` 声明依赖与入口点。发现来源：

1. **已安装发行版**：`importlib.metadata.entry_points(group="automas.plugins")`
2. **本地 `plugins/` 目录**：扫描 `plugins/*/pyproject.toml`；解析同组 entry-points；将 `src/`（或包根）插入 `sys.path`；**同名本地优先覆盖**已安装包

本地包**不要求**事先 `pip install -e`。加载器直接按 entry point 的 `module:attr` 导入。

`pyproject.toml` 约定示例：

```toml
[project]
name = "automas-plugin-example"
version = "1.2.0"
dependencies = [
  "auto-mas-core>=5.0,<6",
  "httpx>=0.27",
]

[project.entry-points."automas.plugins"]
example = "automas_plugin_example.plugin:ExamplePlugin"

[tool.automas.plugin]
# 加载时插件依赖（插件名，非 PyPI 名；用于拓扑，独立于服务 provides/needs）
requires = ["auto_mas_core"]
# 可选弱依赖：缺失时降级加载，不阻断
wants = []
```

插件间 **发行依赖** 走 `[project].dependencies`；**加载顺序/共存依赖** 走 `[tool.automas.plugin].requires`（目标 4 + 9）。

### 5.3 单例化

取消多实例。每个入口点名对应唯一插件实例。配置：`config/plugins/<插件名>.toml`，由插件系统 `config_host` 用 `app/utils/io.write_toml` 原子写；开发者只声明 `config_class`。

### 5.4 核心插件与版本管理

`auto-mas-core`：**不发 PyPI**，代码在 `plugins/auto_mas_core/`，版本号 = 主程序版本（读 `res/version.json`）。

启动时：
1. 将 core 的 `src/` 加入 `sys.path`
2. 向 `importlib.metadata` 注册 **合成发行版**（或写入本地 `.dist-info` 等价物），使其它插件的 `Requires-Dist: auto-mas-core>=X,<Y` 可被解析
3. 加载其余插件前校验对 `auto-mas-core` 的版本约束；失败 → 状态 `error`，不激活

**升级预检**（目标 7）：主程序更新通道在下载/替换前调用 `plugin_versions.precheck_core_bump(new_version)`：
- 枚举已安装 + 本地插件对 `auto-mas-core` 的要求
- 任一冲突 → **拒绝升级**，返回结构化结果：`{plugin, required, new_core}`，前端提示「下列插件与新版本不兼容」

现有系统插件 `emulator`：**降级为普通本地/可发布插件**（`GameAdapterPlugin`），不再 `SYSTEM_PLUGIN_SPECS`；仅 `auto_mas_core` 保留「核心」地位。

### 5.5 加载器与生命周期

```python
@dataclass
class PluginRecord:
    plugin_name: str
    source: PluginSource          # installed | local | core
    status: str = "discovered"    # discovered → loaded → active → error
    plugin_instance: Any = None
    config: ConfigEntry | None = None
    ctx: PluginContext | None = None
    provides: set[str] = field(default_factory=set)
    needs: set[str] = field(default_factory=set)
    requires_plugins: set[str] = field(default_factory=set)  # 加载时插件依赖

class BasePlugin:
    """基础基类。可注册服务/HTTP；不被主程序协议分拣调用。"""
    plugin_name: str = ""
    provides: list[str] = []
    needs: list[str] = []
    wants: list[str] = []
    # 若未在 pyproject 写 requires，可用类属性兜底（二者合并）
    requires_plugins: list[str] = []
    config_class: type[ConfigEntry] | None = None

    def __init__(self, ctx: PluginContext): self.ctx = ctx
    async def on_start(self) -> None: ...
    async def on_load(self) -> None: ...
    async def on_stop(self, reason: str) -> None: ...
    async def on_unload(self) -> None: ...
    async def on_reload_prepare(self) -> None: ...
    async def on_reload_commit(self) -> None: ...

class ExtensionPlugin(BasePlugin):
    """标记基类。主程序按 isinstance 分拣到各 Manager。"""
    pass
```

加载流程：
1. 发现双源 → 去重（本地优先）
2. 解析发行依赖 + `requires_plugins` + 服务 `needs`
3. **两层拓扑**：先按 `requires_plugins` 排序；同层内再按服务 `provides/needs` 排序；环 → 拒绝加载并报错
4. 版本校验（含 core）→ `_load_one`：硬依赖检查 → 实例化 `config_class` 并 `activate` → 构建 ctx → 插件实例 → `on_load`/`on_start` → 拓展基类分拣注册

**移除** `@inject_*` / `@replace_*` 生命周期钩子体系（`lifecycle_hooks.py`）。脚本扩展点一律改为 `ScriptAdapterPlugin` 方法覆盖（目标 16）。

### 5.6 ctx

```python
class PluginContext:
    plugin_name: str
    config: ConfigEntry | None     # 本插件配置（插件系统托管落盘）
    app_config: AppConfig          # 主程序 Config 单例
    logger: Logger                 # module = "plugin.<插件名>"
    services: ServiceFacade        # 仅 provides/needs/wants
    app_signals: Namespace         # 主程序信号域
    plugin_signals: Namespace      # 插件系统信号域
    history: HistoryStore          # 全局历史（目标 15.1；脚本适配强依赖）
```

**明确移除**：`cache`、`runtime`/`runtime_api`、`log`（管道）、`page`、业务注册入口、字典配置代理。

**HTTP**：不再单独挂 `server` facade；通过 `services.expose_http(router_or_routes)`（或 `ctx.services` 上的等价 API）注册，且仅允许暴露已 `provides` 声明的能力面。

### 5.7 服务系统

保留 `provide/set/get/inject/miss`。修订：
- 去掉「服务变更自动重载消费者」；改为 `plugin_signals.service_changed.send(...)`
- owner：`instance_id` → `plugin_name`

### 5.8 事件系统（blinker）

```python
app_signals = Namespace()
plugin_signals = Namespace()
```

不自研 EventBus。异步约定对齐配置基类：receiver 可为 sync，若返回 awaitable 由统一 `_dispatch` 顺序 await（**不再** `asyncio.gather` 并发；与旧 EventBus 行为差异需在迁移清单中注明）。

信号常量最低集：`task_start`、`task_exit`、`config_changed`、`shutdown`、`plugin_loaded`、`plugin_unloaded`、`service_changed`、`capabilities_changed`。

### 5.9 热重载

- watchdog 监视本地 `plugins/*/src` 的 `.py` 变更。
- 配置变更**不**触发插件重载（走 ConfigEntry 信号）。
- 配置文件始终由 `config_host` 持有；重载不丢 `config/plugins/<名>.toml`。
- **禁止**「先 unregister 再 register」空窗；类型重载必须 `await collection.reload_entry_type`（§1.5 / §5.11.4）。

重载状态机（摘要，细节 §5.11.4）：

```
on_reload_prepare
  → 忙碌检查（该插件类型任务运行中 / 游戏 any_alive）→ 忙碌则拒绝重载
  → 导入新模块到 staging
  → 校验将注册的 key 与现 owner 一致（不得抢其它插件的 key）
  → owned 能力原地 replace（脚本注册表 / 游戏工厂 / entry_type / 服务）
  → 按需 rematerialize / rebuild_handle
  → 切换 plugin_instance；失败则回滚 staging，保留旧实例
  → on_reload_commit
  → plugin_signals.capabilities_changed
```

### 5.10 拓展插件基类

本轮实施：**ScriptAdapterPlugin** + **GameAdapterPlugin**。  
**HomepagePlugin**、**ToolPlugin** 仅保留接口草案，**本轮不实现、不迁移前端**（首页与工具页维持现有硬编码）。

#### 5.10.1 ScriptAdapterPlugin

```python
class ScriptAdapterPlugin(ExtensionPlugin):
    script_type_key: str = ""
    def script_config_class(self) -> type[ScriptEntry]: ...
    def user_config_class(self) -> type[ConfigEntry]: ...
    def plan_config_class(self) -> type[ConfigEntry] | None: ...
    async def check(self, rt: ScriptRuntime) -> str: ...
    async def prepare(self, rt: ScriptRuntime) -> None: ...
    async def run(self, rt: ScriptRuntime) -> None: ...
    async def finalize(self, rt: ScriptRuntime) -> None: ...
    async def on_crash(self, rt: ScriptRuntime, error: Exception) -> None: ...

    async def on_start(self) -> None:
        await super().on_start()
        script_types.register(self, owner=self.plugin_name)
        await Config.scripts.register_entry_type(
            self.script_config_class(), owner=self.plugin_name)

    async def on_stop(self, reason: str) -> None:
        # 有该类型实例时框架抛 EntryTypeInUseError → 卸载失败
        await Config.scripts.unregister_entry_type(
            self.script_config_class().__name__, owner=self.plugin_name)
        script_types.unregister(owner=self.plugin_name)
        await super().on_stop(reason)
```

生命周期：`check → prepare → run → finalize`，异常时 `on_crash`。  
类型表变更必须走 Collection API（§1.5）；HMR 走 `reload_entry_type`，不走本 `on_stop`。

#### 5.10.2 HomepagePlugin（本轮搁置）

> 接口草案保留供后续；本轮不实现 `HomepageManager`，不改 `Home.vue`。

```python
@dataclass
class HomeWidgetDecl:
    widget_id: str
    order: int = 100
    layout: str = "card"            # card | banner | stat | quick | list
    asset_paths: dict[str, str] = field(default_factory=dict)
    data_service: str | None = None

class HomepagePlugin(ExtensionPlugin):
    def widgets(self) -> list[HomeWidgetDecl]: ...
    async def widget_data(self, widget_id: str) -> dict: ...
```

#### 5.10.3 GameAdapterPlugin

（基类定义见下；完整管理见 §6.3。）

要点：
- `game_type` 为工厂键；Entry 类经 `Config.games.register_entry_type`（§1.5）。
- **卸载有实例 → EntryTypeInUseError**（须先删配置）。
- **HMR → reload_entry_type**（集合未锁且该类型成员未锁）。
- 进程拒删仍用 `remove_guard` + `any_alive`（与类型表正交）。

#### 5.10.4 ToolPlugin（本轮搁置）

> 接口草案保留供后续；本轮不改工具页 Tab / `ToolsConfig` 结构。

```python
@dataclass
class ToolDecl:
    tool_id: str
    order: int = 100
    entry_kind: str = "config_form"  # config_form | action | page_link
    config_class: type[ConfigEntry] | None = None
    action_service: str | None = None
    schedule_cron: str | None = None
    icon_asset: str | None = None

@dataclass
class ToolResult:
    ok: bool
    message: str = ""
    data: dict | None = None

class ToolPlugin(ExtensionPlugin):
    def tools(self) -> list[ToolDecl]: ...
    async def run(self, tool_id: str, config: ConfigEntry | None) -> ToolResult: ...
    async def on_schedule(self, tool_id: str, config: ConfigEntry | None) -> ToolResult: ...
```

### 5.11 能力注册与 Collection 类型集（插件侧）

> **Entry 类型表的增删改**由配置基类 `ConfigCollection` 执行（§1.5 / 配置基类.md §5.3）。  
> 本节只描述插件如何调用，以及脚本类型键 / 游戏工厂等**非 Collection 类型表**能力的 Owned-Key 规则。

#### 5.11.1 谁改类型表

| 动作 | 调用方 | 框架 API |
|------|--------|----------|
| 插件加载，新增类型 D | `on_start` | `await col.register_entry_type(D, owner=plugin_name)` |
| 插件卸载，删除类型 C | `on_stop` | `await col.unregister_entry_type("C", owner=...)` |
| 插件热重载，换类 C' | HMR（非 on_stop） | `await col.reload_entry_type(C', owner=...)` |

任一 API 不满足 §1.5 守卫 → 抛错 → 插件加载失败 / **卸载被阻止** / HMR 被拒绝。  
**不再**在卸载时把成员标成孤儿来「腾出」类型；有实例占用类型时卸载必须失败。

#### 5.11.2 非类型表能力（仍用 Owned-Key）

| 能力域 | 键 | 注册方 |
|--------|-----|--------|
| 脚本类型 | `script_type_key` | `script_types`（指向插件实例） |
| 游戏工厂 | `game_type` | `game_manager` |
| 服务名 | service name | `ServiceRegistry` |

语义同前：异主冲突、同主替换、按 owner 卸载。  
`script_type_key` / `game_type` 的 unregister 也要求：**没有仍依赖该键的运行中任务 / any_alive**；配置实例占用由 Collection 类型表守卫负责。

#### 5.11.3 可选类型列表如何刷新

```python
plugin_signals.signal("capabilities_changed").send(
    sender=plugin_name,
    domains=["entry_types", "script_types", "game_types"],
    added=[...], removed=[...], reloaded=[...],
)
```

前端类型下拉重拉 `/api/scripts/types`、`/api/games/types`（读 Collection 当前 `_entry_types` + 脚本/游戏注册表）。  
**不要**把「当前全部类型」快照进 `__ui_hints__`。

#### 5.11.4 热重载状态机（必须经 Collection）

```
on_reload_prepare(plugin P)
  → 集合未锁？否则拒绝
  → P 拥有的各 Entry 类型：成员全部未锁？否则 EntryTypeLockedError
  → 无该类型相关任务运行 / any_alive？否则拒绝
  → staging 导入新模块，得到新 entry_cls / handle_class / plugin
  → 对每个拥有的类型名：
       await collection.reload_entry_type(new_cls, owner=P)   # 框架内 rematerialize
  → script_types / game_manager 同主 replace
  → 插件自身 config：走 Entry 级重载（见 §5.12），同受 lock 约束
  → 切换 PluginRecord；capabilities_changed
  → on_reload_commit
失败 → 框架/插件共同回滚；禁止「先 unregister 再 register」空窗
```

HMR **禁止**调用 `unregister_entry_type` + `register_entry_type` 冒充重载（会在有实例时直接失败，且制造空窗）。

#### 5.11.5 卸载

```
on_stop / 卸载 P
  → await collection.unregister_entry_type(各类型, owner=P)
       若 EntryTypeInUseError → 卸载失败，提示先删除相关配置项
  → unregister script_types / game factories / services
  → deactivate 插件自身配置（toml 默认可保留）
```

有该类型配置实例存在 → **自然阻止卸载**。这是预期产品行为，不是异常旁路。

#### 5.11.6 启动时文件中有未注册类型

`activate()` 遇到 order 中类型不在 `_entry_types`：

- **不**自动删数据；
- 该成员进入 **pending_orphan** 占位（只读、可删），或整集 activate 报聚合错误（二选一，实现取：**占位 + 警告**，避免一颗坏类型拖死全集）；
- 待对应插件 `register_entry_type` 成功后，对该 uid 调用框架 `adopt_entry(uid, entry_cls)`（从占位 wire rematerialize 为正式成员）。  
  `adopt` 与 `reload` 同属框架 API，同样要求集合 ACTIVE、未锁。

注意：这与「运行时 unregister 要求零实例」不矛盾——启动占位是类型**尚未**注册；运行时删除类型则要求实例已清。

#### 5.11.7 Script / Game 基类挂钩

```python
# ScriptAdapterPlugin
async def on_start(self) -> None:
    await super().on_start()
    script_types.register(self, owner=self.plugin_name)
    await Config.scripts.register_entry_type(
        self.script_config_class(), owner=self.plugin_name)

async def on_stop(self, reason: str) -> None:
    await Config.scripts.unregister_entry_type(
        self.script_config_class().__name__, owner=self.plugin_name)
    script_types.unregister(owner=self.plugin_name)
    await super().on_stop(reason)

# HMR 路径（加载器，非 on_stop）
await Config.scripts.reload_entry_type(new_cls, owner=plugin_name)
script_types.register(new_plugin, owner=plugin_name)  # 同主替换
```

### 5.12 配置实例与锁定（在框架约束下）

#### 5.12.1 原则

1. **重载/改类型表是配置基类的事**；插件只触发。  
2. **集合锁**挡住类型表变更；**成员锁**挡住该类型 reload。  
3. **删类型**要求零实例 → 卸载与清配置顺序由用户保证。  
4. 实例稳定身份是 **uid**；`reload_entry_type` 可换 Python 对象，持有方按 uid 重取。

#### 5.12.2 三类实例

| 种类 | 存放 | 重载入口 |
|------|------|----------|
| A 插件自身配置 | `config/plugins/<名>.toml` | Entry 级：未锁则可 `rematerialize` 到新 `config_class` |
| B 开放集合成员 | scripts/games toml | **仅** `Collection.reload_entry_type` |
| C 嵌套成员 | 父 Entry 内 | 随父 Entry rematerialize |

A 类同样：`entry.is_locked` 则拒绝插件配置热重载。

#### 5.12.3 与旧「孤儿卸载」策略的关系

| 场景 | v3.4 旧说 | v3.5 |
|------|-----------|------|
| 卸载时尚有该类型实例 | 标孤儿，允许卸载 | **`EntryTypeInUseError`，阻止卸载** |
| 启动时类型未注册 | 孤儿占位 | 保留占位 + 插件加载后 `adopt` |
| HMR | 可 unregister 空窗 | **只准 `reload_entry_type`** |
| 字段选项 stale | 保留标 stale | 仍适用（端点 Select / Literal 收窄）；与类型表无关 |

#### 5.12.4 字段级过期可选值（类型仍在时）

类型仍注册、仅选项收缩时：不自动改字段值；UI `stale_fields`；提交新非法值 422。  
类型被卸（且已无实例）后：选项从 types API 消失，无残留实例可谈。

#### 5.12.5 静态检查（应用声明示例）

```python
# app/config/definitions.py
class ScriptEntry(ConfigEntry):
    """脚本域上界。"""

class ScriptCollection(ConfigCollection[ScriptEntry]):
    _entry_type_mode = "open"

class GameEntry(ConfigEntry):
    """游戏域上界。"""

class GamesCollection(ConfigCollection[GameEntry]):
    _entry_type_mode = "open"

class AppConfig:
    scripts: ScriptCollection
    games: GamesCollection
```

```python
# 插件
class EmuGameConfig(GameEntry):
    ...

async def on_start(self):
    await Config.games.register_entry_type(EmuGameConfig, owner=self.plugin_name)
```

`Config.games[uid]` 静态为 `GameEntry`；业务用 `isinstance` / `require(uid, EmuGameConfig)` 窄化。

---

## 6. 主程序模块适配

### 6.1 脚本管理模块

**现状**：`ScriptTypeRegistry` 管理 `ScriptTypeProvider`，两套存储体系（内建 ConfigBase + 插件 PluginScriptConfig），API 层大量 `isinstance` 分支。

**改造**：`ScriptTypeRegistry` 改为从 `ScriptAdapterPlugin` 子类注册，不再有 `ScriptTypeProvider`：

```python
class ScriptTypeRegistry:
    def __init__(self):
        self._plugins: dict[str, ScriptAdapterPlugin] = {}

    def register(self, plugin: ScriptAdapterPlugin) -> None:
        self._plugins[plugin.script_type_key] = plugin

    def get(self, key: str) -> ScriptAdapterPlugin | None:
        return self._plugins.get(key)

    def get_by_script_config(self, config: ConfigEntry) -> ScriptAdapterPlugin | None:
        return self._plugins.get(config._script_type_key, None)
```

统一使用 `ConfigEntry` 存储，删除 `PluginScriptConfig` 包装器、`script_config_codec` 双态编码。API 层去掉 `isinstance` 分支。`ScriptCreateIn.type` 改为字符串，前端通过 `GET /api/scripts/types` 获取可用类型。

任务调度器通过 `ScriptTypeRegistry.get(type_key)` 获取插件实例，调用生命周期方法。

### 6.2 历史记录模块

统一格式，适配器插件通过 `ctx.history.save(...)` 写入，格式一致、查询统一。

#### 6.2.1 存储

双文件存储：

```
config/history/YYYY-MM-DD/username/HH-MM-SS.json   # 结果数据
config/history/YYYY-MM-DD/username/HH-MM-SS.log    # 日志原文
```

起始时间由文件路径编码（目录名 = 日期，文件名 = 时间），JSON 内不存时间戳字段。

#### 6.2.2 JSON 记录结构

```json
{
  "status": "success",
  "message": "Success!",
  "type_key": "MAA",
  "username": "DLmaster",
  "data": {
    "recruit_statistics": {"3": 10, "4": 5},
    "drop_statistics": {"1-7": {"固源岩": 15, "代糖": 3}},
    "sanity": {"current": 120, "full_at": 18.5}
  }
}
```

#### 6.2.3 data 约束（已锁定）

`data` **必须**是以下两种形状，叶子必须是 `int` 或 `float`（**不**扩展字符串/列表等其它叶子类型）：

```
形状A（二层嵌套）：{ key: { key: int|float } }
  例: {"recruit_statistics": {"3": 10, "4": 5}}

形状B（三层嵌套）：{ key: { key: { key: int|float } } }
  例: {"drop_statistics": {"1-7": {"固源岩": 15}}}
```

不支持其他层级。同一个 data 下不同 key 可以有不同深度。

#### 6.2.4 合并规则

遍历所有 data 的每个 key：
- 首次出现 → 直接复制
- 再次出现 → 检查类型：
  - 两边都是 `int/float` → 累加
  - 两边都是 `dict` → 递归合并
  - 类型冲突 → 该位置标记 `{"__error__": -1}`，后续该位置的合并跳过

示例：
```python
# 正常合并
data1 = {"recruit_statistics": {"3": 10, "4": 5}}
data2 = {"recruit_statistics": {"4": 3, "5": 1}}
# → {"recruit_statistics": {"3": 10, "4": 8, "5": 1}}

# 类型冲突
data1 = {"metrics": {"count": 10}}
data2 = {"metrics": {"count": {"sub": 5}}}
# → {"metrics": {"count": {"__error__": -1}}}
```

#### 6.2.5 HistoryStore

```python
# app/core/history.py
history_store: "HistoryStore" = None

class HistoryStore:
    def __init__(self):
        self._root = Path("config/history")
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, *, username: str, type_key: str, status: str,
             message: str, logs: str, data: dict | None = None) -> Path:
        """保存一条执行记录。起始时间自动从当前时间获取。"""
        now = datetime.now()
        date_dir = self._root / now.strftime("%Y-%m-%d") / username
        date_dir.mkdir(parents=True, exist_ok=True)
        stem = now.strftime("%H-%M-%S-%f")[:15]  # HH-MM-SS-mmm，避免同秒覆盖
        record = {"status": status, "message": message, "type_key": type_key,
                  "username": username, "data": data or {}}
        json_path = date_dir / f"{stem}.json"
        json_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        log_path = date_dir / f"{stem}.log"
        log_path.write_text(logs, encoding="utf-8")
        return json_path

    def search(self, *, start_date: str, end_date: str,
               mode: str = "DAILY") -> dict[str, dict[str, dict]]:
        """按日期范围查询。按 mode 分组、按用户聚合、合并 data。"""
        result = {}
        for date_dir in sorted(self._root.iterdir()):
            if not date_dir.is_dir() or date_dir.name < start_date or date_dir.name > end_date:
                continue
            date_key = self._format_date_key(date_dir.name, mode)
            for user_dir in date_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                records = self._load_user_records(user_dir)
                if not records:
                    continue
                username = user_dir.name
                index = [{"date": f"{date_dir.name} {ts}", "status": "DONE" if r["status"]=="success" else "ERROR",
                          "jsonFile": str(user_dir / f"{ts}.json")} for ts, r in records]
                data_list = [r.get("data", {}) for _, r in records]
                error_info = {ts: r["message"] for ts, r in records if r["status"] == "error"}
                result.setdefault(date_key, {}).setdefault(username, {"index": [], "data": {}, "error_info": {}})
                result[date_key][username]["index"].extend(index)
                result[date_key][username]["data"] = self._merge_data(
                    [result[date_key][username]["data"]] + data_list)
                result[date_key][username]["error_info"].update(error_info)
        return result

    def get_detail(self, json_path: str) -> dict:
        """读取单条记录详情，附带日志内容。路径沙箱保护。"""
        root = self._root.resolve()
        p = Path(json_path).resolve()
        if not str(p).startswith(str(root)):
            raise ValueError("不允许访问历史目录外文件")
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        log_path = p.with_suffix(".log")
        data["log_content"] = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        return data

    def get_overview(self) -> dict[str, dict]:
        """今日概览（首页用）。"""
        today = datetime.now().strftime("%Y-%m-%d")
        data = self.search(start_date=today, end_date=today)
        overview = {}
        for users in data.values():
            for username, info in users.items():
                overview[username] = {
                    "LastProxyDate": info["index"][-1]["date"] if info["index"] else "暂无代理数据",
                    "ProxyTimes": len(info["index"]), "ErrorTimes": len(info["error_info"]),
                    "ErrorInfo": info["error_info"],
                }
        return overview

    def clean(self, retention_days: int | None = None) -> int:
        if retention_days is None:
            retention_days = Config.setting.general.history_retention_days
        if retention_days <= 0: return 0
        cutoff = datetime.now().date() - timedelta(days=retention_days)
        count = 0
        for date_dir in self._root.iterdir():
            if not date_dir.is_dir(): continue
            try: date = datetime.strptime(date_dir.name, "%Y-%m-%d").date()
            except ValueError: continue
            if date < cutoff: shutil.rmtree(date_dir); count += 1
        return count

    @staticmethod
    def _format_date_key(date_str: str, mode: str) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        if mode == "DAILY": return date_str
        elif mode == "WEEKLY": return d.strftime("%Y-W%V")
        else: return d.strftime("%Y-%m")

    def _load_user_records(self, user_dir: Path) -> list[tuple[str, dict]]:
        records = []
        for json_path in sorted(user_dir.glob("*.json")):
            try: records.append((json_path.stem, json.loads(json_path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, KeyError): continue
        return records

    @staticmethod
    def _merge_data(data_list: list[dict]) -> dict:
        result, conflicted = {}, set()
        def _merge(key_chain, old, new):
            if key_chain in conflicted: return old
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                return old + new
            if isinstance(old, dict) and isinstance(new, dict):
                merged = dict(old)
                for k, v in new.items():
                    sk = f"{key_chain}.{k}"
                    if k in merged:
                        if sk in conflicted: continue
                        merged[k] = _merge(sk, merged[k], v)
                    else: merged[k] = v
                return merged
            conflicted.add(key_chain)
            return {"__error__": -1}
        for data in data_list:
            for k, v in data.items():
                result[k] = _merge(k, result[k], v) if k in result else v
        return result
```

#### 6.2.6 插件使用

```python
async def finalize(self, rt: ScriptRuntime) -> None:
    rt.history.save(
        username=rt.user_configs[0].info.name,
        type_key=self.script_type_key,
        status="success",
        message="Success!",
        logs=rt.logger.dump(),
        data={"proxy_times": {"count": 3, "errors": 0}},
    )
```

### 6.3 游戏管理组件

**现状**：`_EmulatorManager` 通过 `EMULATOR_TYPE_BOOK` 硬编码三个模拟器实现，无信号连接，无进程保护。`emulator` 服务插件缺失。

**改造**：升级为 `GameManager` + `GameAdapterPlugin` 插件基类，将"模拟器管理"泛化为"游戏管理"。

#### 6.3.1 游戏配置字段

覆盖模拟器和 PC 游戏两种场景，使用 `ui(deps=["info.game_type"])` 控制字段显隐：

```python
class GameConfig(ConfigEntry):
    class Info(ConfigGroup):
        name: str = "新游戏"
        game_type: Literal["emulator", "pc"] = "emulator"
        """游戏大类。变更时触发 handle 重建。"""

    class Emulator(ConfigGroup):
        """game_type == "emulator" 时显示"""
        emu_type: Literal["mumu", "ldplayer", "general"] = "mumu"
        """模拟器子类型。变更时触发 handle 重建。"""
        path: str = ""; max_wait_time: int = 300
        boss_key: str = "[]"; force_kill: bool = False

    class Pc(ConfigGroup):
        """game_type == "pc" 时显示"""
        pc_type: Literal["general"] = "general"
        """PC 子类型。变更时触发 handle 重建。"""
        path: str = ""; args: str = ""
        wait_time: int = 300; force_kill: bool = False

    class Status(ConfigGroup):
        devices: Virtual[list[dict]] = None

    @virtual_field("status.devices")
    def _get_devices(self):
        handle = game_manager.get_handle(self.uid.hex)
        return handle.list_devices() if handle else []
```

#### 6.3.2 设备操作方式

所有操作统一通过 HTTP 端点执行。PC 和模拟器走同一接口，PC 的 `device_index` 固定 `"0"`，模拟器按实际设备传，启动器可传不同 `device_index`：

```python
ACTIONS = {"launch": lambda h,i: h.launch(i), "terminate": lambda h,i: h.terminate(i),
           "show": lambda h,i: h.set_visible(i,True), "hide": lambda h,i: h.set_visible(i,False)}

@router.post("/games/operate")
async def operate_game(data: GameOperateIn):
    handle = game_manager.get_handle(data.game_id)
    if not handle: raise HTTPException(404, "游戏实例未找到")
    await ACTIONS[data.action](handle, data.device_index)
    return {"status": "ok"}
```

#### 6.3.3 GameHandle 基类

`GameHandle` 是带约束的抽象基类，插件必须继承并实现所有方法：

```python
from abc import ABC, abstractmethod

@dataclass
class DeviceEntry:
    """单个设备实例的状态。前端轮询读取。"""
    index: str                  # 设备索引（"0", "1"）
    title: str                  # 显示名称
    status_code: int            # 状态码：0=在线 1=离线 2=启动中 3=关闭中 4=错误 5=未找到
    status_text: str            # 状态文本
    adb_address: str | None = None


class GameHandle(ABC):
    """游戏管理实例基类。每个配置项对应唯一一个实例。

    插件需继承此类并实现以下方法，框架通过 GameManager 管理实例生命周期。
    """

    @abstractmethod
    async def launch(self, device_index: str = "0", package_name: str = "") -> dict:
        """启动设备/游戏。返回连接信息（adb_address、pid 等）。"""
        ...

    @abstractmethod
    async def terminate(self, device_index: str = "0") -> None:
        """关闭设备/游戏。"""
        ...

    @abstractmethod
    async def set_visible(self, device_index: str, visible: bool) -> None:
        """显示/隐藏窗口。"""
        ...

    @abstractmethod
    async def is_alive(self, device_index: str = "0") -> bool:
        """检查指定设备/游戏进程是否存活。"""
        ...

    @abstractmethod
    async def any_alive(self) -> bool:
        """是否存在仍在运行的设备/进程；供 Collection.remove_guard 使用。"""
        ...

    @abstractmethod
    async def list_devices(self) -> list[DeviceEntry]:
        """列出所有可用设备及其状态。"""
        ...
```

#### 6.3.4 GameManager 设计

```python
# app/core/game_manager.py
class GameManager:
    def __init__(self):
        self._handles: dict[str, GameHandle] = {}
        self._factories: dict[str, Callable[[ConfigEntry], GameHandle]] = {}
        self._factory_owners: dict[str, str] = {}

    def register_factory(self, game_type: str, factory, owner: str): ...
    def unregister_factory(self, owner: str): ...

    def attach_collection(self, collection: ConfigCollection):
        collection.register_remove_guard(self._remove_guard)

        @collection.connect(phase="init", kind="add")
        async def on_init_add(sender, event):
            if event.uid: self._build_handle(event.uid, collection[event.uid])

        @collection.connect(phase="runtime", kind="add")
        async def on_runtime_add(sender, event):
            if event.uid: self._build_handle(event.uid, collection[event.uid])

        @collection.connect(phase="runtime", kind="remove")
        async def on_remove(sender, event):
            if event.uid: self._handles.pop(event.uid.hex, None)

    async def _remove_guard(self, collection, uid: UUID, entry: ConfigEntry) -> None:
        """框架在 commit 应用 remove 之前调用；抛错即拒绝删除并回滚。"""
        handle = self._handles.get(uid.hex)
        if handle is not None and await handle.any_alive():
            raise ConfigRemoveRejected("游戏进程仍在运行，请先关闭再删除")
```

#### 6.3.5 删除保护（框架内）

在 `ConfigCollection` 增加可注册的异步拒删守卫（与 ref `RESTRICT` 互补：ref 管外键，guard 管进程/业务存活）：

```python
# config_framework_v2/collection.py（新增）
RemoveGuard = Callable[["ConfigCollection", UUID, ConfigEntry], Awaitable[None]]

class ConfigCollection(...):
    def register_remove_guard(self, guard: RemoveGuard) -> None:
        self._remove_guards.append(guard)

    def unregister_remove_guard(self, guard: RemoveGuard) -> None:
        self._remove_guards.remove(guard)

    # _commit_op 处理 COLLECTION_REMOVE 时：
    # 1. entry = effective.data[uid]
    # 2. for g in _remove_guards: await g(self, uid, entry)   # 抛错 → 本笔事务失败回滚
    # 3. 再 _delete / 改 order / send(kind="remove")
```

```python
# errors.py
class ConfigRemoveRejected(ConfigError):
    """Collection 成员删除被 remove_guard 拒绝。"""
```

API 不再单独 `can_remove`；统一走框架：

```python
@router.post("/games/delete")
async def delete_game(data: GameDeleteIn):
    try:
        Config.games.remove(UUID(data.game_id))
        await Config.games.commit()
    except ConfigRemoveRejected as e:
        raise HTTPException(409, detail=str(e)) from e
    return {"status": "ok"}
```

要点：
- `remove()` 仍只 stage；**守卫在 commit 应用前**执行（因 `is_alive` 为 async，不能放在同步 `remove()` 里）。
- 守卫抛错 → 该 op 事务失败 → 工作区回滚，stage 可按现有 commit 错误聚合策略处理。
- remove 信号仅在删除成功后发出；handle 释放挂在 remove 信号上，时序正确。

#### 6.3.6 handle 重建

`game_type`、`emu_type`、`pc_type` 三个字段变更时均需重建 handle。在 update 端点中检查：

```python
@router.post("/games/update")
async def update_game(data: GameUpdateIn):
    entry = Config.games[UUID(data.game_id)]
    await entry.update(data.payload)
    if any(k in data.payload for k in ("game_type", "emu_type", "pc_type")):
        game_manager.rebuild_handle(data.game_id)
    return {"status": "ok"}
```

#### 6.3.7 GameAdapterPlugin 插件基类

游戏管理完全插件化。主程序不内置任何游戏类型工厂，`emulator`/`pc` 等均由插件注册。

一个游戏适配插件的职责：声明配置字段、提供 `GameHandle` 子类、提供自动搜索能力（可选）。

```python
# plugins/auto_mas_core/src/auto_mas_core/adapters/game.py

@dataclass
class InstalledGame:
    """自动搜索返回的已安装游戏/模拟器信息。"""
    game_type: str       # "emulator" / "pc"
    name: str             # 显示名称
    path: str             # 管理程序路径
    extra: dict = field(default_factory=dict)


class GameAdapterPlugin(ExtensionPlugin):
    """游戏适配插件基类。

    插件继承此类后需定义两个类属性：
    - game_type：类型标识（如 "emulator"、"pc"）
    - handle_class：GameHandle 子类，框架在需要时实例化

    并可选实现 search() 方法提供自动搜索。
    """

    game_type: str = ""
    handle_class: type[GameHandle] = GameHandle

    def game_config_class(self) -> type[ConfigEntry]:
        """配置项声明。返回 ConfigEntry 子类，自动获得 __ui_hints__。

        不同插件可以返回不同的 ConfigEntry 子类，通过 register_entry_type 注册到 GamesCollection。
        """
        raise NotImplementedError

    def search(self) -> list[InstalledGame]:
        """（可选）扫描系统上已安装的游戏/模拟器。"""
        return []

    async def on_start(self):
        await super().on_start()
        await Config.games.register_entry_type(
            self.game_config_class(), owner=self.plugin_name)
        game_manager.register_factory(
            self.game_type, lambda cfg: self.handle_class(cfg), owner=self.plugin_name)

    async def on_stop(self, reason: str):
        """真卸载。有该类型游戏实例时 unregister_entry_type 失败 → 阻止卸载。"""
        await Config.games.unregister_entry_type(
            self.game_config_class().__name__, owner=self.plugin_name)
        game_manager.unregister_factory(self.plugin_name)
        await super().on_stop(reason)
```

#### 热重载与插件增删

游戏 Entry 类型走 **§1.5 Collection API**；工厂键走 §5.11.2 Owned-Key。  
卸载有实例 → `EntryTypeInUseError`；HMR → `reload_entry_type`（成员未锁）。详见 §5.11–§5.12。

`AppConfig.games` 为 open `GamesCollection[GameEntry]`（见 §4.1）。

#### 6.3.8 API 端点

端点命名与旧 `app/api/emulator.py` 一致：

```
POST /api/games/get        → 查询（game_id 可选，空返回全部）
POST /api/games/add        → 添加
POST /api/games/update     → 更新（类型字段变化时 rebuild_handle）
POST /api/games/delete     → 删除（框架 remove_guard 进程保护 + ref RESTRICT）
POST /api/games/order      → 排序
POST /api/games/operate    → {game_id, device_index, action}
POST /api/games/status     → {game_id} → 设备状态列表
POST /api/games/emulator/search → 扫描已安装的模拟器/游戏
POST /api/games/options        → 游戏列表（供 ref 使用）
POST /api/games/device-options → {game_id} → 设备实例列表
```

#### 6.3.9 配置基类补充：connect 增加 kind 参数

当前 v2 的 `connect` 签名缺少 `kind` 参数，订阅者无法直接按事件类型（add/remove/set_order）过滤。需补充：

```python
# node.py 中 caller 签名补充 kind 参数
def caller(receiver=None, *, phase="runtime", kind=None, group=None, field=None):
    ...

def _wrap(receiver, phase, kind, group, field):
    def wrapper(sender, event, *args, **kwargs):
        if kind is not None and getattr(event, "kind", "") != kind:
            return None
        if group is not None and getattr(event, "group", None) != group:
            return None
        if field is not None and getattr(event, "field", None) != field:
            return None
        return receiver(sender, event, *args, **kwargs)
    return wrapper
```

使用示例（按事件类型精确订阅）：
```python
@collection.connect(phase="init", kind="add")    # 激活期新增
@collection.connect(phase="runtime", kind="add")  # 运行时新增
@collection.connect(phase="runtime", kind="remove")  # 删除
```

### 6.4 首页与工具（本轮搁置）

首页（`Home.vue`：command/quick/satellite/proxy）与工具页（`tools/index.vue`、`ToolsConfig`）**维持现状**，不引入 `HomepageManager` / 工具 manifest，不实现对应拓展基类。

后续插件化时再启用 §5.10.2 / §5.10.4 草案。本轮 History 的 `get_overview` 仍可供现有首页 proxy 区使用。

---

## 7. 全局对照

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| 配置基类包结构 | 平铺 14 模块 | core/ + fields/ 子包 |
| 预设字段 | types.py 中 12 个 | 增加路径/字符串校验类 |
| int 别名 | 有 PortInt 等 | 手写 Field(ge=..., le=...) |
| UI 提示 | Schema 四大模块 | `__ui_hints__` 虚拟字段 |
| select | PluginField.select() | Select 注解标记三种形式 |
| 旧字段迁移 | legacy_group/legacy_name | legacy() 注解 |
| 文件 IO | wire.py 直写 | app/utils/io.py 原子写 |
| 插件实例 | 多实例 | 单例 |
| 插件配置 | 字典代理 | ConfigEntry 活对象 |
| ctx | 10 项 | 6 项 |
| 事件 | 自研 EventBus 850 行 | blinker 两个 Namespace |
| 服务 | ServiceRegistry + 自动重载 | ServiceRegistry 简化 + 信号 |
| 生命周期钩子 | @inject_*/@replace_* 体系 | 基类方法覆盖 |
| 脚本适配 | ScriptAdapterDefinition + Hooks | ScriptAdapterPlugin 直接声明 |
| 历史记录 | 四套 save_*_log 散布 | 统一 HistoryStore |
| 模拟器管理 | EmulatorManager + 硬编码 EMULATOR_TYPE_BOOK | GameManager + GameAdapterPlugin + 框架 remove_guard |
| 首页 / 工具 | 硬编码 | **本轮维持硬编码**（插件化搁置） |

## 8. 被删除文件

| 模块 | 行数 |
|------|------|
| event_bus / event_contract / event_factory / decorators / event | 882 |
| log_pipeline / log | 436 |
| lifecycle_hooks | 452 |
| schema / fields / schema_utils / script_adapter_schema | 1884 |
| cache_store / runtime_api | 801 |
| config_store / script_config_store | 841 |
| script_config_codec / plugin_script_config | 269 |
| system | 86 |
| support/security.py | 37 |
| manager / loader / context（重写） | 3311 |

总计删除约 6,100 行，重写约 3,300 行。

## 9. 实施阶段

| 期 | 内容 | 依赖 | 验证 |
|----|------|------|------|
| P1 | 包结构调整 + logger/加密改引 `app/utils` + types.py + io.py + wire 精简 | — | 现有测试通过 |
| P2 | hints/select/legacy + `remove_guard` + `connect(kind=)` + **开放 Collection 类型 API**（register/unregister/reload/adopt） | P1 | 类型表守卫与 rematerialize 回滚单测 |
| P3 | history.py + game_manager.py + script_types.py + 游戏/脚本 API | P2 | API 回归 + CRUD + 存活拒删 |
| P4 | core 插件 + 加载器/HMR（§5.11 无空窗）+ ctx/services/versions + 单例化 | P2 | 插件冒烟 + HMR/增删冲突 |
| P5 | ScriptAdapter + GameAdapter + 内建 task 薄插件 | P4 | 脚本/游戏冒烟；执行转发 `app/task` |
| P6 | ConfigEntry 全量切换；旧 Schema / 钩子 / EventBus 退出主启动与业务热路径 | P2+P5 | 配置加载与核心 API 导入冒烟 |
| P7 | 清理旧文件 | P4-P6 | grep 零残余 |

P3 依赖 P2 的 `remove_guard` 与 `kind=` 后再接 GameManager。

## 10. 已确认决策

1. `support/` 删除；logger/security/io **直接引用** `app.utils`（配置基类是应用的一部分）。
2. **`app/task/` 已切到 ConfigEntry**：内建脚本由 `plugins/automas_script_*` 薄插件注册，存量执行器直接接收 definitions Entry 与 ConfigCollection。
3. 多选 ref 取消，ref 固定单选。
4. `Select` 标记在 `fields/select.py`，`ui()` 标记在 `fields/hints.py`。
5. 历史记录 `data` **坚持**仅两层/三层嵌套数字结构，类型冲突标记 `__error__`。
6. 双文件存储（json + log），起始时间由路径编码；文件名含毫秒。
7. 插件单例；双源发现；core 合成发行版 + 升级预检。
8. 加载依赖：`[tool.automas.plugin].requires` + 服务 `provides/needs/wants` 两层拓扑。
9. `__ui_hints__` 不含文案与宽度；Trigger→button；布局 24 栅格由前端定义。
10. 路径预设 Wire 类型为 `str`，非法回退 `""`。
11. **首页 / 工具本轮不插件化**，维持硬编码；对应基类草案搁置。Tools **存储与 API 已迁 ConfigEntry**。
12. **游戏拒删在框架内**：`Collection.register_remove_guard`，commit 应用 remove 前检查。
13. **开放 Collection**：`register/unregister/reload_entry_type` 为配置基类 API；仅 ACTIVE+未锁；删类型要求零实例；reload 要求该类型成员未锁。
14. **域集合静态上界**：`ScriptCollection[ScriptEntry]` / `GamesCollection[GameEntry]`；插件 Entry 必须继承上界。
15. **ok_script / okww**：主入口使用 `automas.plugins` 下的 v2 插件（`ScriptAdapterPlugin` + Entry 注册）；旧 entry point / `app.plugins` 适配层仅作运行时兼容，**不再是配置权威或主启动路径**。

### 10.16 全量切流 DoD（已完成）

- [x] 框架包在 `app/config/`（`core/` + `fields/` + `definitions/`）
- [x] `AppConfig` 根节点 `setting/scripts/games/plans/queues/tools`，`migrate` + `activate`
- [x] API 读写新门面（Wire / Entry）
- [x] 内建脚本与 ok_* 注册 `ConfigEntry` / `register_entry_type`
- [x] 旧 `app.models.config` 领域类降为 Entry 别名；配置权威不在 ConfigBase
- [x] `main.py` 仅新 `plugin_loader`
- [x] P6：业务配置路径全量使用 `app.config` / `ConfigEntry`
- [x] P7：删除 `config_framework_v2` shim，Python 业务代码无旧包导入
- [ ] 首页 / 工具插件化（本轮明确不做）

---

## 11. 评审修订（v3 → v3.1）

（历史记录，见版本注记。开放点已由 v3.2 关闭。）

### 11.1–11.4

见 git 历史中的 v3.1 正文；已被 §12 覆盖处不再重复维护。

---

## 12. 评审修订（v3.1 → v3.2）与二次审查

### 12.1 拍板落地

| 议题 | 决定 | 文档落点 |
|------|------|----------|
| 框架↔app 依赖 | 允许并鼓励复用 `app.utils`；按应用层级组织 | §0、§1.2、§10.1 |
| 首页 / 工具 | 本轮搁置，不插件化 | §5.10、§6.4、P6 |
| History `data` | 坚持 2/3 层数字树 | §6.2.3、§10.5 |
| 游戏拒删 | 框架 `remove_guard`，非仅 API | §6.3.4–6.3.5、P2 |

### 12.2 二次审查总判

| 结论 | 说明 |
|------|------|
| **可行，可开工** | 拍板后范围更清晰：配置基类应用内收敛 + 插件单例/脚本/游戏主线；首页工具不进本轮降低前端耦合。 |
| **剩余硬依赖** | P2 必须先交付 `remove_guard` + `connect(kind=)`，否则 GameManager 无法按设计接线。 |
| **范围收缩收益** | 去掉 Homepage/Tool 后，P3/P5/P6 可专注脚本配置链与游戏进程唯一性，风险更可控。 |

### 12.3 对照原 18 条目标（v3.2）

与 v3.1 相同处不重复。配置切流已经完成；本轮仅保留下列明确延期的插件化目标：

- **15.2 首页组件插件**、**15.4 工具插件**：草案保留，**不进入 P1–P7 验收**。
- **15.1 / 15.3**：已完成（脚本适配 + History 全局单例；游戏适配 + 框架拒删）。
- **配置全量切流（1C+2A）**：已完成，见 §10.16。

其余 1–14、16–18 已按 v3.1 修订执行；目标 1 的配置包已落位 `app/config/`，不再保留迁包或 strangler 路径。

### 12.4 仍存缺陷与实施约束

1. **`remove_guard` 与 stage 语义**：`remove()` 同步 stage 成功后，若 commit 时守卫拒绝，需保证 staged remove 被清空或整笔 commit 失败且 live 不变。应复用现有「单 op 事务失败记入 errors / 回滚」路径，并单测「stage 后守卫失败 → live 仍在、可再次 commit」。
2. **守卫顺序与 ref RESTRICT**：同一 commit 中若既有 remove 又有其它字段变更，守卫只拦 remove op；外键 RESTRICT 仍在目标 Entry 的 remove 信号路径。文档约定：**先跑 remove_guard，再 mutate，再 send(remove)**，避免「已删又被信号 RESTRICT」的混乱（RESTRICT 监听的是「目标被删」侧，逻辑仍成立）。
3. **多设备存活**：已增加 `GameHandle.any_alive()`；`remove_guard` 必须调用它，禁止只用默认 `is_alive("0")`。
4. **FilePath 语义**：v2 现为 `Path`+哨兵，迁移改为 `str`+`""`——P1 必改，否则 TOML 往返与旧配置不兼容。
5. **GlobalConfig 示意≠全集**：仍须另开字段对照表；Voice/UI/Start 等不能因 §4.1 示例被误删。
6. **History 同秒**：已要求毫秒文件名；`search`/`get_detail` 路径解析需同步接受新 stem。
7. **blinker 顺序 await**：与旧 EventBus 并发差异仍在；迁移清单需标注。
8. **emulator 服务兼容**：任务侧 `service.get("emulator")` 过渡策略未变——GameAdapter `provides=["emulator"]` 或改调 `game_manager`。
9. **未知 Entry 类型**：插件卸载后灰显可删——守卫不应拦截「无 handle 的僵尸项」删除（`handle is None` → 放行），以便清理残留。
10. **首页仍调 History**：搁置插件化后，`get_overview` API 保持，避免误删首页数据源。

### 12.5 建议的 GameHandle 补丁（写入实现）

```python
class GameHandle(ABC):
    ...
    async def any_alive(self) -> bool:
        """是否存在仍在运行的设备/进程；供 remove_guard 使用。"""
        ...
```

`GameManager._remove_guard` 调用 `any_alive()`，而不是裸 `is_alive()`。

### 12.6 本轮验收边界（DoD）

- [x] 配置基类：包结构 + 预设字段 + `__ui_hints__` + `legacy` + `remove_guard` + `connect(kind=)`；直接使用 `app.utils`
- [x] 插件：单例、双源、core 版本、requires 拓扑、简化 ctx、blinker、服务、热重载
- [x] 脚本：ScriptAdapterPlugin + HistoryStore（2/3 数字树）+ 注册表统一
- [x] 游戏：GameAdapterPlugin + 每配置一项一 handle + 框架拒删
- [x] 拆除：旧 Schema/钩子/EventBus 已退出主启动与业务热路径；兼容桩仅供旧入口导入；**不含**首页/工具前端改造
- [x] P5 内建脚本薄插件 + GameAdapter（`automas_game_emulator`）+ EmulatorManager 优先 GameManager
- [x] 明确不做（本轮）：HomepagePlugin / ToolPlugin 落地、工具 Tab 动态化

### 12.7 无开放拍板项

v3.1 §11.5 四问均已关闭。若后续重启首页/工具插件化，另开设计增量即可。

### 12.8–12.9（v3.3–v3.4）

能力表 HMR、实例 stale 等历史结论已被 **v3.5** 收敛：类型表变更收归 Collection；卸载有实例则失败（不再以孤儿放行卸载）。

### 12.10 v3.5 增量（Collection 开放类型集）

1. 框架新增 `register_entry_type` / `unregister_entry_type` / `reload_entry_type` / `adopt_entry`（配置基类.md §5.3）。
2. 插件增删/HMR **只能**调用上述 API；受 ACTIVE、集合锁、成员锁、实例占用约束。
3. 静态检查：开放域用业务基类作 `ConfigCollection[TBound]`；closed 域保持精确类型。
4. 启动未注册类型仍可占位，插件加载后 `adopt`；与「运行时删类型须零实例」并存。

实施单测：有实例时 unregister 失败；有锁成员时 reload 失败；集合锁定时三类 API 均失败；`type[ScriptEntry]` 不兼容子类在 pyright 下报错（用例或文档示例）。
