# AUTO-MAS v6 进度记录

> 本文件由长期任务持续更新。时间基准：2026-07-26。
> 证据标注：observed = 已直接验证；inferred = 由源码/结构推断；unverified = 尚未验证。
>
> **会话总结：前端 UI、WS v2 自动化收口与 Config v2 native authoritative
> 切换均已完成；后端全量 pytest 已通过。**

## 环境

- 工作树：D:\AM6，HEAD=aceb651a（detached，checkpoint 提交），脏文件 384 条（observed）。
- PowerShell 7.6.4（observed）；yarn 4.9.1 / node 24.14.1（observed）。
- 前端依赖：`yarn install --immutable` 完成（16.9s，peer 依赖警告不阻塞，observed）。
- Python 测试环境：已创建本地 `.venv`，最小补齐 `tomli-w`、`blinker`、
  `pytest-asyncio`；测试命令临时复用系统已有运行依赖（observed）。
- 短临时目录 D:\AM6T 已创建（TEMP/TMP 用）。
- 真实机源码回传包：`D:\AUTO-MAS-v6-real-machine-handoff-20260726-082053-r3.zip`
  （非 Alpha）；含基线补丁、新增文件、测试提示词、报告模板和逐文件 SHA-256，
  已做补丁反向检查、源/副本哈希对比及 ZIP 中央目录/载荷校验（observed）。

## 已完成事项

### 1. 交接说明 4 项修复复核（任务 #1，源码层 observed，测试层待 vitest 结果）

1. `app/core/task_manager.py`：租约路径全部使用 `Config.ScriptConfig[uid]` 映射访问 +
   `in` 判断；全库无 `Config.*Config.get(` 误用（`MultipleConfig.get` 为 async，
   ConfigBase.py:1648）。停止任务的 `coroutine has no attribute is_locked` 根因已消除。
2. `frontend/src/App.vue`：`isStandalonePage`（route.name === 'Logs'）跳过
   /initialization 跳转与欢迎音频；独立页面模板分支不挂 AppLayout、UpdateModal、
   GlobalPowerCountdown、WebSocketMessageListener（App.vue:247,277,309,322）。
3. 调度中心 `scheduler/index.vue`：tab 标签仅显示标题（80-83），无状态 tag；仅
   `失败` 状态显示 MacStatePanel（86-90）；无「正在停止任务」大警告块；
   schedulerMacUi.test.ts:49 锁定该行为。内部状态机（空闲/运行/停止中/结束/失败）
   保留用于 closable/disabled 逻辑，不对外展示。
4. 游戏实例网格 `game-center/GameInstancesTab.vue`：grid 3 列，≤1500px 2 列，
   ≤900px 1 列（:694-890）。

### 2. WS v2 前端现状复核（任务 #8 预研，observed）

- `services/websocket/connection.ts`：唯一主连接 + 单飞行 connectPromise + 代次
  connectGeneration；4001 "connection replaced" 与 1009 皆不自动重连；退避 3s×1.5ⁿ
  封顶 30s、一轮 5 次后交生命周期协调器。
- 渲染层仅 connection.ts 与 WSdev.vue（开发页）调用 `new WebSocket`。
- `composables/useWebSocket.ts` 为新层包装，无旧实现残留。

### 3. UI 收口修改：脚本管理（GOAL 项3，任务 #4）

**修改文件：**

- `frontend/src/views/Scripts.vue`
  - 移除「全部/配置中/空闲/不可用」状态筛选（模板 tablist、
    ScriptStatusFilter/SCRIPT_FILTER_OPTIONS/statusFilterCounts/
    statusFilteredScripts/hasNoStatusFilterMatches/statusFilterEmptyTitle/
    resetStatusFilter 及全部筛选样式与媒体查询）。
  - 移除工具栏常驻提示「拖拽左侧把手调整脚本顺序」。
  - 搜索按钮从 Toolbar `#trailing` 移至 `#leading`（左侧小按钮），Ctrl+F 逻辑保留。
  - `filteredScripts` 简化为：搜索时用搜索结果，否则全部脚本。
- `frontend/src/views/scripts/ScriptsMacLayout.contract.test.ts`
  - 原「筛选存在」断言与 GOAL 冲突（GOAL 为最终裁决），改为锁定新行为：
    `#leading` 搜索入口存在、`script-segmented-filter`/筛选标签/常驻提示不存在。

### 4. 其余 GOAL UI 项巡查结论（源码层 observed，运行层 unverified）

- 项1 标题栏/侧栏：TitleBar 左侧 mac 风格控制钮 + 「AUTO-MAS · 版本号」；搜索/
  主题切换/折叠均在 AppSider，有展开收起动画与选中背景；无重复顶部菜单栏。
- 项2 首页：command 卡 order:1 置顶、greeting 动态问候、卫星卡 min-height 430px。
- 项5 游戏与模拟器：3/2/1 网格 + gameCenterFidelity.contract.test 锁定「下拉选择、
  隐藏 preset 锁定字段与 MaaFW 托管入口」。
- 项6 队列：新建队列已有普通/循环选择（queue/index.vue:225-229 +
  queueCreateFlow.contract.test）。
- 项7 MaaFW：编辑页不再引用 ScriptEditLogInspector（script-edit-fidelity.contract
  .test 锁定）；托管入口在 scriptCreateFlow.ts 与 useGameCenterApi.ts 均已隐藏；
  App.vue 全局 `.ant-switch{width:max-content;flex:0 0 auto}` 防开关拉伸。

### 5. WS v2 后端与插件桥关闭边界（任务 #8，observed）

- `app/core/task_manager.py`：启动队列连接判断改用 WS core
  `MainConnection.is_connected`，业务代码不再读取 `Config.websocket` 旧门面。
- `app/utils/websocket.py`：辅助 WS 管理器新增终态与幂等 shutdown，统一关闭
  Koishi、WSdev、旧 `/api/ws/plugin` 反向会话及插件正向连接，停止后台重连任务；
  关闭后拒绝创建/连接新辅助会话。
- `app/plugins/server.py` + `app/api/plugin_gateway.py`：登记声明式插件 WS 活跃会话；
  插件卸载时主动以 1001 关闭该插件现有会话，后端关闭时回收残余会话。
- `app/api/websocket.py` + `app/api/plugin_gateway.py`：主 WS 进入 quiesce/closing
  后，辅助与插件入口在 accept 前统一以 1012 `service closing` 拒绝。
- `main.py`：自然 lifespan 退出也先 quiesce 入站，再按插件系统 → 插件 WS →
  辅助 WS 顺序 teardown；主连接仍保留到业务清理与 shutdown-ready 完成。
- 新增回归覆盖：关闭期入口拒绝、辅助会话全量关闭、插件卸载会话回收、启动队列
  不再依赖 `Config.websocket`。

### 6. Config v2 native authoritative 收口（任务 #9，observed）

- `app/configuration/__init__.py`：进程默认模式及无效环境变量回退值均从
  `shadow` 切为 `authoritative`；四种显式模式仍保留用于受控回滚和诊断。
- `app/core/__init__.py` 的现有 lazy route 现在默认选择
  `NativeConfigFacade`，正式运行链不再构造 legacy `AppConfig` 配置图。
- `app/core/native_config.py`：在原有八根 CRUD/API facade 基础上补齐正式运行调用面：
  代理、Git/随包版本、关卡缓存/刷新、脚本/任务/计划/模拟器下拉、公告与配置分享、
  历史查询/合并/清理、MAA/MaaEnd/SRC/通用日志、通用脚本导入导出/分享、
  MaaEnd 配置导入和 MAA 基建排班。
- 新增运行面只使用 native `ConfigEntry` / `ConfigCollection` 与 generation store；
  authoritative 下的旧 `_authoritative_load()` 投影和 legacy JSON-first 保存仍明确拒绝，
  不允许形成混合权威。
