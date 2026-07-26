# 设计文档：配置基类替换收尾 与 插件系统重设计

> 版本：v1（2026-07-26，评审稿）。
> 前置阅读：[docs/config-v2-refactor-status.md](../config-v2-refactor-status.md)（已做/未做/防重复造轮子）。
> 范围：用户提出的 18 条要求的完整技术方案。本文只做设计，不含实现。

---

## 0. 总原则

1. **配置基类不再"替换"而是"收编"**：项目内 `app/configuration/v2/` 已是
   config_framework_v2 的生产化超集且默认启用（authoritative，539 测试锁定）。
   本轮对配置侧的工作 = 包结构微调 + introspect 增量 + 插件配置根迁移，
   **不动 v2 内核语义**（事务/信号两相位/世代存储/加密）。
2. **插件系统是重写**：现 `app/plugins/`（约 1.57 万行）保留概念（生命周期、服务、
   热重载），拆除机制（自研 EventBus、多实例、生命周期钩子、Schema 工具、
   pypi 市场锁定链），以 core 插件 + 4 拓展基类重建。
3. 所有新配置声明一律使用 v2 基类（ConfigEntry/ConfigGroup/Collection +
   Virtual/Trigger/ref/encrypted）。

---

## 1. 任务一：配置基类侧

### 1.1 包结构调整（要求 1）

允许调整源码包结构，方案（增量，不搬动被测内核文件）：

```
app/configuration/
  v2/                      # 内核，不动（node/entry/group/collection/fields/
                           #   signals/manager/staging/wire/encrypted/shortcuts）
  roots/                   # 八生产根 schema，不动
  introspect/              # ★新增：UI 组件提示（1.3）
    __init__.py            #   build_ui_hints(entry_cls) + 缓存
    components.py          #   注解→组件类型推导规则表
  persistence/             # 世代存储，不动
  compat/                  # r6 快照与迁移，不动
plugins/core/              # ★core 插件（见 2.4），其中 typing 层重导出
                           #   ConfigEntry 等符号，插件开发者只 import automas_core
```

归档版建议同步整理（供外部阅读，不参与运行）：`docs/design/reference/` 存放
配置基类.md 与归档差异说明即可，源码不必复制进仓（防止双份漂移）。

### 1.2 预设字段扩展（要求 2）

现状：八根已覆盖项目全部生产字段（见现状报告 §3）。本条收敛为**框架级预设
字段类型**的补齐——把项目里高频重复的 Annotated 组合提升为具名预设，放
`v2/types.py`（对齐归档命名）：

| 预设 | 语义 | 现有出处 |
|---|---|---|
| `HHMMString` / `YmdString` / `YmdHmString` / `YmdHmsString` | 纠正型日期时间串 | roots 各处 dt 字段 |
| `NonNegativeInt` / `PositiveInt` / `DayCount(-1..9999)` | 数值域 | RunTimesLimit 等 |
| `FilePath` / `FolderPath` / `ScriptRootPath` | 路径（.lnk/env 展开、黑名单） | legacy FileValidator 族移植 |
| `UrlString` / `ArgumentString` / `AdvancedArgumentString` | 拒绝型校验 | Notify/General |
| `KeyboardKeyString` | 按键名 | ToolsConfig.ArknightsPC |
| `WeekdaysMultiSelect` | 周几多选 | TimeSet/QueueItem |
| `EncryptedStr` = `Annotated[str, encrypted()]` | 密文串 | 全部 token/password |
| `JsonDictString` / `JsonListString` | JSON 字符串字段 | Data 组 |

补齐后 roots 逐步换用预设（机械替换，语义不变，测试保证）。

### 1.3 UI 组件提示虚拟字段（要求 3）★核心新设计

**目标**：Entry 自动暴露一个虚拟配置字段 `UI.Hints`（只读、不落盘），返回组件
提示字典：`{ 组名: [组件提示, ...] }`。取代插件 Schema 工具与脚本适配 schema
装饰两条旧管线。

**组件提示元素结构**（wire 形状，JSON 同形）：

