# MaaFW 通用适配架构研究

> 研究对象：`upstream/dev_v2`（快照 2026-08-06）上的 MaaFW 通用项目适配。
> 源码已迁出主仓：插件形态在 `35193966^`，内置形态在 `612bd30d`。
> 用途：为「把 MaaFW 适配外置、保持 MAS 功能清晰」的方案提供事实基础。

## 0. 先分清两个 MaaFW

仓库里「MaaFW」有两个完全不同的含义，混在一起读代码会乱。

| | 内嵌当库用 | 通用项目适配 |
|---|---|---|
| 是什么 | 主程序自己写 pipeline | 托管第三方 MaaFramework 项目 |
| 代码 | `app/core/maa_manager.py` 的 `_MaaFWManager` + `res/MaaFW/pipeline/*.json` | 已迁出主仓的 `automas_maafw_*` 插件族 |
| 用例 | `app/task/MaaEnd/tools/login.py:81` 调 `MaaFWManager.get_win32_tasker()` 做登录切号 | 读项目 `interface.json`，当作被调度的脚本跑 |

本文只讲后者。

## 1. 核心：认协议，不认项目

原来每接一个脚本要写一套专用适配器（`MAA`/`SRC`/`MaaEnd` 各有自己的 config 类、schema、task 目录、Vue 编辑页）。通用适配换了方向：**只认 ProjectInterface V2 协议**。任何遵守该协议的项目，给一个目录路径就能跑，不需要新代码。

设计文档 `maafw-overall-adaptation-report-2026-06-24.md` §1 的定位：AUTO-MAS 作为 MaaFramework 的 **Client** 直接消费 interface/resource/agent/task/preset/option，而不是把 MFW-PyQt6、MFAAvalonia、MXU 这些通用 GUI 壳当子程序驱动。等于 AUTO-MAS 自己变成了那个壳。

**边界**（文档 §2.1/2.2）：这是**协议级通用，不是运行环境级通用**。能解析 ≠ 能跑通。非目标明确列出：

- 不驱动外部 GUI 壳
- 不在主进程 import 外部 Python Agent
- 不把 AUTO-MAS 的 `.venv` 当 Agent Python
- 不自动改用户 release 依赖
- 不强行收编非 PI 项目

> 注意这条非目标与「外置 + 靠外部 CLI 跑任务」的方向相反，见 §9。

## 2. 壳固定，内容可变

这是「通用」能成立的地方，也是最值得单独拿出来复用的一点。

`MaaFWConfig`（`app/models/config.py:1890`）里**没有任何项目专属字段**，只有「怎么找到它、怎么连上它」：

- `Info_Path` 项目根目录（含 interface.json）、`Info_Controller` / `Info_Resource` 名字，留空则自动选
- `Device_*` ADB 路径地址与截图输入方法、Win32 句柄与三种方法、PlayCover
- `Game_*` 桌面客户端 exe、启动参数、等待时间、结束是否关闭
- `Update_*` MirrorChyan 源、渠道、CDK
- `Run_*` 次数与时长限制，加 `DailyOnceTasks` / `WeeklyOnceTasks` / `MonthlyOnceTasks`

项目千变万化的那部分全塞进一个 JSON——`MaaFWUserConfig.Task_TaskSnapshot`：

```python
# app/models/schema.py:1346
class MaaFWTaskSnapshot(BaseModel):
    taskOrder: List[str]                    # 任务 name 顺序
    taskChecked: Dict[str, bool]            # 勾选状态
    taskOptions: Dict[str, Dict[str, ...]]  # 每任务的选项值
```

所以 **ConfigBase 的字段表是固定的，加新项目不新增任何配置类**，也免了每次改 schema、跑 `yarn openapi`。

插件形态更彻底。`PluginScriptConfig`（`app/models/plugin_script_config.py`）只有三个字段：`Meta.PluginTypeKey`、`Info.Name`、`PluginData.Config`。真实配置是最后那个 JSON 字符串，靠 `app/core/script_config_codec.py` 的 `storage_to_form` / `form_to_storage` 在存储态与表单态之间编解码，顺带处理敏感字段加解密（`_PYDANTIC_SENSITIVE_PREFIX` 前缀区分新密文与遗留明文）和 JSON 字段归一化。

### 保存策略是相反的

| 对象 | 粒度 | 实现 |
|---|---|---|
| 脚本级配置 | 字段级增量 | `handleChange` 每个字段 `@change` 就 PUT 一次单字段，带 `pendingSave` 排队（`useMaaFWScriptConfig.ts:366-403`） |
| 任务快照 | 整块提交 | `savePresetAndSnapshot` 把整个 snapshot `JSON.stringify` 后连 `SelectedPreset` 一起 PUT（`MaaFWUserEdit.vue:754-778`） |

固定字段走增量、可变 JSON 走整块，各自合理。

## 3. 分层与执行链

`MAAFW_MODULE_GUIDE.md`「维护原则」原话：不要把 ProjectInterface 解析、MaaFW 运行、前端展示和更新下载揉在同一个层里。