- `main.py`：启动失败回滚及正常 teardown 都会关闭 native roots，释放
  process-global prepare hook；ConfigService 先排空 outbox，再关闭配置根。
- 配置测试契约从“authoritative 尚不可用”更新为“authoritative 为默认生产路径”，
  同时继续锁定 legacy 投影/写入拒绝、原始 r6 快照先于 Config 导入。
- 修复全量测试的两处本地工作树可移植性：reference fixture 不再依赖固定目录深度；
  本地插件 schema 测试显式使用工作树源码/entry point。更新服务单测显式注入下载源，
  不再依赖未启动的全局 Config。

## 验证命令与结果

| 命令 | 结果 |
| --- | --- |
| `yarn install --immutable`（frontend） | ✓ 完成，peer 警告（observed） |
| `yarn typecheck`（vue-tsc） | ✓ 通过（observed） |
| `yarn lint`（ESLint） | ✓ 通过，158 warnings，0 errors（observed） |
| `yarn format --check`（Prettier） | ✓ 通过（observed） |
| `yarn test`（vitest run） | ✓ 1842 tests passed；6 .mjs 套件 SyntaxError（非源码语法问题，vitest 环境配置issue） |
| `pytest -q tests/ws` | ✓ 71 passed（observed） |
| `pytest -q tests/api` | ✓ 42 passed（observed） |
| `pytest -q tests/configuration`（默认 authoritative） | ✓ 539 passed，2 skipped，81 subtests passed（observed） |
| `pytest -q`（后端全量） | ✓ 906 passed，2 skipped，95 subtests passed；4 个既有 deprecation warnings（observed） |
| `uvx ruff check/format --check`（本批 Python 文件） | 未通过：命中仓库既有 legacy 风格/格式债；未全局自动修复以避免扩大脏工作树（observed） |

## 当前已知问题

- `.venv` 仅为定向测试最小环境；仓库无 `uv.lock`，`uv sync --frozen` 无法使用，
  未生成新锁文件。
- Ruff 对所选文件报告大量既有 legacy 风格/格式债；本轮不做整文件自动格式化。
- WS 自动化已覆盖连接替换、关闭排空、辅助/插件会话回收；当前电脑不具备真实测试
  条件，Electron 后端重启、窗口关闭和任务停止改由另一台 Windows 真实机执行
  （用户确认，unverified）。
- `docs/experimental-alpha` 与历史集成/审计报告仍记录当时的 shadow 基线；这些是历史
  证据，发布前需另做当前 authoritative 用户文档和迁移说明，不能直接改写历史结论。
- Config v2 默认行为属于用户可见变更；下一次唯一发布前需确认 `res/version.json`
  与发布说明同步（当前按约束不打包、不创建 Alpha）。
- HEAD detached；按约束不 commit/branch，仅继续工作树内修改。

## 未完成事项（按优先级）

1. ✓ 前端 UI 收口完成（GOAL 项1-7 全部验证通过）
2. ✓ WS v2 后端/辅助通道/插件桥自动化回归（`tests/ws`: 71 passed）
3. ✓ Config v2 native authoritative 默认运行与配置全门禁（任务 #9）
4. WS v2 / Config v2 最终 GUI 回归：已转交另一台 Windows 真实机；待回传旧 profile
   首迁、配置保存/重启、任务停止、后端重启、窗口关闭、连接替换的日志、截图和结论
5. 安全、格式债、当前用户文档与发布收尾（最后；仍禁止打包）

## 交接清单

### 前端修改已验证

**已完成 UI 收口（GOAL 项 1-7）：**

1. ✓ 标题栏/侧栏：标题 AUTO-MAS + 版本号；搜索/主题/折叠在左侧栏（AppSider）
2. ✓ 首页：command 卡 order:1 置顶；greeting 动态问候；卫星卡 430px 缩放
3. ✓ 脚本管理：搜索按钮移左侧 leading；筛选（全部/配置中/空闲/不可用）全部移除；
   ScriptsMacLayout.contract.test 已更新锁定新行为
4. ✓ 各页响应式与开关：全局 CSS `.ant-switch { width: max-content; flex: 0 0 auto }` 
   已添加（App.vue:361-363）；各页继承 Ant Design Vue 响应式设计
5. ✓ 游戏与模拟器：3/2/1 列网格（GameInstancesTab.vue:694-890）
6. ✓ 调度中心：tab 标签仅显示标题（index.vue:80-82）；仅失败状态显示 StatePanel
   （86-90）；无会话状态 tag
7. ✓ MaaFW：编辑页不含 LogInspector；托管入口已隐藏；编辑/向导页不常驻项目日志

**前端门禁状态：**
- vue-tsc typecheck: ✓ PASS
- ESLint lint: ✓ PASS (158 warnings, 0 errors)
- Prettier format: ✓ PASS
- vitest run: ✓ 1842 tests passed；6 .mjs 套件 SyntaxError（非源码问题，vitest 环境配置 issue）

### 后续工作

**后端验证：**
- task_manager.py：MultipleConfig 租约访问已修复（源码 observed）
- WS v2：主连接、协议、关闭排空、辅助通道和插件桥 `tests/ws` 71 passed
- Config v2：默认 native authoritative；八生产根、迁移、敏感字段、原子事务、崩溃
  恢复、可逆回滚与 API facade 全部通过配置门禁
- 后端全量：906 passed，2 skipped，95 subtests passed
- App.vue：日志窗口独立初始化已实施（源码 observed）
- 调度中心：状态 tag 已移除、信息层级已调整（源码 observed）
- 游戏网格：3/2/1 响应式已实施（源码 observed）

**未验证运行：**
- WS v2 真实 Electron 任务停止、后端重启、窗口关闭、连接替换
- Config v2 真实旧 profile 的 GUI 首迁、保存和重启
- Ruff/格式债尚未全库清理

**真实机回传要求：**
- 使用基线 `aceb651adeafed86e0f116ee2ce5eacb1224fd7f` 还原当前工作树，不在用户的正式
  profile 上直接试验；先复制 profile 并记录原始 SHA-256/文件清单。
- 回传环境信息、逐项 observed/inferred/unverified 结果、前后配置树清单和哈希、
  后端/Electron 日志、关键截图，以及真实机测试前后的 `git status --short`。
- 任何失败先保留现场，不自动修源码、不清理迁移备份、不 commit/push/reset/stash。

### 当前工作树状态

- HEAD: aceb651a（checkpoint 提交）
- 脏文件：384 条（交接恢复状态 + 本轮新增修改）
- 约束：不得 commit/push/reset/stash；禁止打 Alpha 包
- 所有修改仅在工作树，未提交

## 2026-07-26 换盘前收口补充

### Alpha.9 启动阻断修复（observed）

- `app/plugins/config_store.py`：修复 Config v2 authoritative 原生根仍被当成 legacy
  `ConfigBase` 调用 `.load()` 的启动崩溃；原生路径现在通过
  `ConfigManager.transaction()` 写入 `PluginInstance` 根和集合。
- `app/plugins/manager.py`：authoritative 模式不再进入仅适用于 legacy
  `Config.ScriptConfig` 的集合迁移，避免继续访问 `sub_config_type`、`data` 和
  `_save_methods`。
- 新增两组回归，锁定原生插件配置写入及 authoritative 启动不得进入 legacy 集合迁移。
- 定向后端回归：27 passed，2 个既有 Pydantic deprecation warnings。
- 使用独立短 profile、Alpha.9 官方插件布局/wheel/lock 和当前源码启动验证：
  全部插件实例激活，出现 `Application startup complete`，并真实监听
  `127.0.0.1:36163`；验证后进程已停止。

### 初始化界面恢复（observed）