```jsonc
{
  "field": "Source",            // 字段名（i18n 由前端按 组名+字段名 查）
  "component": "select",        // 组件类型
  "options": ["GitHub", "MirrorChyan", "AutoSite", "CNB"],  // 可选项值（展示值）
  "constraints": {"min": 0, "max": 9999},   // 数值域（number/slider 用）
  "readonly": false,            // Virtual 字段为 true
  "sensitive": true             // encrypted 字段为 true（前端渲染 password）
}
```

**注解 → 组件类型推导规则**（`introspect/components.py`，一次实现全局生效）：

| 注解形态 | component |
|---|---|
| `bool` | `switch` |
| `Literal[...]` / `OptionsValidator` 等价 | `select`（options=Literal args） |
| `int`/`float`（含 ge/le） | `number`；标注 `SliderHint()` 时 `slider` |
| `str` 默认 | `input` |
| `Annotated[..., encrypted()]` | `password` |
| `FilePath` / `FolderPath` | `path`（附 `path_kind`） |
| 多选列表（如 `WeekdaysMultiSelect`） | `multiselect` |
| `JsonDictString` / `JsonListString` | `json` |
| `Trigger` | **`button`**（要求明确：触发器=按钮） |
| `Virtual[T]` | `readonly` |
| `ref(target)` | `ref-select`（附 `ref_target` 集合名，前端调对应 combox 源） |
| 嵌套 Collection | 不进 Hints（由集合级 UI 承载） |

覆盖机制：极少数推导不出的场景用 `Annotated[T, UIHint(component="textarea")]`
标注覆盖（marker 进 pydantic metadata，introspect 优先读取）。

**明确不提供**：文案（label/help/placeholder——前端按 `组名.字段名` 查 i18n）、
组件宽度（前端自定义每组宽度比例）。

**实现方式**：`ConfigEntry` 基类上以框架内建虚拟字段暴露（子类零代码）；
结果按 Entry 类缓存（类定义期规格不变）。API/WS 侧随 `model_dump()`
（include_reactive=True）自然带出。

**前端渲染契约**：
- 宽屏：每组一行 24 栅格（a-row :gutter），组件宽度取前端**每组宽度比例表**
  （新增 `frontend/src/ui-hints/groupLayout.ts`，键=组名，值=各组件 span），
  放不下自动换行（a-row flex-wrap 原生行为）；
- 窄屏：每行固定 1 组件（`:xs="24"`）；
- i18n：新建 vue-i18n 层，key 约定 `cfg.<组名>.<字段名>.label|help`，
  插件字段 `plugin.<插件名>.<组名>.<字段名>.label|help`；
- 渲染器：改造现 `SchemaForm.vue`——字段判定/敏感策略/校验错误逻辑复用，
  数据源从旧 schema 换成 Hints，布局层从 12 列 CSS grid 换成 24 栅格。

---

## 2. 任务二：插件系统重设计

### 2.1 总体架构

```
┌────────────── 主程序 ──────────────┐
│ app/plugin_runtime/（新加载器，取代 app/plugins 大部分）
│   discovery.py   双通道发现（2.3）
│   loader.py      单例装载 + 依赖排序（2.6）
│   context.py     简化 ctx（2.7）
│   config_host.py 插件配置实例化→config/plugins/*.toml（2.8）
│   hmr.py         热重载（2.11，源自 dev_hmr）
│   versions.py    版本预检查（2.5）
├────────────── core 插件 ────────────┤
│ plugins/core/ → 包名 automas-core（不发 pypi，随主程序，版本=主程序版本）
│   automas_core/plugin.py      BasePlugin / ExtensionPlugin
│   automas_core/adapters/      script.py / home.py / game.py / tool.py（2.10）
│   automas_core/signals.py     app / plugins 两个 blinker Namespace（2.9）
│   automas_core/config.py      重导出 v2 配置基类符号
│   automas_core/context.py     PluginContext Protocol
└────────────── 第三方插件 ───────────┘
  pypi 包（entry point "automas.plugins"）或本地 plugins/<name>/ 目录
```

### 2.2 发布与依赖声明（要求 4）

- 插件 = 标准 pypi 包，`pyproject.toml` 声明：
  - `[project] dependencies`：python 依赖 + **插件间依赖**（插件互为普通
    pypi 依赖）+ `automas-core >=X.Y,<X+1`（核心版本约束，见 2.5）；
  - `[project.entry-points."automas.plugins"] <插件名> = "<包>:Plugin"`。