```
1. interface_loader / models   读 interface.json 与 import，校验引用完整性，两级缓存
2. task_config                 任务快照归一化，选项默认值计算，preset 转快照
3. pipeline_override           用户选的 option → MaaFW 认的 override JSON
4. run_plan          ★        MAS 与 MaaFW 运行时之间的边界对象（纯数据，无 SDK 对象）
5. runner                      Resource/Controller/Tasker/Agent 的创建、绑定、生命周期
6. worker                      唯一持有 MaaFW SDK 的进程边界，全文件 91 行

旁挂：project_updater · agent_env · controller_adb / controller_win32
```

`run_plan` 是最关键的设计。`build_maafw_run_plan()` 把 interface 加用户选择折叠成一次确定输入，**runner 只管执行，不猜意图**。不兼容当前 controller/resource 的任务直接进 `skippedTasks`，不是运行时才失败。另有路径越界校验（防 interface.json 声明的路径逃出项目目录）和日志脱敏。

### 执行走子进程

```python
# worker.py:57-88 节选
plan = MaaFWRunPlan.model_validate(payload["plan"])
device_config = MaaFWDeviceConfig.model_validate(payload["deviceConfig"])
runner = MaaFWRunner(plan, send_log=_emit_log)
result = runner.run(device_config)
_emit({"type": "result", "data": result.model_dump(mode="json")})
return 0 if result.success else 2
```

`finally` 里无条件 `runner.shutdown()`。宿主侧 `service.run_worker` 用 `subprocess.Popen([sys.executable, "-m", "automas_maafw_runner.worker", job_path])`，解析 stdout 的 `{"type": "log"|"result"|"error"}` 三类事件。

**为什么必须隔离进程**——两个硬性原因：

1. 同一进程里 MaaFramework 的 client 模式和 agent-server 模式**不能共存**。主进程 import 外部 `maa.agent.agent_server` 会污染 `maa.library.Library` 的模式判断，导致 Client 侧对象析构时调错 native 入口，抛 `OverflowError`。这个崩溃正是内置阶段要解决的根因。
2. agent 依赖版本由项目自己的 `requirements.txt` 决定，可能与主程序冲突。

于是有两级 venv 隔离：runner 一个（`config/maafw_runner_venvs/`），agent 子进程再一个（`config/maafw_agent_venvs/`），都不碰主程序 `.venv`。代码明确禁止进程内加载 embedded agent，宁可抛错也不退化。

### 终态判定

单任务失败不中断整个 plan——`_run_tasks` 里 `except Exception` 记入 `_failed_task_errors` 后 `continue`，除非主动停止才重新抛。汇总时有失败记录则 `success=False`，`errorMessage` 拼最多 3 条摘要。失败细节从 SDK 通知里筛 `Node.Action.Failed`、`Tasker.Task.Failed` 这类事件富化。

runner 层**本身没有超时机制**，只有宿主 `run_worker` 的 `process.wait(timeout=...)`，由调用方决定传不传。ADB 设备就绪另有专用重试：轮询 `adb get-state` 最多 30 次、间隔 1 秒，因为模拟器刚启动的短暂 offline 会被误判成任务失败。

三个生命周期方法职责不同：`cleanup()` 只停当前任务；`reset_for_retry()` 同上但不清 `_initialized`；`shutdown()` 才彻底释放 agent 进程（`terminate()` 5 秒后 `kill()`）、断开 client、join 日志线程。

### 日志采集

三路收敛到同一个 `send_log`：

1. SDK 事件 sink（`_MaaFWResourceLogSink` / `_MaaFWControllerLogSink` / `_MaaFWTaskerLogSink`），挂在 `resource/controller/tasker.add_sink`
2. Agent 子进程 stdout，daemon 线程逐行读，多编码解码 + 去 ANSI，加 `[Agent:{label}]` 前缀
3. Python 环境准备阶段的 subprocess 输出

## 4. 选项翻译

`pipeline_override` 解决「用户在界面上点的东西怎么变成 MaaFW 认的 JSON」。深度合并，优先级从低到高：

```
task baseline → global option → resource option → controller option → task option
```

| option 类型 | 翻译规则 |
|---|---|
| `select` / `switch` | 取选中 case，合并其 `pipeline_override`，递归处理该 case 挂的子 option，带 lineage 防环 |
| `checkbox` | 多选，逐个选中 case 依次合并 |
| `input` | 按 `pipelineType` 转 bool/int/float/string，再替换模板里的 `{input_name}` 占位符，区分整字段替换与字符串内嵌替换 |
| `scan_select` | 选中值写入 `attach` 字段 |

`case` 和 `input` 上还能再挂 `option`，这是 interface.json 里表达**选项联动的唯一方式**。解析层用 `_collect_task_options` 递归摊平成 `dict[str, MaaFWOption]` 供前端渲染。

## 5. 前端：editor_kind 决定渲染方式

`ScriptTypeProvider.editor_kind`（`app/core/script_types.py:142`）是「要不要写专用 Vue 组件」的总开关，三档：`"schema"` 走通用表单、`"builtin:xxx"` 走宿主内建组件、`"plugin:xxx"` 走插件自带 Web Components。