- `frontend/src/views/Initialization/index.vue` 保留并展示七个真实阶段：
  Python、Pip、Git、源码、依赖、插件、后端。
- 宽屏使用左侧阶段轨道，窄屏使用可横向滚动阶段轨道；执行进度和用户回看阶段分离，
  已完成/跳过/失败阶段可只读回看且不会重复执行。
- 修复后端阶段状态向父级同步、重试/跳过状态复位、总体进度和 macOS 玻璃样式。
- 初始化 UI 契约与现有 macOS 契约共 63 tests passed；`vue-tsc --noEmit` 通过；
  本批 ESLint 通过。
- Vite renderer 构建及 wheelhouse 校验通过。随后 electron-builder 因当前 Windows
  账户无法创建 `winCodeSign` Darwin 符号链接而失败；这是本机打包权限问题，不是
  renderer 编译失败。失败过程生成的 `frontend/dist/win-unpacked` 是可再生产物。

### 换盘基线与未验证边界

- 当前 HEAD 仍为 detached `aceb651adeafed86e0f116ee2ce5eacb1224fd7f`。
- 当前 `git status --short` 共 512 项：237 项已跟踪变更、275 项未跟踪项，
  其中 20 项为删除；全部必须随工作树迁移。
- `D:\AM6R\.git` 是 linked-worktree 指针，目标位于
  `D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\AUTO-MAS\.git\worktrees\AM6R`。
  迁移时必须同时保留 `D:\AM6R` 和该共享 Git 对象库；只复制源码目录会丢失 Git
  基线。
- 当前没有 36163 端口残留监听。
- 本轮只证明了 authoritative 后端启动与实际监听；Electron 内的 WS v2 握手、重连、
  任务停止以及旧 profile 全链首迁仍需换盘后执行真实 GUI 回归，不能据此宣称
  Config v2 / WebSocket v2 已 100% 迁移完毕。

## 2026-07-26 第二阶段收口：UAC 启动路径与当前门禁

### 已验证（observed）

- `main.py` 的 Windows UAC 重启现在把当前工作目录作为 `ShellExecuteW` 的
  `lpDirectory` 传入；提升后的子进程不再依赖调用方的默认目录。这个目录会决定
  Config v2 profile、迁移备份和日志落点。
- `tests/ws/test_server_config.py` 新增 UAC 工作目录回归；定向测试为 **2 passed**。
- 当前工作树本轮配置与 WS 收口后的自动门禁：
  - 后端全量：**908 passed, 2 skipped, 5 warnings, 95 subtests passed**；
  - `tests/configuration`：**541 passed, 2 skipped, 5 warnings, 81 subtests passed**；
  - `tests/ws`：**71 passed**；
  - 前端：typecheck 通过；lint **0 error / 158 warnings**；Vitest
    **140 files / 1910 tests passed**；Vite、renderer chunk graph、main build 与
    wheelhouse 校验通过。
- `D:\AM6E\run-20260726-085056\alpha9-p0-config-native-startup.stdout.log` 与
  `stderr.log` 均为空；因此 Alpha.9 当时的“启动失败”没有可归因的 Python 异常栈。
  该证据与启动器触发 UAC、父进程立即退出的现象一致，但不单独证明提升后的子进程
  已成功运行。

### 环境边界（unverified）

- 当前终端仍未获得 Windows 提升令牌；因此尚未直接实测当前源码经 UAC 提升后的
  子进程、Electron GUI 首迁、真实 WebSocket 重连/窗口关闭与真实旧 profile 迁移。
- `yarn build` 的 Electron 打包阶段仍受当前账户不能创建 winCodeSign Darwin
  符号链接限制；Vite/TypeScript/renderer/wheelhouse 阶段均已通过。未在本轮重打
  Alpha，也没有覆盖已有 Alpha.9 产物。

### 下一步

1. 在管理员 PowerShell 或启用 Windows Developer Mode 的环境中，对独立临时
   profile 实测 UAC 后端启动与 36163 监听；不触碰用户正式 profile。
2. 继续以 Config v2 authoritative 与主 WebSocket v2 的真实 GUI 行为为准做
   P0/P1 收口；旧 ConfigBase 仅保留显式 rollback/shadow/canary 兼容路径。
### UAC 启动补充（observed）

- UAC 脚本参数改由 `subprocess.list2cmdline()` 生成，绿色包位于包含空格的
  目录时也会以一个完整参数传给提升后的 Python。
- `ShellExecuteW` 返回值不再被无条件当作成功：返回 `<= 32` 时会抛出带返回码的
  启动异常，启动器可显示失败而不会停在“正在加载”。
- 对应 `tests/ws/test_server_config.py` 当前 **3 passed**，覆盖提升成功、保留 cwd、
  带空格路径以及 UAC 失败返回码。

### WebSocket 回归复跑（observed）

- UAC 启动器改动后，完整 `tests/ws` 复跑为 **73 passed, 3 warnings**。
  warnings 为已有 Pydantic/Starlette 弃用提醒，未出现 WS 协议、鉴权、关闭或重连失败。
- 本机未安装 Ruff，因此仅对本轮 Python 改动执行了 pytest 与 `git diff --check`；
  Ruff 全库债务不在本次最小启动器修复范围内。

### Config v2 authoritative 定向复核（observed）

- `tests/configuration/authoritative_api_cert`、`tests/configuration/test_authoritative_gate.py` 与
  `tests/configuration/test_authoritative_runtime.py` 在短 `TEMP/TMP=D:\T6C2` 下复跑：
  **79 passed, 4 warnings in 3.42s**。
- warnings 为既有 Pydantic 配置类弃用和 pytest fixture 弃用提醒；本轮没有新增
  authoritative 配置读取、保存、回滚或 API 兼容失败。
- UAC 启动修复与 `tests/ws` **73 passed** 共同构成当前源码门禁；真实提升子进程和
  Electron GUI 仍保持 `unverified`，不得将该自动化结果写成真实机通过。

### PluginConfig authoritative 分流收紧（observed）

- `app/plugins/config_store.py` 不再以 `Config.PluginConfig.load` 是否存在推断运行模式；
  只有非 authoritative 兼容模式才允许调用 legacy `load()`。
- authoritative 模式固定走 Config v2 transaction/native root；即使未来兼容门面提供同名
  方法，也不能重新把正式持久化带回 `ConfigBase`。
- 原生根测试故意提供带 `load()` 的代理门面，并断言该方法未被等待；
  `tests/configuration/test_plugin_config_native_root.py`: **16 passed, 2 warnings**。

### Config v2 全量回归（observed）

- 本轮显式 authoritative 分流修复后，`tests/configuration` 使用短
  `TEMP/TMP=D:\T6C2` 全量复跑：**541 passed, 2 skipped, 5 warnings, 81 subtests passed
  in 71.89s**。
- 两个 skip 位于 optional plugin API 覆盖清单，不是本轮 Config v2 读写、迁移或
  rollback 失败；warnings 均为现有依赖弃用提醒。

## 2026-07-26 第三阶段：Alpha.9 启动失败根因修复（observed）

### 根因：Python 3.12 mkdtemp 的 Windows owner-only DACL + UAC 令牌漂移

- 现场：`D:\T6RUN-20260726-114037\startup3.stderr.log`，
  `ensure_legacy_original_snapshot → _validate_generation → _lexical_stat →
  lstat(manifest.json)` 抛 `PermissionError WinError 5`。
- 机制（本机实证 + CPython 自带测试佐证）：Py3.12 `tempfile.mkdtemp` 在
  Windows 以 `os.mkdir(mode=0o700)` 创建目录，DACL 为
  `D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;OW)`（protected，无用户
  ACE）。UAC 提升进程首启创建快照（属主 Administrators），`os.replace`
  发布后 DACL 保留；非提升进程（filtered token 中 Administrators 为
  deny-only）对 generation 目录内文件连 lstat 都被拒 → 二次启动崩溃。
  仓库内无任何主动 ACL/只读写保护代码，快照“不可变性”全靠协议约束。