- 移除：自建市场锁定链（market.py/market_channel.py/wheelhouse 锁定/
  `_install_plugin_package` 白名单拦截）。安装即 `uv pip install`（保留镜像
  回退），卸载即 uninstall；市场页面改为纯 PyPI 检索视图。

### 2.3 双通道加载（要求 6）

1. **已安装依赖**：`importlib.metadata.entry_points(group="automas.plugins")`
   ——扫描当前运行环境（不再限定 `plugins/pypi/site-packages` 专用目录）；
2. **本地 plugins 目录**：扫 `plugins/*/pyproject.toml`，解析 entry point 与
   依赖后把 `src/` 直接挂 `sys.path` 导入（**不再 editable 安装**，去掉
   uv/entry-point 中转）；同名冲突时本地目录优先（开发态覆盖）。

### 2.4 core 核心插件（要求 7）

- 取代 `system.py` 的"系统插件"白名单概念；`auto_mas_core` SDK 包演进为
  `automas-core`。
- 不发 pypi：主程序启动时以 in-memory distribution 方式向 importlib.metadata
  注册 `automas-core==<主程序版本>`（版本号与主程序严格一致），使插件的
  pyproject 依赖解析、运行时 `version("automas-core")` 都能命中。
- 内容：全部插件基类 + ctx Protocol + 信号命名空间 + 配置基类重导出。
  **不再打包主程序 API 路由**（现 `get_core_plugin_routers()` 的路由回归主程序
  `app/api` 直管）。
- browser 等现"系统插件"降级为普通预装插件，正常走版本管理。

### 2.5 版本管理与升级预检查（要求 7 后半）

- 兼容基线 = core 插件版本（= 主程序版本）。插件在 pyproject 中声明
  `automas-core` 约束；加载时校验，不满足 → 拒载并提示。
- **主程序升级预检查**（新增 `versions.py`）：更新流程在下载前，用**目标版本号**
  对全部已安装插件的 `Requires-Dist: automas-core` 约束做离线求解；存在不满足
  的插件 → 拒绝升级，弹出冲突清单（插件名、当前约束、目标版本），用户先升级/
  卸载冲突插件。接入现 `app/services/update.py` 的更新确认链。

### 2.6 单例与生命周期（要求 5、8、16）

- **取消多实例**：一插件一实例，标识 = 插件名（instance_id 全链拆除：
  config_store 实例数组、EventBus scope="instance"、ServiceRegistry owner、
  `data/<instance_id>/`、前端实例列表 UI）。
- **生命周期定义保留**：状态机 `discovered → loaded → active → disposed →
  unloaded`（+error）与 WS 快照推送保留；插件侧钩子即基类方法：
  `on_load(ctx)` `on_start()` `on_stop(reason)` `on_unload()`
  `on_reload_prepare()` `on_reload_commit()`（可选实现，签名不变）。
- **移除脚本任务阶段钩子**（`lifecycle_hooks.py` 的 inject_*/replace_* 与
  hook 命名空间）：该扩展面由 ScriptAdapterPlugin 基类的可覆写方法承接（2.10.1）。

### 2.7 简化 ctx（要求 11）

```python
class PluginContext(Protocol):
    plugin_name: str
    config: ConfigEntry          # 本插件配置实例（v2 Entry，2.8）
    app_config: AppConfigFacade  # 主程序配置入口（NativeConfigFacade 只读+受控写）
    logger: Logger               # loguru，module=插件名
    services: ServiceFacade      # provide/set/get/inject（2.9 保留语义）
    signals_app: Namespace       # 主程序信号命名空间（blinker）
    signals_plugins: Namespace   # 插件系统信号命名空间（blinker）
    history: HistoryStore        # 历史记录全局单例（2.10.1，脚本适配用）
```

移除：`ctx.cache`/`data_dir`（插件自管数据目录）、`ctx.runtime/runtime_api`、
`ctx.log`（日志管道，脚本日志经适配基类方法参数传入）、`ctx.event`（自研
EventBus）、`ctx.page`/`ctx.server`（页面与 HTTP 注册收敛为 BasePlugin 能力，
见 2.10 说明——"业务注册"不再挂 ctx）。