前端不直接用它挑组件，先映射成路由 segment，三张静态表按优先级查：

```typescript
// frontend/src/utils/scriptRegistry.ts:137-167
const BUILTIN_EDITOR_SEGMENTS = { 'builtin:maafw': 'maafw', ... }
const TYPE_KEY_EDITOR_SEGMENTS = { MaaFW: 'maafw', M9A: 'maafw', Okww: 'okww' }
const PLUGIN_EDITOR_SEGMENTS = { 'plugin:automas_script_hsr': 'hsr' }
```

`TYPE_KEY_EDITOR_SEGMENTS` 里 **`M9A` 和 `MaaFW` 指向同一个 segment**——这是「M9A 合流」在前端的落点，M9A 没有自己的编辑页。查不到映射兜底 `edit/schema`。

MaaFW 的 `editor_kind` 是 `plugin:automas_script_maafw`，`supported_modes` 只有 `("AutoProxy",)`——**没有 ScriptConfig 模式**，因为没有外部 GUI 壳可以拉起来让用户改配置，配置全在 AUTO-MAS 这边。

零前端代码那条路靠 `PluginField`（`app/plugins/fields.py`）：插件用 `PluginField.string/select/file/json/multiple(...)` 声明式描述字段，宿主编译成运行时 ConfigBase 类加前端 JSON schema 两份产物。真需要自定义前端时走 `frontend_extensions.py`，插件包里放 `frontend/manifest.json`，渲染成 custom-element，与宿主构建链完全隔离。插件自己的 HTTP 面走 `app/api/plugin_gateway.py` 的 catch-all `/plugin/{path:path}`，HTTP 与 WebSocket 都转发。

### 任务选项编辑器

`MaaFWTaskOptionEditor.vue` 是递归组件，四层分发：`option.type` 分控件 → `input` 再按 `pipelineType` 二次分发（`int`→整数 `a-input-number`、`float`→带小数、`bool`→`a-switch`、其余→文本）→ case 挂的子选项递归渲染自己并传 `lineage` 防循环 → 未知 type 兜底渲染警告不崩。

一个细节：`option.controller` / `option.resource` 白名单不匹配时，选项**直接从 `visibleOptions` 剔除，不是置灰**。同一任务换控制器后可配置项集合会变。选项超 5 个自动按类型分组折叠并出搜索框。

### 初始化向导

四步：选择项目 → 控制配置 → 更新设置 → 运行参数，复用编辑页同一套 Section 组件。存在强先决链，用门槛 computed 卡顺序：

```typescript
// MaaFWSetupWizard.vue:294-314
const isStepZeroReady = computed(() => isInterfaceReady.value && isAgentEnvReady.value)
const maxReachableStep = computed(() => {
  if (!isStepZeroReady.value) return 0
  if (!isStepTwoComplete.value) return 1
  return 3
})
```

第 0 步要 interface 已读取 + Agent 环境已准备两项都打勾才能过。`Info.Path` 已存在时向导自动跳过直达编辑页。

## 6. 接一个新项目要做什么

通用适配的验收点：**标准 PI V2 项目零代码接入**。建一个 MaaFW 类型脚本，填项目路径加 controller 类型，就能跑。

只有想要开箱即用的默认值、友好通知文案、旧配置迁移时，才写一个 project pack 插件，通过 `maafw.registry.v1.register_project_pack()` 注册。M9A pack 就是这样——**没有任何执行代码**，只三个方法：

```python
get_definition()      -> M9APackDefinition      # 纯声明：repo、默认队列、周期规则、图标
translate_notification(result, ...)             # 通知文案
create_migration_draft(old_script_config, ...)  # 旧配置迁移
```

### 七个插件的边界

| 插件 | 服务名 | 职责 |
|---|---|---|
| interface | `maafw.interface.v1` | 解析校验 interface.json，产出模型、预览、任务快照。无网络无进程 |
| project-update | `maafw.project_update.v1` | MirrorChyan / GitHub Release 检查与应用 |
| agent-env | `maafw.agent_env.v1` | agent 运行方式识别、命令规划、Python 环境准备 |
| controller-adb / -win32 | `maafw.controller.adb` / `.win32` | 各自设备参数构造，互相独立可选安装 |
| runner | `maafw.runner.v1` | 整合上述输出，构建运行计划、跑子进程。唯一执行任务本体 |
| script-maafw | `maafw.registry.v1` | 脚本类型注册 + controller / pack 的动态注册表 |
| pack-m9a | `maafw.pack.m9a.v1` | M9A 默认约定、通知文案、旧配置迁移 |

依赖方向单向：底层能力插件互不依赖，只依赖 interface 的公共模型；runner 通过服务名消费全部底层；script-maafw 把 runner 接入脚本类型体系；pack 只填默认值。新增 controller 或 pack 不需改 script-maafw 的代码。

「服务契约」很轻：`ServiceSpec` 只有 `provides` / `needs` / `wants` 三个字符串列表，服务就是任意 Python 对象，**进程内直接调方法，不是 HTTP 或 RPC**。版本化纯靠命名约定（`.v1`），新旧版本可并存供渐进迁移。