- 同类雷共 3 处，全部发布持久产物：`legacy_original_snapshot.py:161`（快照
  generation）、`authoritative.py:371`（r6 回滚 bundle）、`archive.py:296`
  （ZIP 解压发布，影响更新链路）。`mkstemp` 文件不受影响（继承父 ACL，
  已实证）。

### 修复（observed）

- `app/utils/atomic_file.py`：新增 `create_staging_directory`（默认安全
  描述符 `os.mkdir` + `secrets.token_hex`，继承父 ACL）。
- `app/configuration/compat/legacy_original_snapshot.py`：暂存目录改用内联
  `_create_staging_directory`；`_lexical_stat` 把 `PermissionError` 转为新增
  `LegacyOriginalSnapshotPermissionError`（可诊断信息）；对既有坏 DACL 的
  generation 提供一次性 `icacls /reset /t /c /q` 自愈重试
  （`_validate_generation_with_acl_recovery`），失败仍 fail-closed。
- `app/configuration/authoritative.py`、`app/utils/archive.py`：改用
  `create_staging_directory`，移除 mkdtemp。
- `app/plugins/manager.py` `_assert_locked_projects_unchanged`：报错分流——
  入口点缺失（wheel 引导未完成）与 editable/版本漂移给出不同信息，漂移
  详情列明来源/版本/editable。
- 回归：`test_legacy_original_snapshot.py` 新增 3 测（mkdtemp 禁用契约、
  ACL 自愈成功路径、自愈不可用 fail-closed），**14 passed, 2 skipped**；
  `test_authoritative_runtime.py` **6 passed**；`test_update_service.py`
  **44 passed, 14 subtests**；`test_manager_bundled_runtime_policy.py` +
  `test_bootstrap_discovery.py` **18 passed**。

### 启动实测进展

- 修复后探针（D:\T6R2，非提升）已越过配置快照阶段，新阻断为插件锁契约：
  profile 继承的 pypi 环境中 4 个随包插件是 editable 安装
  （`__editable__.*.pth`），按契约拒启——这是**设计内拒绝**，真实链路由
  Electron 初始化向导从 wheelhouse 装 wheel。离线引导 + 启动实测已交并行
  agent 重建 pypi 环境后复跑。

### ArknightWin32 后台初始化修复与就绪实测（observed）

- 症状：authoritative 模式下 `main.py:317` 报
  `ImportError: cannot import name 'ArknightWin32Toolkit'`，`后端完全就绪`
  永不出现（MainTimer、插件后台安装、Koishi 均未启动）。
- 根因：`app/MaaFW/ArknightWin32.py:65` 调用
  `Config.ToolsConfig.bind("ArknightsPC", "Enabled", ...)`；`bind` 只存在于
  legacy `ConfigBase.py:1353`，原生 `ToolsConfig` 根没有该方法。模块级
  `__getattr__` 把构造器抛出的 AttributeError 掩蔽成 "cannot import name"。
- 修复：按 `CONFIG_V2_MODE` 显式分流——authoritative 用原生根的
  `connect_observer(group="ArknightsPC", field="Enabled")` after-commit
  观察者承接同一回调语义（新增 `_on_enabled_observer` 适配签名）；
  兼容模式仍走 legacy `bind`。同时在 `__getattr__` 里先
  `logger.exception` 再抛，避免真因被 import 机制吞掉。
- 实测（D:\T6R2 独立 profile，非提升令牌，32 wheels 按 install_contract
  离线安装）：**后端完全就绪，总耗时 2.35s**；`核心初始化完成 0.25s`；
  进程启动→端口监听 ≈3.6s；20 个插件实例激活；
  `/api/core/health` 返回 `{"ready":true,"backgroundStatus":"ready"}`；
  `已禁用明日方舟PC工具` 证明观察者链路真实生效。验证后进程已停止，
  36163 已释放。

### 前端 UI 收口全量修复（observed）

- 11 处 `@container` 自引用死规则全部改挂真实祖先容器（重度三处：
  ScriptSplitView 单列降级、settings-body 竖排、plugin-page 溢出滚动）。
- 队列/首页视口栅格 `a-col :xs/:sm/:xl` 改为容器查询 grid；队列两个子组件
  的 `a-card` 外壳弱化，消除白框套白框——过程中发现两处位于 `</style>`
  之后的**死文本 CSS**，此前的弱化尝试从未生效。
- 队列表格行最小宽 976→约 756 并补横向滚动；脚本卡片/用户行/搜索栏、
  mac/PageHeader、插件新增弹窗的 `@media` 全部改为容器查询；历史页三栏
  补窄屏折叠。
- 16 个设置页开关补 `aria-label`；删除死代码 `AppToolbar.vue`（重复顶部
  菜单+搜索+主题）、`ScriptEditLogInspector.vue` 及两处日志框死 CSS；
  调度侧栏双重隐藏规则合并为单一容器查询。
- 门禁：`yarn typecheck` 通过；`yarn lint` **0 error / 158 warning**
  （顺带修掉 11 个既有 error）；`yarn test` **140 文件 / 1914 测试全过**。

### 冷启动优化（本轮，observed）

**4.2 MB Monaco 退出首屏（构建实测验证）**

- 第一层原因：`frontend/src/utils/monaco.ts` 静态 import `loader` 与
  `editor.worker?worker`；`SchedulerLogPanel.vue` / `HistoryLogModal.vue`
  静态 import `VueMonacoEditor`。已分别改为动态 import 与
  `defineAsyncComponent`。`main.ts` 的 `requestIdleCallback` 只延后了调用、
  从未延后加载。
- **但只改这一层无效**：改完重新构建，`index.html` 里 vendor-monaco 的
  modulepreload 依旧存在。逐 chunk 反查发现入口只从该 chunk 导入一个符号
  `_`——那是 Vite 的 `__vitePreload` 辅助函数。该 helper 被每个含动态
  import 的 chunk 共享，且其虚拟模块 id 不含 `/node_modules/`，`manualChunks`
  直接放行，Rollup 把它归进了 vendor-monaco。于是入口为了拿一个函数而静态
  依赖整个 4.2 MB 编辑器，index.html 随之写出它的 modulepreload 与 145 KB
  阻塞式 stylesheet。
- 修复：`frontend/vite.config.ts` 的 `resolveVendorChunk` 在 node_modules
  早退判断**之前**把 `vite/preload-helper` 固定分配到 `vendor-ui`（入口本就
  必须加载的 chunk）；`vite.config.test.ts` 新增对应用例锁定该策略。
- 构建实测对比（`vite build --emptyOutDir=false`）：

  | 项 | 修复前 | 修复后 |
  | --- | --- | --- |
  | index.html modulepreload | vendor-ui、**vendor-monaco 4.24 MB**、vendor-markdown | vendor-ui、vendor-markdown |
  | index.html 阻塞 stylesheet | vendor-ui、**vendor-monaco 145 KB**、index | vendor-ui、index |
  | vendor-ui 体积 | 1,634.82 kB | 1,636.06 kB（+1.24 kB，即那个 helper） |

  首屏净减 4.24 MB JS（gzip 1.09 MB）+ 145 KB 阻塞 CSS，代价 1.24 kB。

**其他**

- `frontend/src/utils/appEntry.ts`：版本检查服务改为并行
  （`Promise.allSettled`）+ 即发即忘，不再 gate 住启动遮罩消失；
  单飞行标记改为 promise memo，顺带修掉“并发调用都会越过守卫”的既有缺陷
  （原实现在最后一个 await 之后才置位）。