### 2.8 插件配置声明与落盘（要求 10、17 后半）

- 插件类声明 `Config`（v2 ConfigEntry 子类，字段用 ConfigGroup）；
- 插件系统读取声明后实例化，注册为独立持久化根，落
  `config/plugins/<插件名>.toml`（进世代仓库统一事务/崩溃恢复），经
  `ctx.config` 提供；
- 淘汰 `PluginConfig.json` 的 `ConfigRaw` JSON 字符串双层编码与实例数组
  （一次性迁移：instances[0] → 新 toml，多余实例导出备份后丢弃）；
- 配置文件全权由插件系统管理，插件开发者不接触路径/落盘/热重载。

### 2.9 事件（要求 12）与服务（要求 13）

- **blinker 原生**：两个 `Namespace`——`app_signals`（主程序域：任务/脚本/
  配置变更转发）与 `plugin_signals`（插件域：生命周期、插件间自定义信号）。
  不做封装层：`ctx.signals_app.signal("task.start").connect(fn)`；异步接收者
  由发送侧统一 `await`（沿用 Config v2 signals 的 `_dispatch` 模式）。
  自研 EventBus、priority/once/error_policy、事件契约版本信封全部移除。
- **服务系统保留**：`ServiceRegistry` 语义不变（provide 声明、set 赋值、
  needs/wants 注入、拓扑加载排序）；owner 从 instance_id 改插件名。
  **移除"服务变更自动卸载重载消费者"隐藏行为**（`loader._before/_after/_sync`），
  改为发 `plugin_signals.signal("service.changed")`，消费插件自行决定响应。

### 2.10 基础/拓展插件基类（要求 14、15）

**BasePlugin**（基础基类）：生命周期方法 + 两种对外公开方式——
`register_service(name, obj)`（函数式，进 ServiceRegistry）与
`register_http(router)`（FastAPI APIRouter，挂 `/plugin/<插件名>/`，供第三方
程序调用）。拓展插件基类均继承 BasePlugin，因此**拓展插件同样可以注册服务**。

**四个拓展基类**（`automas_core/adapters/`，主程序直接调用）：

#### 2.10.1 ScriptAdapterPlugin（脚本适配）
```python
class ScriptAdapterPlugin(BasePlugin):
    def script_entry(self) -> type[ConfigEntry]: ...      # 脚本配置声明
    def user_entry(self) -> type[ConfigEntry]: ...        # 脚本用户配置声明
    def plan_entry(self) -> type[ConfigEntry] | None: ... # 计划表声明（可选）
    def create_task(self, script, user, mode, ctx) -> ScriptTask: ...  # 任务实现
```
- Entry 注册进 Scripts 多态集合（`_default_entry_types` 动态注册），UI 走
  Hints 虚拟字段；`ScriptTask` 基类提供 check/prepare/run/finalize/on_crash
  可覆写方法（承接原 hooks 扩展面）。
- **历史记录独立模块**（本条前置）：从 Config 双门面抽出
  `app/services/history_store.py`，全局单例 `history_store`，API：
  `record(entry) / query(range, user, mode) / clean(retention_days)`；
  存储沿用现目录形制；修复写侧 cwd 硬编码与 `/api/history/data` 路径沙箱；
  Config 门面同名方法改为薄委托（保 API cert 兼容），经 `ctx.history` 提供。

#### 2.10.2 HomeWidgetPlugin（首页组件）
```python
class HomeWidgetPlugin(BasePlugin):
    def widgets(self) -> list[HomeWidgetDecl]: ...
```
`HomeWidgetDecl = {id, order, size(1/2/3 档跨度), asset(图像相对路径，经
/plugin-assets/<插件名>/ 静态挂载), data_service(可选：服务名，前端经统一
`home.widget.data` WS 命令拉数据), interaction(点击跳转 route 或触发 Trigger)}`。
前端首页模块注册表从硬编码枚举改为"内建模块 + 插件 widgets"合并渲染，
声明式对齐现 pageDeclarations 模式；文案 i18n key `plugin.<插件名>.widget.<id>.*`。