## 7. 三阶段演进

| 时间 | 提交 | 动机 |
|---|---|---|
| 06-26 | `612bd30d` 内置一体化 `app/task/MaaFW/` | 先跑通，并解决 `OverflowError` 崩溃根因。此时 `run_plan` 的「边界对象」设计已预先划好了后来的插件切割线 |
| 07-10 | `60af79c3` 拆成 7 个包 | 控制器互斥（ADB 与 PC 通常二选一，塞一个类型里表单臃肿）、避免专项重复造轮子、复用既有插件生态。产出 `docs/maafw-plugin-service-contracts.md` 定义版本化服务契约 |
| 07-12 → 08 | `35193966` 移出源码，改 PyPI 固定版本 | 契约稳定后独立发布、独立迭代。版本记录：「避免主仓残留源码覆盖已安装插件」 |

现在 `pyproject.toml` 的 `[tool.auto-mas.plugin-bootstrap]` 钉住八个包，包括 `automas-maafw-interface 0.1.1`、`automas-maafw-runner 0.1.1`、`automas-script-maafw 0.1.4`、`automas-script-maafw-pack-m9a 0.1.1`。

## 8. 边界与已知限制

### 容错策略

两条线分明：**结构性错误 fail fast，字段级未知内容 graceful degradation**。

- 硬性拒绝加载：task / option / preset 引用了不存在的 controller / resource / option / case；import 路径越界或循环；JSON 解析失败
- 只 warning 并忽略：不认识的顶层字段、不在白名单里的 option 类型、pretask 引用不存在的对象

`interface_version: Literal[2]` 把 schema 锁死在 V2，所以严格说是 **V2 专用，不兼容 V1**。「通用」指任意遵守 V2 规范的项目。

### 缓存

内存加磁盘两级。signature 对 interface.json 及所有 import 依赖、scan_select 扫描命中的文件取 `(mtime_ns, size)`，任一变化触发重载——内容指纹比对，没有显式失效 API。磁盘缓存按 `sha256(root_path)` 命名，30 天 TTL，`.tmp` 加 `replace` 原子写。

### 文档里明确记的坑

- 资源热更新时序：agent 启动后改 `resource/` 本次运行不生效，要下次运行
- `agent.embedded: true` 未真正嵌入，仍按外部进程处理
- 模拟器刚启动时 ADB offline 会误判任务失败，靠 30 次轮询兜
- 渠道服选错 resource 时，即使 ADB ready 也起不了目标包
- 首轮范围只做 ADB / 模拟器，PC 与 PlayCover 因「当时无法测试」暂缓

### 协议通用 ≠ 运行通用，在 UI 上是硬编码的

interface.json 声明了 Adb / Win32 / macOS / PlayCover / Gamepad / wlroots 六种 controller，解析层全都建模了，前端只放开两种：

```typescript
// useMaaFWScriptConfig.ts:31-38
const MAAFW_DIRECT_CONTROLLER_TYPES = ['Adb', 'Win32'] as const
```

其余在下拉里直接置灰。能力探测也只生成**只读文案**不给开关：选模拟器 id → `emulatorTypeById` 反查类型 → 查 `controlCapabilities.emulatorExtras[type]` → 输出一条提示。

Win32 分支甚至没有窗口选择——后端 `previewWindows` 接口在（`useMaaFWApi.ts:209-240`），前端没调用。配置阶段只收 exe 路径与启动参数，窗口匹配是运行时按 interface 规则做的。这个接口目前悬空。

### 队列模型的一个限制

`MXU_PRETASK` 伪任务必须钉在队列最前，`partitionTaskOrder` 每次写入强制前置。另外「在队列即启用」——`normalizeTaskSnapshot` 会把队列内任务的 `taskChecked` 强制设为 true 并清掉游离键，**没有「禁用但保留」的中间态**，想临时停一个任务只能移出队列。`taskChecked` 这张表实际是冗余的。

## 9. 进一步外置：生态现状与影响

> 本节为「更新交给 Updater、任务运行交给 CLI」方案调研的事实记录，含核实日期与来源。

### 已经外置到什么程度

**更新这一半已落地：自行用 Go 实现了独立 Updater**（2026-08-26 确认）。以下 Python 包的现状仅作参照，不是采用的路线：

- `AUTO-MAS-Project/automas-maafw` 仓库**私有**（GitHub API 返回 404），源码不可读；以下全部由 PyPI 元数据反推。
- `automas-maafw-project-update` 已到 0.2.3，PyPI 描述为「Standalone MaaFW project update service and AUTO-MAS plugin」，支持 `mirrorchyan` / `github_release` 两种 provider，不依赖 runner / agent 运行时。

剩下待决的是 **Task 运行那一半**。

### 上游架构又下沉了一层（2026-08-26 核实）

上游依赖链里新增了 `automas-maafw-runtime-pool`，位置在 **runner 之下**，只依赖 `maafw>=4.4.0`，**不依赖任何 automas 包**——是纯 MaaFW SDK 的池化封装。同时 runner 从 0.1.1 跳到 0.4.0 并新增了对它的依赖。