- 定向回归：`vite.config.test.ts` + scheduler + history 共
  **10 文件 / 125 测试全过**。

### 专项编辑页路由断裂修复（B1，observed）

- 根因：官方插件声明的 `editor_kind`（MAA=`plugin:script_maa`、
  MaaEnd=`plugin:maaend_adapter`、OkScript=`plugin:ok_script_adapter`，均从
  wheel 内 plugin.py 核实）不在前端任何映射表中，`getScriptEditPath` 全部
  回落 `/edit/plugin` 通用 SchemaForm，三套定制编辑页（含 MAA 模拟器管理、
  MaaEnd Skyland Token 敏感字段协议、OkScript 项目元数据）用户侧不可达。
- 附带发现：`/scripts/:id/edit/maa` 路由**从未注册**（committed HEAD 亦无），
  `MAAScriptEdit.vue` 是彻底的孤儿组件；仅补映射仍会 404，已补注路由。
- 修复：`PLUGIN_EDITOR_SEGMENTS` 与 `TYPE_KEY_EDITOR_SEGMENTS` 补齐三键；
  删除无生产者的死键 `builtin:maa`/`builtin:ok-script`/`builtin:okef`
  （保留 `builtin:src`/`builtin:maaend`/`builtin:m9a`，宿主 fallback 仍会
  产出）；删除零生产调用的 `getScriptEditSegment`/`SCRIPT_EDIT_SEGMENTS`
  死代码及其测试——正是它让"有测试"掩盖了真实路由。
- 新增 `src/utils/scriptRegistry.test.ts`（11 条）：导入**真实 router 注册表**
  逐段比对 9 条路径，修复前必挂。全量 `yarn test` **141 文件 / 1924 测试通过**。
- 遗留（未改，仅记录）：`app/core/script_types.py` 的 MaaEnd fallback 写
  `builtin:maaend`，与插件声明 `plugin:maaend_adapter` 不一致；前端已双向
  接住，建议后端后续对齐。

### 版本 bump 与文档收口（observed）

- 全仓 9 个文件的版本串统一 bump 到
  `v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.10`，snapshot_id 同步
  `r10-portable-v10`；electron-builder 的
  `snapshot.version === package.json.version` 门禁不变量复核通过。
- `res/version.json` changelog 补齐 #268 循环队列、#289 游戏中心、
  Config v2 authoritative 默认化、WebSocket v2 全栈迁移、Alpha.9 启动失败
  修复共 5 条。
- `docs/integration-plugin-matrix.md`：以 runtime-lock.json 为唯一事实源逐行
  核对 23 个 distribution，实际更正 **13 处**版本（HSR 四件、script-maafw、
  runner、interface、project-update、managed、okww/ok_script/maaend adapter、
  script_maa），并在头部声明事实源。
- KNOWN_GAPS 增补 GAP-14~17（断点续传缺失、三条插件链缺宿主自动化测试、
  插件市场仅 WS 无 HTTP 回退、任务管理器游离 MultipleConfig）。
- 门禁复验：`verify_wheelhouse_snapshot.py --strict` 通过
  （127 wheels / 23 plugins / 21 entry points）；`validate-wheelhouse.mjs
  --require-snapshot-contract` 通过；
  `pytest tests/plugins/test_verify_wheelhouse_snapshot.py` **22 passed**。

### 多镜头 bug 狩猎（20 agent 工作流，六镜头并行 + 对抗验证）

针对“WS v2 与 Config v2 是否真的完全替换”做穷举扫描：六个只读镜头
（config 残留 / ws 残留 / 插件生命周期 / asyncio 危害 / 前端核心层 /
Windows 平台）并行发现 41 条，取最严重 14 条逐条派独立 agent **对抗复核
（默认证伪，除非触发路径真实可达且后果如描述）**，确认 13 条、证伪 1 条。

**证伪那条反而挖出一个 P0**：`app/core/task_manager.py:652-671` 的循环起始
提交调用 `set_many([...], expected=[...])`，但 `expected` 只存在于 legacy
`ConfigBase.set_many`；authoritative 下 `QueueItem` 是原生 `ConfigEntry`，
其 `set_many(changes)` **没有该参数**（复核者用 `inspect.signature` 运行时
验证）。后果：默认模式下循环队列第一个到期项到点即 `TypeError`，脚本尚未
开始运行，整个 CycleRun 崩溃——**#268 主打功能在默认模式完全不可用**。

已确认的 13 条 P1（全部附完整触发链证据）：

| 域 | 缺陷 | 后果 |
| --- | --- | --- |
| Config | `IfSelfStart`/`IfAllowSleep` 在 authoritative 下无观察者也无启动应用 | 开机自启开关 API 成功、配置持久化、前端回读 true，但 schtasks 任务从不创建/删除；阻止休眠沦为空设置 |
| Config | 旧 `OkwwConfig` 记录迁为 `OkwwScript`，但 native facade 无对应 descriptor 且遍历无逐条隔离 | r6 老用户升级后 `/api/scripts/get` 等全部 500，**所有**脚本不可见，且删改 API 同样报错，无自愈路径 |
| Config | `check_data` v1.7→v1.11 迁移链在 authoritative 下不可达 | ≤v1.10 用户按默认配置升级必然启动失败；且旧字节已被冻结进不可变快照，改模式跑一次 legacy 也救不回来 |
| WS/前端 | `useSchemaActionRunner` 仍等待已废弃的 `Signal`/`Accomplish` | schema 会话永不完成；crash 路径下全屏遮罩（z-index 9999）永久卡死，只能重启应用 |
| WS/前端 | `emulator.notice` 前端零订阅者 | 模拟器启停异步失败对用户完全不可见（仓库自带 T-GAP-06 已记录未修） |
| 前端 | 1009 关闭与 shutdown 共用 `'closed'` 终态 | 手动重连、重启后端、启动重试**全部**失效，且重启后端会真杀进程丢任务；唯一出路是重启应用 |
| 插件 | `ServiceFacade._names` 丢弃 list/tuple/set | 公开 SDK 契约静默 no-op：`inject(needs=[...])` 回调在服务未就绪时立即执行 |
| 插件 | repair 后台任务无锁读改写，`stop()` 也不取消它 | 与用户配置写请求交错时整体回退对方修改（`_write_root` 是 remove-all/re-add-all） |
| 异步 | `second_task`/`hour_task` 循环体无异常防护 | 单次异常永久静默停摆：定时代理与游戏签到全部不再触发，无日志无提示 |
| 异步 | CycleRun 与脚本删除竞态，`_acquire_script_leases` 抛 KeyError 而只捕 RuntimeError | 删除某个到期项引用的脚本会让整个循环任务崩溃退出，而非跳过该项 |
| Windows | `emulator/general.py:144` 把 PID 当 HWND 传给 `IsWindowVisible` | 静默模式假成功（窗口仍可见）；显示路径每 0.5s 反复发 BossKey 直到超时报错 |
| Windows | `update.py:638` 用 `Path.rename` 晋升下载包 | 残留同名 zip 时永久无法完成更新下载（每次重试都完整重下再失败） |
| Windows | `AUTO_MAS_UV_EXE` 只写不读 | 报错文案、文档、Electron 注入三处都承诺的自救通道实际不存在 |

另有 28 条 P2 未逐条验证（含 UAC 提权丢参数、ProcessManager.kill 不清进程树、
MergeableStateCache 无淘汰、卸载插件包半删除无回滚、多处 subprocess 编码与
`CREATE_NO_WINDOW` 缺失等），完整清单在工作流输出。

修复已分四组并行派出（Config 缺口 / CycleRun / 定时器与插件生命周期 /
Windows 平台）。

## 2026-07-26 第四阶段：最终集成会话（进行中）

> 本节由当前接管会话维护。若中断,从这里恢复。