#### 2.10.3 GameAdapterPlugin（游戏适配）＋游戏管理组件升级
```python
class GameAdapterPlugin(BasePlugin):
    def game_entry(self) -> type[ConfigEntry]: ...   # 游戏配置声明
    def create_manager(self, entry) -> GameManager: ...  # 游戏管理实现
```
- 原模拟器管理组件升级为**游戏管理组件**（`app/services/game_manager_host.py`）：
  - 订阅游戏配置 Collection 的 blinker 信号（add/remove/field change），
    保证**每个配置项 ↔ 一个 GameManager 实例**（uid 键控，add 即建、
    remove 即销毁），实例唯一且存活；
  - **进程未释放时拒绝删除配置项**：删除经 v2 事务 validator 相位信号，
    manager 报告进程存活 → handler 抛错 → 本笔回滚 → API 返回非 200 +
    中文 message（前端 game-center 删除报错路径已具备，直达用户）；
  - `GameManager` 接口：`launch/close/status/is_process_alive`，模拟器与
    直启客户端是两个内建 GameAdapter 实现。

#### 2.10.4 ToolPlugin（工具）
```python
class ToolPlugin(BasePlugin):
    def tool_entry(self) -> type[ConfigEntry]: ...   # 工具配置（含 Virtual 状态字段、Trigger 动作）
    def scheduled(self) -> ScheduleDecl | None: ...  # 定时执行声明（窗口/间隔），接入主程序 timer
```
基类指标（对齐现工具页两工具的共性）：配置即 UI（Hints 渲染，Trigger=手动
执行按钮，Virtual=状态/结果展示）、定时调度声明、执行入口
`async run(trigger_ctx)`、通知集成（走主程序 Notify）。前端工具页从硬编码
Tab 改为按已加载 ToolPlugin 动态生成 Tab（segmented + Hints 通用表单）。

### 2.11 热重载（要求 17）

保留 `dev_hmr.py` watchdog 机制，简化：监视对象 = 本地 plugins 目录源码；
`.py/.toml(pyproject)` 变更 → 单例 reload（prepare → unload → 清模块缓存 →
load → commit）；前端资源变更 → frontend_refresh。插件配置 toml 的变更不再
触发 reload（配置热更新走 v2 信号）。

### 2.12 移除 Schema 工具（要求 18）

删除：`schema.py`（PluginSchemaManager）、`fields.py`（PluginField）、
`schema_utils.py`、`script_adapter_schema.py`。全部能力由 v2 配置基类 +
introspect Hints 承接。前端 `SchemaForm` 改造见 1.3。

---

## 3. 迁移路线（建议分期）

| 期 | 内容 | 依赖 |
|---|---|---|
| P0 | 设计评审定稿；i18n 层选型落地（vue-i18n） | 本文 |
| P1 | introspect Hints + 前端 24 栅格渲染器 + groupLayout 表 | — |
| P2 | HistoryStore 独立 + 路径沙箱修复 | — |
| P3 | core 插件包 + 新加载器（双通道、单例、blinker、简化 ctx、config/plugins/*.toml）＋ 版本预检查 | P1 |
| P4 | 四拓展基类；ok_script_adapter/okww_adapter/browser 迁移到新基类 | P3 |
| P5 | 游戏管理组件升级（manager host + 拒删语义） | P4 |
| P6 | 首页/工具页插件化渲染；旧 schema 双管线下线 | P1/P4 |
| P7 | 旧 app/plugins 拆除、PluginConfig 根迁移、文档 | P3-P6 |

P1/P2 可并行先行；P3 起是重写主体。每期独立可发布、可回退。

## 4. 风险与开放问题

1. **NativeConfigFacade API 面不可破**（cert 锁定）：插件配置根新增走独立根，
   不动八根;历史门面方法改薄委托需过 authoritative_api_cert。
2. 取消多实例是**用户可见行为变更**：现网多实例配置迁移只保留首实例，
   需要发布说明与备份导出。
3. in-memory distribution 注册 `automas-core` 的实现需验证 uv/pip 解析路径
   （备选：启动时物化一个最小 dist-info 到私有 site 目录）。
4. 市场锁定链（wheelhouse fail-closed）移除后，发行包完整性校验策略需另行
   设计（超出本文范围，标记给发布流程）。
5. 前端 i18n 全量铺开工作量大：P1 仅要求配置表单域（Hints 消费面）接 i18n，
   其余页面文案渐进迁移。