主仓钉住的版本已明显滞后（版本号取自 PyPI JSON API，2026-08-26）：

| 包 | 主仓 `pyproject.toml` | 上游最新 | 落差 |
|---|---|---|---|
| `automas-maafw-runner` | 0.1.1 | **0.4.0** | 3 个 minor |
| `automas-maafw-interface` | 0.1.1 | **0.2.0** | 1 个 minor |
| `automas-maafw-project-update` | 0.1.0 | **0.2.3** | 1 个 minor |
| `automas-script-maafw` | 0.1.4 | **0.1.13** | 9 个 patch |
| `automas-script-maafw-pack-m9a` | 0.1.1 | **0.1.6** | 5 个 patch |
| `automas-maafw-agent-env` | 0.1.0 | **0.1.4** | 4 个 patch |
| `automas-maafw-runtime-pool` | **未钉** | 0.2.0 | 缺必需依赖 |

> 更正：先前误记 `automas-script-maafw` 为 0.4.0（来自二手报告）。PyPI 上该包只发布过 0.1.2 / 0.1.4 / 0.1.13，**最新是 0.1.13**。跳到 0.4.0 的是 `runner`。

依赖图（从 PyPI `requires_dist` 反推）：`script-maafw` 是唯一聚合层，依赖 interface / runner / runtime-pool / agent-env / project-update / controller-adb / controller-win32；`runner` 依赖 interface / runtime-pool / agent-env；`interface` 与 `runtime-pool` 都是叶子（无 automas 依赖）；`pack-m9a` 只依赖 `script-maafw`。

### runtime-pool 实际做什么（已读源码，0.2.0）

> 更正：先前据包名推测它「跨次运行复用 Tasker / Resource、runner 已变常驻」——**读源码后确认此推测错误**。来源：`pip download automas-maafw-runtime-pool` 解包，`src/automas_maafw_runtime_pool/`（共 3508 行）。

它是**共享 Python 环境池**，不碰 MaaFW 运行时对象。README 首句：「Shared, selector-addressed Python environments for MaaFW runner workers.」

- **身份算法**：由「完整规范化依赖集 + 选定 Python ABI + 探测到的 patch 版本 + 平台 + 架构」共同决定。**全同身份的项目复用同一个 venv**，依赖选择器或解释器身份不同则各得一个。
- **解释器管理**：支持 CP312 / CP313，可解析「已配置 / 宿主 / 池内 uv 管理」三类解释器。`resolve_runtime()` 只查不下载，`ensure_runtime()` 才准备缺失的池内解释器。`==3.13.14` 这类精确约束按 uv 管理的该 patch 安装。
- **生命周期**：`acquire_lease` / `release_lease`、`add_reference` / `remove_reference` / `reconcile_references`、`pin`、`touch`、`gc` / `collect_garbage`——有租约与引用计数的垃圾回收，不是简单缓存。
- **池标识**：根目录下 `.auto_mas_maafw_runtime_pool.json` 持有持久 UUID，v1 标记原地升级。拒绝未知非空目录、非法标记、符号链接与 Windows reparse point 链。默认位置 `config/maafw_runtime_pool`。

模块规模：`pool.py` 1391 行、`installer.py` 1180 行、`service.py` 389 行、`cache.py` 222 行、`identity.py` 214 行。

**所以它解决的是 venv 泛滥**——取代原先「每项目一个 `maafw_agent_venvs/maafw_venv_<hash>`」的做法，改成按依赖集去重共享。runner 仍然是一次性的。

### 修正后的含义

1. 上游对「执行不该是宿主业务」给的答案是**加深栈、保持进程内**——加一层环境池，不是换成外部二进制。
2. **runner 没有变成常驻**，一次性进程的假设仍然成立。你的 Go 执行器可以是一次性 CLI，不必设计 job 协议常驻服务。
3. Go 执行器**自己不需要 venv**（静态二进制），所以 runtime-pool 对它只在「项目自带 Python agent」时才相关——那部分环境准备仍要有人做。

### 另一个边界细节：插件 SDK 是独立包

`runtime_pool/plugin.py` 的导入是 `from auto_mas_core import PluginContext`，**不是** `from app.plugins import ...`。而 `maaend_adapter/plugin.py` 用的是后者。说明较新的插件依赖 `auto-mas-core` 这个 SDK 包而非直接 import 宿主 `app.*`——宿主与插件之间还隔了一层可独立发版的 SDK。

配置声明也有两种风格：runtime-pool 用朴素 dict（`schema = {"Root": {"type": "folder", ...}}`），maaend_adapter 用 `PluginField` 嵌在 Pydantic 模型里。两者宿主都能渲染。

### 上游插件的实际形态（`automas-script-maafw` 0.1.13，已读源码）

> 来源：`pip download automas-script-maafw --no-binary :all:` 解包。仓库私有但 **sdist 公开**，所以源码可读。

模块构成（共 6994 行）：