### 已完成（observed）

1. **WS suspended 语义测试收口**：connection.test.ts 旧 1009→closed 断言按新语义重写,
   新增 6 条测试:1009→suspended 不自动重连、4001→suspended、普通 connect 不越过
   suspended、connect({force:true}) 恢复 open、shutdown 后 force 仍拒绝、恢复后再
   shutdown 不可复活。定向 vitest(websocket + useAppLifecycle + useSchemaActionRunner
   + useEmulatorApi):**5 files / 64 tests 全过**。
2. **交接 8 组已完成修复完整性复核**（8 agent 并行工作流,全部返回):timer、插件
   生命周期、CycleRun、Windows 平台 7 项、Electron 冷启动、Config v2 三项 P1
   (含 mkdtemp→create_staging_directory)、WS v2 前端、ArknightWin32/config_store
   ——**全部 intact,零回退**,证据 file:line 已存工作流输出。

### 已完成（第二轮吸收,observed）

3. **UAC 自提权 P0 修复**(main.py,主 Agent 亲改):审计实证无条件
   ShellExecuteW("runas") 自提权是绿色包普通用户启动 100% 失败根因——提权后
   Electron 的进程句柄/stdio/env(含 AUTO_MAS_BACKEND_OWNER_TOKEN 无兜底)/PID
   归属全部断裂,waitUntilReady 立判"后端进程已退出",孤儿进程永久占 36163
   (与 Alpha.9 空日志现象完全吻合)。修复:默认**不再自提权**(打包契约
   asInvoker + 前端 restart-as-admin 是正规提权路径,后端继承提升令牌);
   保留 AUTO_MAS_SELF_ELEVATE 显式 opt-in 逃生口,且重启参数行现在保留 -I 等
   解释器隔离 flag 与全部 argv。tests/ws/test_server_config.py 重写为 5 条
   (默认不提权、opt-in 保留 cwd/带空格路径、失败码、参数行保留)。
4. **独立 legacy 升级器完整落地**(任务批1-2 核心,主 Agent 亲写):
   - app/configuration/compat/legacy_data_upgrade.py:幂等 v1.7→v1.11,版本表
     为断点续传标记;已存在旧快照+pre-v1.11 数据时
     LegacyDataUpgradeConflictError fail-closed(防旧 Alpha 冻结的
     pre-v1.11 字节与现场脱钩);版本表歧义/未知版本/坏库全部明确拒绝。
   - app/configuration/compat/_legacy_v1_8_layout.py:v1.8→v1.9 目录布局迁移
     的独立重实现(不构造 legacy Config,直接按 MultipleConfig 序列化契约
     产出 {"instances":[{uid,type}],uid:{...}},嵌套走 SubConfigsInfo)。
     白名单字段映射 + 主动纠正(枚举/日期/路径存在性/用户名/密码置空),
     因为产物直接被 fail-closed 的 v2 导入链消费,legacy validator 的
     auto-correct 帮不上忙。gui.json/基建/ConfigFiles 复制与旧目录清理
     按 legacy 语义;先写根后删目录(比 legacy 更安全的崩溃次序)。
   - v1.9→v1.10 与 v1.10→v1.11 重定义:Config.json 白名单重建(含
     IfSkipMumuSplashAds→IfBlockAd 映射,Data/Update/密文组丢弃再生);
     用户 Task 组旧键名(IfWakeUp/IfBase/IfCombat...)结构化重命名——legacy
     的 str.replace 重命名从未写盘,真实 v1.10 档案带旧键名会被 v2 拒收,
     此实现兑现重命名意图并且保值(优于 legacy 的丢弃归默认)。
   - main.py prepare_configuration_startup 接入:升级→快照→模式断言,全部
     在任何 Config import 之前。
   - **关键验收**:test_legacy_v1_8_layout.py 的
     test_output_is_accepted_by_v2_import 把完整升级链产物直接喂真实
     legacy_production_roots_to_wire(fail-closed)无异常通过。
   - 测试:test_legacy_data_upgrade.py + test_legacy_v1_8_layout.py +
     test_server_config.py 共 **21 passed**;tests/configuration 全量
     **562 passed, 2 skipped**(升级器接入后)。
   - 已知边界(记录):v1.9/v1.10 起点档案的 Script/Plan/Queue 根是当年
     legacy 产物,除 Task 键名外的时代差异字段仍可能被 v2 fail-closed 拒收
     (无真实档案可验,拒收时错误信息明确,不会脏写)。Windows 大小写
     不敏感的 config.json→Config.json 改名按目录真实项名判断。
5. **P2 快修吸收**(全部亲核 diff + 后端定向 90 passed):
   - ProcessManager.kill 递归杀进程树(先子后父,psutil,失败降级),6 测试。
   - MergeableStateCache:task.completed 终结事件清除对应 task.info.updated
     条目 + 每 type 软上限 128 淘汰,11 测试;证伪 operationId 轴(emulator.notice
     不入缓存)。
   - 插件卸载"半删除无回滚"**证伪**:实际顺序不可逆在前、配置最后,重启
     _repair_invalid_instances_after_start 完整自愈,零改动。
   - subprocess 扫修 9 处(system.py 关机链 6 处 CREATE_NO_WINDOW、
     runtime_api.py 编码+隐窗、game_providers.py adb 隐窗)。
6. **WS v2 闭环审计**(9 维度):协议/鉴权/重连/并发/背压/关闭/插件桥闭环 OK;
   断链已派修:P1 toolkit.notice 前端零订阅、P1 冷启动快照先于任务订阅被丢弃
   (前端从不发 snapshot.request)、P2 suspended 无用户恢复入口、P2 鉴权失败
   1008→1006 无限静默重连、P2 task.log 超 4MB 静默丢弃。
7. **ConfigBase 残留审计**:authoritative 生产链干净,零 P0;
   app/task/{MAA,M9A,MaaEnd,general}/manager.py 为游离视图+authoritative 下
   死代码(调用即 AttributeError,全仓零注册方),MaaEnd/manager.py 未被
   GAP-17 记录——发布前文档定性,不删代码。
8. **MaaEnd/wheelhouse 审计**:0.0.6 六方闭环零漂移("0.0.5"是过期前提);
   #302 新登录本体未落地(后端仍 Id+Password,范围性记录);两个中级安全断点
   已派修(loguru 绕过脱敏+diagnose dump、token 片段进 UI 通知);记录:
   MaaEnd wheel dirty 构建不可复现、Python 校验器不校验单 wheel 摘要、
   frontend/scripts 下 4 个未跟踪调试残留 .mjs 会被 vitest 拾取。
9. **UI 快修吸收**(设计比对 13 处偏差→5 agent 全返回,测试+typecheck 全绿):
   调度中心窄屏底部栏新建入口(断点联动契约)、插件页大框降级无边界分栏、
   历史页窄屏降级(warn 级别证伪:后端只有 DONE/ERROR 两态)、深色 token 5 项
   对齐(0.5px 描边/标题栏 0.75/hairline/侧栏 blur 24px/主色回退)、
   插件市场留白融合 3 项。

### 已完成（第三轮吸收,observed）

10. **WS 断链修复吸收**(全部亲核 diff):toolkit.notice 前端订阅
    (WebSocketMessageListener,level 分级 antMessage)、HomeStatusCard
    suspended/断连重连按钮、冷启动快照补拉(调度订阅就绪后发
    id=Main snapshot.request,幂等)、鉴权失败可见性(后端在跑连续 3 轮
    连不上→复用恢复失败 Modal,不再无限静默)。
11. **日志脱敏链补齐**(安全 agent 落了 skland 片段移除+冒号正则;
    loguru patcher 与 diagnose 门控由主 Agent 补):logger.py 每条应用日志
    过 sanitize_log_message;diagnose 局部变量转储仅 AUTO_MAS_DEV=1 保留;
    tests/utils/test_log_sanitization.py 4 类断言。