| 模块 | 行数 | 职责 |
|---|---|---|
| `runner_task.py` | 1793 | 任务执行入口，对接 MAS task 调度 |
| `api.py` | 1623 | **插件自带的 HTTP API 面**，`register_routes()` 挂到 `ctx.server` |
| `configuration_reuse.py` | 1353 | 配置复用（相当于 ScriptConfig 会话的插件版） |
| `configuration_controller.py` | 693 | 配置复用的传输层控制器 |
| `adapter.py` | 407 | `MaaFWAdapterHooks`——生命周期钩子基类 |
| `runtime_route.py` | 308 | 运行时路由选择 |
| `schema.py` | 250 | **`PluginField` DSL 声明的全部配置字段** |
| `agent_env_state.py` | 250 | agent 环境状态 |
| `api_models.py` | 109 | API 请求响应模型 |
| `plugin.py` | 107 | 插件声明 |
| `registry.py` | 59 | controller provider 与 project pack 注册表 |

**`plugin.py` 的声明**（这是「宿主边界」的全部内容）：

```python
class Plugin(ScriptAdapterPlugin):
    provides = ["maafw.registry.v1", "maafw.configuration_reuse.v1", "maafw.api.v1"]
    needs = ["maafw.runtime_pool.v1"]
    wants = ["emulator", "maafw.interface.v1", "maafw.project_update.v1",
             "maafw.agent_env.v1", "maafw.runner.v1"]

    def build_script_adapters(self):
        return [ScriptAdapterDefinition(
            type_key="MaaFW",
            hooks_factory=MaaFWAdapterHooks,
            script_groups=SCRIPT_GROUPS,      # PluginField 声明
            user_groups=USER_GROUPS,
            module="automas_script_maafw.schema",
            related_bindings={"EmulatorConfig": "EmulatorConfig"},
            editor_kind="plugin:automas_script_maafw",
            legacy_config_class_name="MaaFWConfig",   # 迁移锚点
            ...
        )]
```

注意 `needs` 只有 `runtime_pool` 一项是硬依赖，interface / runner / project_update / agent_env 全在 `wants` 里——**缺了能降级不崩**。

`schema.py` 用的是 `PluginField.group(...)` 元组风格，和 `maaend_adapter` 的 Pydantic + `PluginField` 风格并存，宿主两种都能渲染：

```python
SCRIPT_GROUPS = (
    PluginField.group("Info", "基础信息", [
        PluginField.string("Name", "脚本名称", "新 MaaFW 脚本"),
        PluginField.folder("Path", ...),
    ]),
    PluginField.group("Emulator", ..., [PluginField.related_id(...), ...]),
    ...
)
```

`registry.py` 只有 59 行，纯 dict 注册表：`register_controller_provider` / `register_project_pack` + 对应的 unregister / list / get，definition 统一 `model_dump(mode="json")` 拍平。新增 controller 或 pack 不用改这个文件。

### 后端其实已经外置完了，前端没有

插件自带 API 路由（`api.py` 里 `register_routes()`），实际注册的路径：

| 插件路由 | 宿主 `/api/scripts/maafw/*` 是否也有 |
|---|---|
| `/maafw/agent-env/prepare` | 有——**重复** |
| `/maafw/project/update` | 有——**重复** |
| `/maafw/progress` | **无**，插件新增 |

而前端仍在调宿主那条：`useMaaFWApi.ts` 里是 `/api/scripts/maafw/agent-env/prepare`，生成的 Service 方法也全指向 `/api/scripts/maafw/...`。

**所以现状是：插件已经提供了后端能力，宿主的 5 条路由是尚未拆掉的旧路径，前端还绑在旧路径上。**这解释了为什么宿主 `app/api/scripts.py` 里还有 111 处 MaaFW 且直接 import 插件内部模块——那是过渡期的胶水，不是设计终态。

包内也确认**没有 `frontend/` 目录**（只有 `assets/maafw.png`），所以那 7136 行 Vue 确实还是宿主在扛。对比 `maaend_adapter` 自带 `frontend/dist/index.js` + `manifest.json`——**MaaEnd 的前端外置做到了，MaaFW 的没做**。

### 两半的外置难度不对称

更新与运行对 MaaFramework 的依赖程度完全不同，这决定了它们的外置成本：

| | 更新 | 任务运行 |
|---|---|---|
| 要不要 MaaFW 绑定 | 不要。只是查版本、下载、解压、替换文件 | **要**。必须驱动 Resource / Controller / Tasker / Agent |
| 反馈粒度 | 自定（进度、校验、回滚都在自己代码里） | 取决于是套壳现成 CLI 还是自己调 API |

### Go 侧的可行性：绑定有，PI 层没有