12. **全量门禁(当前工作树)**:
    - 后端:**988 passed, 2 skipped, 100 subtests**(91s,含全部新增测试)。
    - 前端:typecheck ✓;lint 0 error/160 warnings;
      `vitest run scripts/` **228 passed**(6 个 .mjs 门禁真实执行);
      全量 vitest **146 files / 1966 tests passed**(含 electron 24 套件)。

### 批3 运行时 UI 验收（observed,浏览器 JS 布局测量 + 真实后端联调）

- 环境:Vite dev server(web 模式)+ 当前源码后端(T6R2 隔离 profile,
  非提升令牌,36163 真实监听);Electron 打包链见下。
- **后端冷启动:核心初始化 0.37s,后端完全就绪 2.11s**;dashboard 实时联通
  (动态问候、快速开始置顶、后端已连接、WebSocket 已连接、卫星图实时)——
  WS v2 全栈在真实浏览器会话端到端工作,UI 不卡加载页。
- **三档宽度(1600/1100/700)× 10 页**(home/scripts/game-center/plugins/
  market/queue/scheduler/history/tools/settings):页面级横向溢出全部为 0;
  700px 下越界元素均位于合法裁剪容器内。
- 专项:设置页 700px 单栏 ✓;调度中心 1600px 侧栏可见+底部无重复入口、
  700px 侧栏隐藏+底部"新建会话"入口出现(断点联动)✓;卫星图 700px
  452×457 无左右裁切 ✓;标题栏"AUTO-MAS+版本号"✓;侧栏三件套
  (折叠 Ctrl+B/搜索/主题切换)✓。
- 限制(记录):游戏中心网格列数与历史页三栏折叠需真实数据渲染,本 profile
  空态无法运行时确认,由契约测试(gameCenterFidelity、history 容器查询)
  锁定;深色 token 已按设计对齐并有契约测试,视觉观感留人工手测卡。
- **electron-builder 打包链在本机首次走通**:winCodeSign 缓存手动预填充
  (解压 7z 跳过 2 个 darwin dylib 符号链接,Windows 打包不使用)绕过
  SeCreateSymbolicLink 权限限制;`yarn build` 全链 exit 0,产出
  dist/win-unpacked 与 NSIS Setup。

### ✅ Alpha.10 打包完成（observed）

- **短路径包:`D:\AUTO-MAS-v6-alpha.10.zip`,451,204,995 字节(430.3 MiB),
  SHA256 `40f9a2ad131b7d24cc903ecaf6459937709cd5bf53a02803689db4182e680068`**。
- 权威产物与证据:`D:\A10OUT\`(archive + alpha-release-manifest.json +
  SHA256SUMS + evidence/EVIDENCE_INDEX.json);stage `D:\A10S`;
  身份构建 `D:\A10R`;wheelhouse 证据归档 `D:\A10E\wheelhouse-alpha10.zip`
  (sha 50c912e7...);解压冒烟现场 `D:\A10X`(Expand-Archive 原生解压,
  根含 EXE/environment/resources,无 wrapper,21 个根条目)。
- 管线:`release:integration --unpacked-only`(Alpha 身份 EXE,extraResources
  自动带 integration-snapshot/source-provenance/evidence/ico)→ stage 组装
  (win-unpacked + 冻结 r6 的 full\environment 只读复制)→ prepare-portable
  → 7za 打 zip → finalize(便携包中央目录契约校验通过,status=packaged)。
- 环境束:`D:\release-nexus-a1-r6\full\environment`(Py3.12 嵌入式 +
  uv 0.11.30 + MinGit 2.46;上游归档 sha cfa5fff8...67190a,
  environment-info.json 溯源)。**冻结 r6 实际位于 D:\release-nexus-a1-r6**
  (非 E 盘;E 盘未挂载),本轮仅只读复制其 environment,零修改。
- git-sha 绑定 aceb651a(dirty-captured,provenance 记录 worktree 状态)。

### ✅ Alpha.11 出包完成(observed)

- **`D:\AUTO-MAS-v6-alpha.11.zip`,451,209,717 字节(430.31 MiB),
  SHA256 `e8a7e89c2fcfa720c3e03c9a2b51a47d40524258a4f8615547fc20b91de71074`**;
  权威产物 D:\A11OUT(finalize status=packaged,中央目录契约过),
  stage D:\A11S,构建 D:\A11R,解压冒烟 D:\A11X。
- 门禁:后端 **1000 passed/2 skipped/100 subtests**;前端 typecheck ✓、
  lint 0 error(修 3 处 prettier)、scripts **229**、全量 vitest **2018**。
- 版本 bump 9 文件到 .11 + snapshot r11-portable-v11;version.json 补 5 条
  问题修复 changelog。
- 收录修复:真机反馈 15 项(遮罩/主页六项含网格拖拽/侧栏全局搜索/脚本搜索
  横向/添加游戏选项卡/插件名可见+市场预热+版本上报/调度加号/历史三段)、
  卫星占位 2/3 行宽+轨道容器自适应、**P0 MaaFW 脚本变砖**(校验键空间
  错用类名,改走 get_script_type_key+fail-soft)、找日志对话框定位
  appRoot\debug。

### 真机反馈第二批(P0):创建 MaaFW 脚本后应用变砖(已修,见上)

证据 D:\AUTO-MAS-v6-alpha.10\debug\app.log:automas_script_maafw 20:09:26.767
已注册 ['MaaFW'],随后 main.py:436 validate_script_type_registry 仍抛
"脚本类型注册不完整 ... config_class=MaaFWScript" → 每次启动必死。
键不匹配根因 + 校验降级 fail-soft(仅内建缺失硬失败,插件脚本缺 provider
标记不可用继续启动)已派 agent;另派:启动失败"找日志"对话框默认目录应为
appRoot\debug。maaend_adapter 双重注册线索一并排查。

### 2026-07-26 真机反馈第一批(Alpha.10 手测,15 项,6 agent 并行修复中)

1 启动检查全屏遮罩与主界面分阶段加载重复→界面就绪即放行;2 主页问候行重复快速开始标题;3 "暂无可运行任务"黄条多余;4 启动脚本/添加脚本/管理插件三按钮移右上工具行;5 最近活动空态背景空缺;6 编辑布局上下移不可用→修复+评估网格拖拽(安卓小组件式);7 侧栏删"主菜单"标题+深色模式与下三项对齐;8 全局搜索应搜页面/设置项/插件/脚本+模糊匹配跳转;9 脚本管理搜索改横向展开;10 添加游戏改选项卡样式(仿添加脚本);11 插件实例列表实例名不可见;12 插件市场启动时异步预热不阻塞;13 "本机版本:版本未上报"数据链修复+已是最新时禁用更新按钮;14 调度中心新建会话"+"移回工作区头部行最右;15 历史级别段改 全部/错误/信息(删死的"调试"段)。
所有权分区:A=遮罩+home;B=AppSider+全局搜索;C=Scripts 搜索;D=game-center;E=PluginInstanceList+Market+appEntry 预热;F=scheduler+history。
修完需:全量 vitest+typecheck+lint 复跑→若出新包用 **alpha.11**(alpha.10 zip 已存在,禁覆盖,需 bump 9 处版本串+snapshot_id 并复核 electron-builder 版本不变量)。

### 真机反馈第三批(alpha.11 手测,进行中)

已完成:初始化向导中性配色+顶部横向 stepper(78 用例);主页默认顺序
command→queue→recent(4)+satellite(8)→status→proxy + 六按钮统一(32 用例)。
在途:侧栏 agent(抖动/全局搜索二次无结果/深色模式条目样式统一/图标改
太阳月亮);瀑布流工作流(全局行等高留白→iPad 双栏瀑布,排除
Initialization/home/app-shell)。
排队(等瀑布流完成防 scheduler 目录冲突):①设置大页升级三档
(≥约1400 三栏/980-1400 双栏/以下单栏);②**调度中心整页简化**:删
"调度会话"头块+四计数条+工作区侧栏,只留老版调度台(会话 tab+选择器+
开始执行+任务总览/日志),调度台自带 加会话/删当前会话/一键全删 三操作
(契约测试 schedulerMacUi 需按新形态重写;窄屏底部栏入口机制随侧栏
一并撤除)。③**全站页面标题统一**:各大页标题格式不一(计划管理是裸大
标题,其他页各异),统一为 MacPageHeader 规范(标题+副标题+右侧动作区,
同字号同间距);覆盖 plans/scripts/game-center/plugins/market/queue/
history/tools/settings,主页保持问候行形态,调度中心随重构去头。

### 原打包流水线笔记(已执行完毕,留档)

已确认的管线与事实:
- 最终门禁已全绿:后端 988/2 skipped;前端 typecheck/lint/scripts 228/全量 1966;
  `verify_wheelhouse_snapshot.py --strict` ✓;`validate:wheelhouse:integration`
  (snapshot contract bound)✓。
- **E 盘当前未挂载**,冻结 r6 无法定位(本轮零触碰风险,报告需注明)。
- Alpha 身份:executableName/artifactStem=`AUTO-MAS-v6-Experimental-Alpha`
  (frontend/scripts/experimental-alpha-release-identity.cjs);普通 `yarn build`
  产出的是 `AUTO-MAS.exe`,**不能**直接用;必须
  `yarn release:integration --wheelhouse D:\AM6R\plugins\wheels --output D:\A10R
  --unpacked-only`(electron-builder.integration.cjs 注入身份;已后台启动)。
- winCodeSign 权限问题的解法(已生效):手动解压
  `%LOCALAPPDATA%\electron-builder\Cache\winCodeSign\009759227.7z` 到同目录
  `winCodeSign-2.6.0`(7za x -snld,跳过 2 个 darwin dylib 符号链接)。
- win-unpacked 的 resources/integration-snapshot 由 extraResources 自动生成且
  为今日源码(已验证含 _self_elevation_requested 与 upgrade_legacy_data)。
- 版本定为 **alpha.10**(v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.10;.10 从未
  发布过包,身份 9 文件已在前会话 bump,今日构建一致)。

剩余步骤(顺序,命令均在 D:\AM6R\frontend):
1. stage 组装 D:\A10S(必须全新目录):A10R 的 win-unpacked 全量内容 +
   `environment/`(python/python.exe、python/Scripts/uv.exe、git/bin/git.exe;
   完整束搜索 agent 进行中——AM6R/主工作树/all-plugins-integration 的
   environment 都只有 uv.exe,缺 python/git)+
   docs/experimental-alpha/{ALPHA_README,RELEASE_NOTES,KNOWN_GAPS,
   MANUAL_TEST_CARDS,OFFLINE_FIRST_START}.md+CI_GATES.json →
   stage/resources/integration-snapshot/evidence/ +
   `node scripts/capture-alpha-source-provenance.mjs --output
   D:\A10S\resources\integration-snapshot\source-provenance.json
   --expected-git-sha aceb651adeafed86e0f116ee2ce5eacb1224fd7f
   --repository-root D:\AM6R --wheelhouse D:\AM6R\plugins\wheels`
   (输出必须在 git 工作树之外,A10S 满足)。
2. 7za 打 wheelhouse 与 environment 归档(仅为 sha256 证据,放 D:\A10E),
   算 SHA256。
3. `node scripts/generate-experimental-alpha-installer.mjs prepare-portable
   --stage D:\A10S --output D:\A10OUT --version
   v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.10 --wheelhouse-sha256 <..>
   --environment-sha256 <..> --git-sha aceb651a...`。
4. 在 stage 根内 `7za a -tzip D:\A10OUT\AUTO-MAS-v6-Experimental-Alpha-Full-
   v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.10-x64.zip *`(必须 cd 进 stage 用
   通配,禁 tar -C;7za 产正斜杠条目无 ./ 前缀)。
5. `... finalize --prepared-manifest D:\A10OUT\
   alpha-release-manifest.prepared.json`(内含便携包中央目录契约校验)。
6. 复制到 `D:\AUTO-MAS-v6-alpha.10.zip`(确认不存在),Expand-Archive 到
   D:\A10X 冒烟验证根含 EXE/environment/resources,报告大小+SHA256。

### 进行中

- main.py 旧数据升级(v1.7→v1.11)→immutable snapshot→Config v2 启动顺序:
  规格研究 agent 进行中;结论:check_data 的 v1.7→v1.8/v1.9→v1.10 是纯 JSON 变换,
  v1.10→v1.11 实为 no-op(原代码 str.replace 未赋值 bug,升级器需 bug-for-bug 只
  bump 版本),v1.8→v1.9 需按 legacy MultipleConfig 序列化形状独立重实现。
  落点:prepare_configuration_startup 中 ensure_legacy_original_snapshot 之前。
  注意角落:已存在旧快照(冻结了 pre-v1.11 字节)且无 v2 committed generation 时
  必须 fail-closed,不得自动升级造成快照与现场不一致。
- 只读审计 4 agent:ConfigBase 生产链残留、WS v2 全栈闭环 9 维度、UAC 自提权
  7 项(argv/-I/env/stdio/PID 所有权/owner token/必要性)、MaaEnd wheelhouse+#302。
- 前端假绿修复 agent:6 个 scripts/*.test.mjs SyntaxError + MaaEndUserEdit
  sensitive-save-protocol 空转断言重写(要求注入破坏验证测试有效性)。
- UI 静态比对工作流(11 agent):11 张设计页 vs 当前 Vue 实现,产出批3缺陷清单。
- P2 快修 4 agent(先证伪再修):ProcessManager 进程树、MergeableStateCache 淘汰、
  插件卸载半删除回滚、subprocess 编码/CREATE_NO_WINDOW 全库扫修。
  文件所有权分区:主 Agent 独占 main.py、app/core/config.py、app/configuration/**。

### 迁移核验结论（两个并行只读 agent，observed）

- **Config v2 authoritative**：默认模式与无效回退均为 authoritative；lazy
  route 默认 NativeConfigFacade；正式链不构造 legacy AppConfig 图；插件
  config_store/manager 已清退（仅剩 issubclass 类型判定 import）；迁移 /
  DPAPI 加密 / 原子事务（CAS 血缘）/ 崩溃恢复（显式确认）/ r6 回滚 bundle
  全部 fail-closed 完整。唯一残留：`app/task/{MAA,M9A,general}/manager.py`
  在 authoritative 下构造游离 `MultipleConfig` 内存视图（不落盘，非双
  权威），已交并行 agent 评估收口。
- **WebSocket v2**：后端主链（鉴权 1008 / 替换 4001 / 背压 64+4MB / 关闭
  排空 quiesce→drain→1001）、辅助通道与插件桥（accept 前 1012、卸载 1001、
  关闭回收）、前端唯一主连接（单飞行、代次、退避 3s×1.5ⁿ 封顶 30s、
  4001/1009 不重连）均已迁移；业务代码 `Config.websocket` 读取清零（仅剩
  写侧兼容门面）。**发现断链**：后端连接即推 `Main/snapshot.response`，
  前端零订阅者，断线重连后除弹窗外无状态快照恢复——已交并行 agent 修复
  （前端展开重分发）。其余残留（旧 /api/ws/plugin 双路径带锁串行、迁移桶
  订阅、utils/websocket 旧栈）属兼容层，有错误隔离，不阻断发布。