[MaaXYZ/maa-framework-go](https://github.com/MaaXYZ/maa-framework-go)（官方组织下）核实结果：

**有的**——用 **purego 而非 cgo** 做 FFI，直接调共享库，所以交叉编译和分发和纯 Go 程序一样简单。包内提供 `maa.NewTasker()`、`maa.NewResource()` / `res.PostBundle()`、`maa.NewAdbController()` 等，`tasker.PostTask("TaskName")` 可用，Controller 各型别（Adb / PlayCover 等）与 Context（自定义 action / recognition）都覆盖。

**没有的**——**不含 ProjectInterface 层**。`internal/native/toolkit.go` 暴露的 MaaToolkit 函数只是 ADB 设备枚举、macOS 权限这类工具，没有 `MaaToolkitProjectInterface*`。**interface.json 的解析、任务/选项/资源/控制器枚举、PI 任务队列执行都要调用方自己实现。**

这正好是通用适配里代码量最大、最有价值的那部分。Python 侧实现的规模：

> **行数口径**：以下全部数自 `35193966^`（2026-07-12，插件迁出主仓前的快照）。上游 `automas-maafw-interface` 现已到 **0.2.0**，实际行数已变，下表只用于估量「Go 侧要补多少 PI 层」的数量级，不代表当前值。

| 模块 | 行数（迁出前快照） | 内容 |
|---|---|---|
| `loader.py` | 1075 | interface.json 解析、import 递归合并、引用完整性校验、两级缓存 |
| `task_config.py` | 621 | 任务快照归一化、选项默认值、preset 转换 |
| `preview.py` | 356 | i18n 解析、description 展开、过滤降噪 |
| `pipeline_override.py` | 335 | 选项到 override JSON 的深度合并与类型翻译 |
| `models.py` | 308 | PI V2 数据模型 |
| 合计 | **≈2695** | 同期无 Go 对应实现 |

反过来，Go 绑定能替代的是 `runner.py`（同期 2139 行）的 Tasker / Resource / Controller 生命周期部分——但注意上游 runner 已到 0.4.0 且新增了 runtime-pool 依赖，这块的形态可能已经变了，见下文「上游架构又下沉了一层」。

### 三条路线

| 路线 | PI 层 | 反馈粒度 | 成本 |
|---|---|---|---|
| 套壳 MaaPiCli | 白拿（C++ 已实现） | 退出码 0/-1 + 纯文本 | 最低 |
| Go 自写完整 CLI | 自己移植 ≈2695 行 | 完全自定 | 最高 |
| **Go 只做执行器，PI 层留在 Python** | 复用现有 `automas-maafw-interface` | 完全自定 | 中 |

### 第三条路线为什么成立

`run_plan` 当初就是按「MAS 与 MaaFW 运行时之间的边界对象」设计的——**纯数据、可 JSON 序列化、不含任何 SDK 对象**。而 `worker.py` 消费的就是这个：

```python
# worker.py:57-88
payload = json.loads(job_path.read_text(encoding="utf-8"))
plan = MaaFWRunPlan.model_validate(payload["plan"])
device_config = MaaFWDeviceConfig.model_validate(payload["deviceConfig"])
```

所以一个 Go 二进制读同一份 job 文件、吐同一套 `{"type":"log"|"result"|"error"}` JSON 行，对宿主侧就是**原地替换**，`service.run_worker` 那层解析逻辑一行都不用改。分工变成：

- **Python 保留**：interface.json 解析、任务快照归一化、pipeline_override 构建 → 产出 `MaaFWRunPlan` JSON（已写好、已测过）
- **Go 接管**：读 plan → 建 Tasker/Resource/Controller → 跑任务 → 吐结构化事件（替代 `runner.py` + `worker.py`）

附带好处：runner 那一级 venv 隔离（`config/maafw_runner_venvs/`）可以整个去掉，Go 是静态二进制。

### 遗留约束：agent 环境

项目自带 Python agent 时仍要准备它的运行环境——建 venv、装 `requirements.txt`、pip 健康检查（现有 `agent_env` 插件约 500 行，含规避 `backports.zstd` 冲突那类实测经验）。这块与 runner 用什么语言写无关。

值得考虑的归属调整：**agent 环境准备本质上是「准备项目」而不是「运行项目」**，和下载解压资源同属一类。既然 Updater 已经是 Go 的，把这块也归给它比留在运行链里更自然——运行时只负责挑已经就绪的解释器。

### MaaPiCli：存在且在维护，但反馈粒度粗

- v5.12.3（2026-08-01）的 Windows 包内仍有 `bin/MaaPiCli.exe`；v5.12.1 还有针对它的 bug 修复，不是弃用代码。源码在 `source/MaaPiCli/`。
- 两种用法：`./MaaPiCli` 交互式菜单；`./MaaPiCli -d` 读已保存的 `config/maa_pi_config.json` 直接执行。
- **退出码只有 `0` 和 `-1`**。`interactor.load()` 失败、配置无效、权限提升失败、Runner 执行失败全部映射成 `-1`。
- 终端输出是人类可读文本（如 `### Failed to run tasks ###`），**不向调用者输出结构化 JSON**。内部给 Agent 子进程准备的 `PI_CONTROLLER` / `PI_RESOURCE` 等 JSON 环境变量是给子进程用的，不是事件流。

### maafw-cli 不是 PI 执行器

[otowa-kotori/maafw-cli](https://github.com/otowa-kotori/maafw-cli)（PyPI 最新 0.1.6）是**低层设备操作 CLI**：`device` / `connect` / `ocr` / `reco` / `screenshot` / `click` / `swipe` / `type` / `key` / `action`，加 `pipeline load|list|show|validate|run` 操作**原始 pipeline JSON**。README 全文没有 `interface.json` 或 `ProjectInterface`。自述「实验性项目，早期开发阶段，接口可能随时变化」。

有全局 `--json` 可让 `ocr` / `reco` 输出结构化结果，但 `pipeline run` / `daemon` 的事件流格式与退出码语义未文档化。

**结论：它不能替代 PI 任务队列执行。**

### 没有官方 Updater

MaaFramework 官方没有为框架本体提供自更新组件，把更新责任推给各个通用 GUI 壳，且只针对「项目资源」。`interface.json` 里的 `mirrorchyan_rid` / `github` 字段是官方预留的**约定**，不是实现。

MirrorChyan 是第三方分发平台，**纯 HTTP API**：`GET https://mirrorchyan.com/api/resources/{res_id}/latest?current_version=&cdk=&user_agent=`，返回 `version_name` / `url`（限时链接）/ `release_note`，错误用非零 `code`。它只管元数据与下载源，本地落地逻辑要自己写。

### 通用壳的 autostart 能力

| 壳 | 无人值守参数 |
|---|---|
| MFAAvalonia | `--instance`/`-i`/`-c`、`--autostart`、`--quit-after-run`/`-q`、`--forceStart`/`-f` |
| MXU | `--autostart`、`-i`/`--instance <name>`、`-q`/`--quit-after-run` |
| MFW-PyQt6 | `--config-id <ID>`、`--direct-run`、`--force-restart`、`--reuse-existing` |

共同点：**都没有 `-t`/`--task` 指定单任务**，任务集合要预先在 GUI 或配置文件里勾好，CLI 只触发「跑已配置好的那一组」。MFW-PyQt6 没有跑完退出参数，且 `--direct-run` 后 GUI 窗口仍会打开。三者 README 都没有 JSON 输出或退出码约定。

### 换成外部 CLI 会丢什么

现状能拿到的反馈，与外部 CLI 能给的对比：

| 能力 | 现状（Client + worker 子进程） | 外部 CLI |
|---|---|---|
| 事件流 | `{"type":"log"\|"result"\|"error"}` 逐行 JSON | 纯文本日志 |
| 失败定位 | SDK 事件筛 `Node.Action.Failed` / `Tasker.Task.Failed`，知道**哪个任务哪个节点**失败 | 退出码 0/-1 |
| 区分崩溃与任务失败 | 能（result 事件 vs 进程异常退出） | 不能 |
| 运行前兼容预判 | `skippedTasks`，controller/resource 不匹配的任务提前剔除 | 无 |
| 中断 | `post_stop()` 优雅停止 | kill 进程 |
| 选项表达 | 自建 `pipeline_override`，支持 case/input 嵌套联动与占位符替换 | 需改写成 `maa_pi_config.json`，表达力待验证 |

依赖这些粒度的上层功能：每用户 `LastProxyStatus` 与统计、`DailyOnceTasks` / `WeeklyOnceTasks` / `MonthlyOnceTasks` 的「正常完成一次才跳过」判断、通知文案里的失败详情。改成套壳后这些要么降级，要么改成解析日志文本（即 MAA / M9A 那种 `LogMonitor` 模式）。

### 与原设计的关系

设计文档把「不驱动外部 GUI 壳」列为非目标，理由是要作为 Client 拿到完整控制力。但当初迫使走 Client 模式的**技术**理由是 `OverflowError`（client 与 agent-server 模式不能共处一进程），而这个问题**已经被子进程隔离解决**——所以那条约束不再强制 Client 模式，剩下的就是反馈粒度的取舍。

如果要既外置又保留粒度，官方给出的集成路径是直接调 `Configurator::generate_runtime()` + `Runner::run()` 这层 C API，绕开 MaaPiCli 的壳，自己控制反馈——这也正是现有 `automas-maafw-runner` 在做的事。

---

## 附：源码定位

```bash
# 插件形态（7 个包）
git show 35193966^:plugins/automas_maafw_interface/src/automas_maafw_interface/loader.py
git show 35193966^:plugins/automas_maafw_runner/src/automas_maafw_runner/runner.py
git show 35193966^:docs/maafw-plugin-service-contracts.md

# 内置形态
git show 612bd30d:app/task/MaaFW/AutoProxy.py
git show 612bd30d:MAAFW_ADAPTER_PLAN.md
git show 612bd30d:docs/dev/maafw-overall-adaptation-report-2026-06-24.md
git show 612bd30d:docs/dev/maafw-plugin-ecosystem-and-m9a-adaptation.md

# 当前状态（主仓残留 + 前端）
git show upstream/dev_v2:app/models/config.py          # MaaFWConfig:1890
git show upstream/dev_v2:app/core/script_types.py      # 注册表 + LEGACY 元数据
git show upstream/dev_v2:frontend/src/composables/useMaaFWScriptConfig.ts
```
