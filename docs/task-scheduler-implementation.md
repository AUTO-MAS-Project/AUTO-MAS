# 当前任务调度实现检查说明

更新：2026-11-04。检查对象：`codex/migrate-task-scheduler-v2` 当前工作区，包括尚未提交的迁移代码；基线为 `64dc394713de70a8ff9e4324d418e207d0759078`。本文描述实际实现，不把原计划或预留接口当成已完成的业务能力。

## 1. 阅读顺序与实现边界

建议先读第 2 节的文件分工，再读第 4 节的正常派发和第 5 节的中止流程，最后用第 9 节的方法清单逐项对照源码。

当前只有三个公开创建模式：`TaskMode.AUTO_PROXY`、`SCRIPT_CONFIG`、`SCRIPT_VIEW`。人工排查、循环和更新都不是创建模式。循环是 timer 的一种触发原因；专项更新另走维护入口，内部仍复用运行树和执行生命周期。

当前四级框架并不表示旧专项都已改成 L3/L4：

```text
L1  _TaskManager.start(mode, tasks, trigger=TaskTriggerReason.MANUAL)
    校验、建完整运行树、登记、发布 task.created
    └─ L2 ScriptExpander
       按根下托管快照派发；插件分支持托管锁，不另建资源预约
       ├─ 内建 task：factory → 旧 manager._execute_task()
       │  └─ manager 自己检查、持锁、重建用户列表、执行用户任务、收尾
       └─ 插件：真实 plugin_expander 返回 UserExpander
          └─ L3 UserExpander：使用已锁托管，准备、持用户锁并派发
             └─ L4 ModeWorker：使用已锁用户，模式执行、用户收尾
```

`TaskBase` 是 L2、L3、L4 共用的生命周期基类，不是一个额外的业务层。L1 是任务管理组件，本身不继承它。插件解析器目前没有在正式宿主装配中接入，L3/L4 是可用的框架扩展点和回归验证对象；当前内建专项实际走左侧 manager 路径。

## 2. 文件树与代码归属

以下树以 `D:/Dev/AUTO-MAS` 为根。各节的方法清单提供可点击的绝对源码位置。

```text
D:/Dev/AUTO-MAS/
├─ main.py                         宿主装配、后台就绪、应用退出
├─ app/api/
│  ├─ dispatch.py                  创建/停止/查询/重连快照；端点专用模型
│  ├─ scripts/operations.py        专项维护操作入口，独立于公开任务模式
│  ├─ queue.py                     队列、时间项的配置读写入口
│  └─ mcp.py                       把已有公开 HTTP 操作开放给 MCP
├─ app/core/
│  ├─ __init__.py                  运行时按需导出 + TYPE_CHECKING 静态导入
│  ├─ timer.py                     启动、定时、循环的到期判定和任务提交
│  ├─ background_tasks.py          背景任务组、并发限额、限时结果与应用关闭
│  ├─ lifecycle.py                 应用退出过程的幂等协调
│  ├─ task_manager.py              L1、要求树建树、运行索引及 TaskManager 单例
│  ├─ notify/
│  │  ├─ lifecycle.py             旧 manager 原持锁位置的等待与凭证取得
│  │  ├─ commands.py              QQ 等通知渠道文字命令的启动适配
│  │  ├─ task_report.py           任务报告与并行社区签到结果衔接
│  │  └─ tasks.py                 通知批次、协调器上下文与旁路投递所有权
│  └─ ws/
│     ├─ protocol.py              消息类型常量和信封
│     └─ publisher.py             Pydantic 数据转 JSON，交给主连接发送
├─ app/models/
│  ├─ task.py                     模式、参数、运行节点、推送订阅与私有日志游标
│  ├─ schema.py                   要求节点、任务树投影、HTTP/WS 公共契约
│  └─ config/queue.py             队列触发配置、时间项、队列项星期周期
├─ app/config/
│  ├─ core/node.py                UUID、父子关系、暂存提交、业务锁、生命周期
│  ├─ core/entry.py                ConfigEntry 的字段/分组/虚拟字段机制
│  ├─ core/group.py                ConfigGroup 的热态读写、字段校验和时区
│  ├─ core/collection.py           ConfigCollection[T] 的有序集合机制
│  ├─ core/manager.py              事务、提交入口、ContextVar 票据、持久化
│  ├─ fields/ref.py                Virtual[T]、Trigger 等声明类型
│  ├─ shortcuts.py                collection、virtual_field、trigger_field
│  └─ wire.py                     从配置声明派生 API 输入/输出模型
├─ app/services/common/
│  ├─ obs_replay.py                OBS 采集及受管临时副本清理
│  └─ telemetry.py                 托管运行观察、计数及本地事件发布
├─ app/task/
│  ├─ lifecycle.py                来源 TaskBase 的执行/中止/收尾契约
│  ├─ context.py                  TaskContext；仅存当前节点参数，隔离复制
│  ├─ script_expander.py           L2 和内建/插件分叉
│  ├─ user_expander.py             L3 插件托管执行骨架
│  ├─ mode_worker.py               L4 三种模式的抽象执行骨架
│  ├─ legacy.py                    旧方法名到 TaskBase 的生命周期适配
│  ├─ manager_base.py              旧专项共用选择、维护检查、跳过、报告逻辑
│  ├─ base.py                      自动代理用户总时限、维护画面监视、用户附加脚本
│  ├─ registration.py              类型化能力声明和工厂契约
│  ├─ builtin_registration.py      正式宿主选择内建专项，构造能力索引
│  ├─ history_core.py              单用户历史归档与任务回放会话
│  └─ 各专项目录/                  专项 manager、AutoProxy、ScriptConfig 等
└─ frontend/src/
   ├─ api/                         OpenAPI 生成的 TaskMode、节点和调用客户端
   ├─ composables/taskSelection.ts  页面选择 → 有序要求树
   ├─ composables/useTaskApi.ts     请求、错误转译、请求受理统计
   ├─ composables/taskTreeProjection.ts  运行树 → 现有面板展示结构
   ├─ composables/useTaskRuntimeState.ts HTTP/WS 运行状态公共缓存
   ├─ composables/useScriptConfigLock.ts 查询配置锁并共享按目标缓存
   ├─ composables/useSatelliteStatus.ts 配置与持久化历史概览，不读取运行缓存
   ├─ services/realtimeSnapshotApi.ts    初始/重连 HTTP 快照
   ├─ services/websocket/types.ts   WS 信封、映射及部分手写传输类型
   ├─ views/scheduler/              调度面板、日志、恢复入口和任务标签页
   └─ views/queue/components/       QueueTriggerSettings、TimeSetManager/Row、QueueItemManager
```

### 2.1 内建专项的具体任务代码

每项的 `registration.py` 提供运行工厂和配置能力；L2 按配置的**精确类型**查工厂。模拟器绑定字段仍属于配置能力，不再生成独立任务资源声明。并非按类名拼接导入 manager。

- MAA：[manager.py](D:/Dev/AUTO-MAS/app/task/MAA/manager.py)、[AutoProxy.py](D:/Dev/AUTO-MAS/app/task/MAA/AutoProxy.py)、[ScriptConfig.py](D:/Dev/AUTO-MAS/app/task/MAA/ScriptConfig.py)。manager 协调安装访问、更新、配置备份恢复、用户任务和汇总通知；单用户文件处理实际专项调用。
- MaaEnd：[manager.py](D:/Dev/AUTO-MAS/app/task/MaaEnd/manager.py) 及同目录 AutoProxy、ScriptConfig、Update；更新文件属于专项能力，不是公开 TaskMode。
- SRC：[manager.py](D:/Dev/AUTO-MAS/app/task/SRC/manager.py) 及同目录 AutoProxy、ScriptConfig；取得托管配置锁后读取并固定本轮安装路径，历史配置恢复仍归 manager。
- General：[manager.py](D:/Dev/AUTO-MAS/app/task/general/manager.py) 及同目录 AutoProxy、ScriptConfig。
- BetterGI：[manager.py](D:/Dev/AUTO-MAS/app/task/BetterGI/manager.py) 及同目录 AutoProxy、ScriptConfig、Update。
- Okww：[manager.py](D:/Dev/AUTO-MAS/app/task/Okww/manager.py) 及同目录 AutoProxy、ScriptConfig、Update。
- OkNte：[manager.py](D:/Dev/AUTO-MAS/app/task/OkNte/manager.py) 及同目录 AutoProxy、ScriptConfig。
- HSR：[manager.py](D:/Dev/AUTO-MAS/app/task/HSR/manager.py) 及同目录 AutoProxy、history；其多引擎选择、恢复和通知继续归专项。
- ZzzOd：[manager.py](D:/Dev/AUTO-MAS/app/task/ZzzOd/manager.py) 及同目录 AutoProxy、ScriptConfig；恢复服务由宿主装配提供。
- BAAH：[manager.py](D:/Dev/AUTO-MAS/app/task/BAAH/manager.py) 及同目录 AutoProxy；不假定所有专项支持全部模式。
- Whimbox：[manager.py](D:/Dev/AUTO-MAS/app/task/Whimbox/manager.py) 及同目录 AutoProxy、ScriptConfig。
- MaaFW、M9A、MSS：[embedded\_manager.py](D:/Dev/AUTO-MAS/app/task/MaaFW/embedded_manager.py) 共用宿主执行入口；[runner\_task.py](D:/Dev/AUTO-MAS/app/task/MaaFW/tools/embedded/runner_task.py) 等继续管理嵌入式 worker。M9A/MSS 在 MaaFW 的运行类型声明中登记。

本文逐方法解释公共调度骨架；专项内部的游戏参数转换、文件格式处理、日志解析和截图算法不逐个展开，入口按上述文件定位。

## 3. 类型提示与数据身份从哪里来

### 3.1 Python 静态类型和运行校验是两条链

1. [app/models/task.py](D:/Dev/AUTO-MAS/app/models/task.py) 是模式和运行结构的声明源：`TaskMode(StrEnum)`、`TaskParams`、各节点的 `Info`/`Current`、`ConfigCollection[具体节点]`。`ScriptItem`、`UserItem` 是新节点类的别名，不是另一套状态模型。
2. [app/config/core/node.py](D:/Dev/AUTO-MAS/app/config/core/node.py) 提供 `uid: UUID`、`parent`、`root`、锁票据和提交方法；`ConfigEntry`/`ConfigGroup`/`ConfigCollection[T]` 的注解与泛型让调用方知道字段和成员类型。热态属性读取和写入拦截是运行机制，不代替这些静态声明。
3. `Virtual[T]` 和 `Trigger` 定义在 [fields/ref.py](D:/Dev/AUTO-MAS/app/config/fields/ref.py)。`Virtual[T]` 实际是带元数据的 `T | None`，计算绑定来自 `@virtual_field`；`Trigger` 是带元数据的 bool，动作绑定来自 `@trigger_field`。Pydantic 元数据负责运行行为，不保证所有类型检查器都能把动态投影推断为具体类。
4. [app/models/config/\_\_init\_\_.py](D:/Dev/AUTO-MAS/app/models/config/__init__.py) 汇总专项配置类型和 `CLASS_BOOK`；旧 manager 使用 `ScriptConfigType`/`UserConfigType` 等联合类型。`ScriptAutoProxyBase[S, U]` 用泛型细化某专项和用户配置类型；`selected_user_configs()` 的 overload 尽量保留传入的用户具体类型。
5. [app/task/registration.py](D:/Dev/AUTO-MAS/app/task/registration.py) 定义 `ManagerFactory = Callable[[ScriptItem], TaskExecuteBase]`、`ScriptRegistration`、`ScriptCapabilities`。工厂只接收当前托管运行节点，节点参数继续由 `TaskContext` 传递。配置类型和运行工厂的联系来自注册校验，不是类型检查器自动证明的映射关系。
6. [app/core/\_\_init\_\_.py](D:/Dev/AUTO-MAS/app/core/__init__.py) 在 `TYPE_CHECKING` 下显式导入真实单例，为编辑器提供 `Config`/`TaskManager`/`MainTimer` 等的类型；运行时由 `__getattr__` 按需导入并缓存。静态检查不必真的初始化所有核心组件。
7. [app/models/task.py](D:/Dev/AUTO-MAS/app/models/task.py) 对旧 `TaskExecuteBase` 同样使用 `TYPE_CHECKING` 导入和运行时 `__getattr__`，实际实现归 [app/task/legacy.py](D:/Dev/AUTO-MAS/app/task/legacy.py)。这是旧导入路径兼容，不是模型层拥有执行实现。
8. [TaskContext](D:/Dev/AUTO-MAS/app/task/context.py) 用 dataclass 和 `JsonValue` 描述当前层参数，不重复保存任务根。队列、托管、用户的 `params` 分别复制传递，**不自动合并上层参数**。字段 `instance_idx` 从当前托管节点的 params 读取，并校验为非负整数。

根集合调用 `build()` 时须显式绑定泛型，例如 `ConfigCollection[QueueConfig].build([QueueConfig], name="QueueConfig")`。其返回注解是 Self，未绑定调用类时，当前检查器会把集合成员推断为 Unknown；参数列表负责登记允许运行的成员类型。模拟器、计划、脚本、队列和社区账号集合现均已绑定成员类型，模型私有字段及属性返回值也保留准确泛型；混合计划与脚本集合使用对应的具体配置联合类型。

### 3.2 输入校验、运行树导出与前端类型

- HTTP 创建包装 [TaskCreateIn](D:/Dev/AUTO-MAS/app/api/dispatch.py) 只属于端点：`mode` 与 `tasks`；内部直接调用 `TaskManager.start(mode, tasks)`，不要求构造包装对象。
- [TaskSelectionNode](D:/Dev/AUTO-MAS/app/models/schema.py) 递归声明 `uid`、`params`、`children`；`extra="forbid"` 拒绝多余字段。同文件的 `TaskRequirements` 是内部允许模型节点或字典的宽输入类型；L1 的 `_launch()` 用 `TypeAdapter(dict[int, TaskSelectionNode])` 解析，直接在建树时校验顺序、归属和层数。
- `TaskTreeData = config_contract(TaskItem, include_collections=True)` 从运行节点声明派生传输模型，集合形状是 `order + data`。这是动态生成的 Pydantic 契约，不是手写另一份运行数据。
- FastAPI 根据端点/公共模型导出 OpenAPI；前端执行 `yarn openapi` 调用 openapi-typescript-codegen 和 `scripts/postprocess-openapi.mjs`，生成 `TaskMode`、`TaskSelectionNode`、`TaskItemDocument`、`TaskScriptItemDocument` 等及 HTTP 客户端。
- [websocket/types.ts](D:/Dev/AUTO-MAS/frontend/src/services/websocket/types.ts) 把 `task.info.updated` 数据别名指向生成的 `TaskItemDocument`，并声明消息类型映射；其他消息仍有手写类型。
- [realtimeSnapshotApi.ts](D:/Dev/AUTO-MAS/frontend/src/services/realtimeSnapshotApi.ts) 使用生成的快照类型和 GetService 方法，移除了手写快照外壳与通用 request 调用。WS 完成消息仍有手写信封类型，但 task 字段引用生成树类型。
- [taskTreeProjection.ts](D:/Dev/AUTO-MAS/frontend/src/composables/taskTreeProjection.ts) 的展示接口、[useTaskRuntimeState.ts](D:/Dev/AUTO-MAS/frontend/src/composables/useTaskRuntimeState.ts) 的运行缓存类型和页面选择类型属于前端内部投影。

### 3.3 当前类型覆盖的实际限度

L1/L2 的构造、派发、停止、查询，以及 L3/L4 的解析、准入、工厂和生命周期已补齐主要参数/返回注解。`PluginExpander` 明确返回 UserExpander 或 None，要求节点直接使用 TaskSelectionNode，用户集合访问用只读 `_UserLookup` 协议；根节点和锁内配置的非空约束由创建/执行位置保证。不再声明中间建树规格。

旧专项的平铺属性和开放构造参数仍保留动态形状；后端兼容展示字典已移除；Config 动态生成的 TaskTreeData 也不是普通静态类型别名。局部抑制与保留原因见第 12 节。类型检查通过不等于全仓 strict 模式已通过，实际 worker 绑定、配置有效性和 Pydantic 字段值仍需运行校验；TaskParams 只保证 JSON 值，不为每个插件提供独立参数 schema。

### 3.4 请求身份与运行身份

顶层固定为索引 0 的唯一入口：自动代理选择一个队列或 -，配置／查看会话选择一个托管。下级请求索引表达选择顺序，真实队列下 uid 是队列项 UUID，L1 从其配置解析托管 UUID；直接运行 uid="-" 的下一级才是托管 UUID。运行节点自行生成 UUID，进度指针存运行 UUID，配置查找使用 info 中的业务 ID。同一托管重复出现时各次独立记录。

运行树现在为 `TaskItem → TaskScriptItem → TaskUserItem → LogRecord`，根直接持有 scripts 集合。配置/查看会话不再建立空队列节点。管理器已有的运行映射保存多个独立任务根，不建立总根。不保留 TaskQueueSource 或来源区间。托管节点不保存队列 ID、队列项 ID 或队列参数；L1 记时只保存局部队列引用，L2 直接遍历根下托管。

触发原因使用 TaskTriggerReason，仅包含 manual、startup、timed、cycle 四个独立值，每次创建只对应其中一项。根 info.trigger 是唯一来源，不保存 trigger_source 或 is_cycle 派生字段；HTTP、WS 和前端运行状态直接传递 TaskTriggerReason，通知与匿名统计只在各自消费边界转换分类，不从自定义 params 猜测原因。

## 4. 一次任务如何派发

### 4.1 入口和要求树

前端手动入口：配置候选 → 本次运行范围草稿 → `scopeRequest()` → `requestTaskStart()` → 生成客户端 → `/api/dispatch/start` → `TaskManager.start(mode, tasks)`。首页、托盘、配置会话复用这条转换/请求链；页面仅保留一份有序范围草稿；快捷入口用 `targetRequest()` 构造相同契约。

通知渠道经 `execute_notification_command()` 把唯一名称解析为 ID，直接创建要求树调用相同 start。MCP 将公开 dispatch 操作作为工具开放，并不另有一套执行器。

要求树示例（尖括号内容代表对应 UUID，示意并非可原样发送的请求）：

```json
{
  "mode": "AutoProxy",
  "tasks": {
    "0": {
      "uid": "<队列UUID>",
      "params": {},
      "children": {
        "0": {
          "uid": "<队列项UUID>",
          "params": {"instance_idx": 0},
          "children": {"0": {"uid": "<用户UUID>", "params": {}}}
        }
      }
    }
  }
}
```

顶层必须且只能包含索引 0；其余各层索引按传入顺序从 0 连续递增。空 children 在自动代理中展开全部当前成员。`uid="-"` 的队列层必须显式选择托管。非空选择须是配置顺序的子序列。`ScriptConfig`/`ScriptView` 请求只有“托管 → 一个用户或 default”两层，不接受空目标或多个目标。

### 4.2 L1 完整受理与统一记账

`start(mode, tasks, *, trigger=MANUAL)` 先检查停止全部屏障和宿主工厂，要求树只允许一个顶层入口；随后在短事务内直接处理该入口，校验下级结构、归属、顺序和出现次数。队列项解析成实际托管并直接加入根 scripts；空用户选择展开全部，禁用和天数不足的用户仍建立节点。各级 params 隔离复制，不隐式合并父参数。

完整树建好后，在同一事务提交对应队列的 LastStartTime，并按触发原因提交 LastStartupTime、Cycle.LastRunAt。直接选托管不伪造队列时间。失败回滚全部关联时间，不发布部分树；已受理后取消仍保留创建记录。timer 不再负责提交这些时间。

事务结束后加入运行映射，发布创建消息并启动 L2；维护操作仍不创建普通调度面板。创建返回单个任务 ID，去掉队列运行层不改变一次请求的返回数量。

### 4.3 L2：根下派发与托管锁

L2 直接按根 scripts 的顺序执行，星期条件仍由 L2 跳过。不按来源队列切片，不再安排队列前后附加脚本。各托管、用户参数仍按层传递，不保存原队列来源或队列参数副本。建树后删除或重排原队列不改变本轮托管清单。

插件分支每次先解析并确认托管存在，再尝试非级联 X 锁；等待后重新解析。L2 保存凭证，将已锁配置交插件解析器及 L3，等待 L3 连同恢复完整结束后解锁。正常路径及 final_task 共用释放当前凭证的逻辑。解析器返回旧能力时，先释放探测锁，再进入旧 manager 的递归锁路径，避免重复持锁。

### 4.4 内建 manager 路径：以 MAA 为例

`MaaManager` 的构造绑定 script_info/task_info；`ScriptManagerBase._run_main_task()` 先复用游戏更新/维护公告检查，再进入 manager.main_task。

`MaaManager.main_task()`：check → prepare → 标记 prepared → 遍历用户 → 配置/维护/次数限制检查 → 根据 `execution_mode` 从 METHOD_BOOK 建单用户任务 → `run_user_task()` → 等单用户完整收尾 → 下一个用户。

`prepare()` 获取安装资源访问，按旧语义对托管取**递归 X 锁**，引用当前热态配置，处理遗留恢复/配置备份，初始化设备，按旧逻辑 `set_users()`。因此旧 manager 可以替换 L1 建立的用户节点，用户运行 UUID 可能在准备阶段重新生成；新框架没有强迫其保持插件路径的不可变用户快照。

`AutoProxyTask` 的 check/prepare/main_task/final_task 处理单用户脚本注入、启动、日志/权威结果消费、重试、截图、历史保存和恢复。`ScriptConfigTask` 处理原生 GUI 配置会话；`ScriptView` 在旧路径映射到 ScriptConfig 执行方法，并通过 view_only 属性标识查看语义。实际查看支持和保存规则仍由专项决定。

manager.final_task 处理专项汇总、设备/配置恢复、通知；外层 `_finalize_task()` 还可补充异常准备时的恢复，finally 解配置票据。L2 等它全部结束后才继续派发。旧 manager 在原有 `lock_script_config()` 位置等待递归 X 锁；每次重试检查配置是否删除或替换，取消由 TaskBase 传播。原有持锁范围保持不变。

这条路径保持旧专项能力，也意味着“其他未占用用户可随时修改”的细粒度承诺**只适用于新 L3/L4 路径**；不能把旧递归锁路径描述为已完成同等迁移。

### 4.5 插件 L3/L4 路径

L3 接收 L2 已锁的托管配置，执行 check/prepare，然后逐用户派发。每次先解析并确认用户存在，再等待用户级联 X 锁；取得后核对身份、读取最新启用状态及剩余天数。失效记异常，禁用或天数为 0 记跳过，继续其他节点。凭证留在 L3，已锁配置传给 build_worker(user, config)，等待 L4 完整收尾后解锁。

L4 接收已锁用户配置，只做模式校验、进度、check/prepare/main_logic 和用户恢复，不再重新查配置或申请、释放票据。共享 default 传 None，不创建账号、不锁全用户，由 L2 的托管锁保护。worker 必须给出实际结果，正常返回仍为运行会报错。

游戏订阅／释放注释保留在 L3 托管锁已由上层取得之后、用户派发之前，以及对应恢复之后；真正插件与游戏能力尚未接入，不能把骨架或注释视为已完成的模块迁移。

## 5. 中止、取消传播与收尾

### 5.1 正常中止路径

```text
前端 stopTask / stopNativeConfig
  → POST /api/dispatch/stop {taskId}
  → TaskManager.stop_task → stop
  → ScriptExpander.stop
     写入任务树 cancelled；关闭新回放采集；通知当前旧 manager 手动停止
  → TaskBase.stop
     cancel 顶层 Task，并 await 它
     → 当前 await 链接到的子任务收到 CancelledError
     → 最内层 run.finally 等完整 final_task
     → 逐层返回并各自 final_task
  → L2 final_task 发布 task.completed
  → 顶层 ended 信号 → TaskManager.drop
  → accomplish.set；stop 返回；HTTP 返回受理结果
```

`spawn(child)` 是直接 `await child.run()`，不为每层另开 asyncio Task；旧适配的 spawn 也委托同一契约。取消从顶层 await 链传下去。子层通常没有自己的 `_task` 句柄，单独对其 TaskBase.stop 没有顶层停止的含义。

`ScriptExpander.stop()` 同时设置任务回放取消标记；当前旧 manager 标记 stopped_manually 并执行取消钩子。实际关闭脚本进程、设备、日志读取器、临时文件和恢复配置由各专项 final_task 负责。Python 协程取消不是强制杀所有系统进程；不可取消的线程调用也不会因 cancel 自动结束。

托管／用户业务中的附加脚本继续复用 execute_script_task：执行库等待进程清理后抛出 CancelledError，由所属执行链继续收尾。L2 不再编排队列附加脚本。

### 5.2 TaskBase 怎样保证收尾

- `run()` 在成功、普通异常和 CancelledError 的 finally 中都执行 `_wait_finalizer()`；普通异常交 on_crash，取消标记后继续向上抛。
- `_wait_finalizer()` 只创建一个 `_finalizer` Task，通过 shield 等待。等待者重复收到取消时继续等 finalizer，等它结束后再传播取消。
- `_finalize()` 调用 final_task，普通收尾异常记录到 error/on_crash；顶层再发 ended，最后无论如何置 accomplish。
- 只有持顶层 `_task` 的执行对象发送 ended，因此子任务收尾不会误删整个任务登记。
- start 后立刻取消、run 尚未进入时，stop 仍补调用 `_wait_finalizer()`。
- final_task 自己若被外部直接取消、ended 接收器抛异常等，不属于“所有代码永不失败”的保证；应对照实际异常处理检查，不能从 shield 推导出无限兜底。

### 5.3 资源释放次序与提交边界

L4 完成用户 finish 并提交该收尾协程自身暂存，返回后由 L3 释放用户配置锁；不向树写锁状态。L3 完成托管恢复、游戏释放预留和该收尾协程暂存提交，返回后由 L2 释放托管锁。两层持票者都有 final_task 兜底，提交或恢复失败也要释放凭证。

互斥归派发层：L2 持托管本体非级联 X 锁，L3 持当前用户级联 X 锁。旧 manager 继续在自己的原持锁位置等待递归 X 锁；不存在两套同时占用的锁或目录预约。未占用用户仍可修改、删除；等待期间删除不会对旧对象永久等锁。

重要：final_task 在单独 Task 运行。X 票据的 ContextVar 可以继承，但暂存队列按实际执行 Task 隔离；**final_task 的 commit 不会提交主流程 Task 尚未提交的字段**。prepare/main_logic 必须在返回或交接前原地提交自己的修改。不能把最终 commit 理解为“把所有协程未提交内容自动扫进来”。

旧专项同步/线程回调使用 `LegacyCallbacks.submit(operation)`：由消费者自己执行赋值和 commit，不代提交其他协程暂存。桥由旧 manager 创建，子任务复用；旧生命周期收尾前后排空，L2 在专项返回后关闭入口。插件 L3/L4 不依赖这条桥。

### 5.4 停止全部、并发创建、应用退出

`stop("ALL")` 通过 `_stop_lock` 串行化；先设置 `_stopping_all=True` 拒绝新 start，取消待执行电源动作，再等待 `_idle` 确保已进入建树的创建完成，然后 gather 停止运行任务和维护任务，finally 解除屏障。

停止当前轮或 ALL 不修改队列启动/定时/循环开关。timer 后续到期仍会提交新任务；屏障只覆盖这次停止全部过程。要关闭未来触发，需要修改队列配置。

[main.py](D:/Dev/AUTO-MAS/main.py) 的 shutdown_services 停 WS 入站和连接钩子、取消电源动作，并行停止 MainTimer 和全部任务；History.close 等用户收尾，再回收桌面资源、更新/回放服务，shutdown BackgroundTaskManager、关闭通知，最后 flush 配置。`ShutdownCoordinator` 保证退出清理只执行一次。

## 6. 状态、日志、历史和界面怎样一致

### 6.1 唯一运行状态源与分类订阅

运行树继续是状态、结果和日志的唯一业务来源；即时信号仍在事务内发送，接受过程态。元数据按配置基类 effective 视图导出本次工作区值，不依靠后续日志事件刷新状态；完整查询仍走原导出路径。任务模型定义之后的 _info_changed 与 _log_changed 两个配置类订阅函数分别处理元数据和日志，不新增后台发布队列。正文变化不发布整棵信息树；状态、参数、指针及结构变化才导出元数据，相同字段值不重复推送。只读投影逐配置分组排除正文后，再通过同一动态契约验证，不复制并序列化巨量正文再删除。

### 6.2 WS 与查询

- task.info.updated：树结构、基础信息、状态、指针、结果和日志记录头部，省略根／托管 current.log 与 LogRecord.info.content。
- task.log.updated：log、seq、append、firstLine；普通追加只发新增片段，首次、重置、切换来源或片段超限时整体替换，内容不变不重复推。
- task.completed：终态、结果与同一不含正文的树。完整终态树仍留存供查询。
- task.notice 与 task.script.started/finished 继续各自负责提示和执行统计。

完整查询与 runtime-snapshot 不裁剪日志。快照包含完整当前正文及 logSeq/logFirstLine；尚未发送日志时以序号 0 建立初始基线，首个包必替换；已有过程态游标与当前正文不匹配时 logSeq 为空，前端不能据此直接追加。游标由任务根 PrivateAttr 保存，发送异常不推进；解绑时清理，不进入公开信息树或配置回滚。类级订阅随任务模型导入自动安装，接收者在模型文件内按运行登记筛选事件并直接发送；创建不绑定回调，结束仅注销并清理私有游标；不另建 _LogState、管理器日志映射或推送锁。按行日志基线仅浅拷贝行引用，正常追加只拼接新增行；旧专项字符串直接保存引用。

前端独立合并日志：append=false 重建基线，连续 seq 才能追加；缺少基线或漏消息时拉快照。信息树消息不覆盖日志缓存，迟到快照不回退已有更大日志序号。WS 不充当可靠事件队列，断线依赖完整快照恢复。

### 6.3 日志保留与显示窗口

LogRecord.info.content 保留完整行列表，旧专项 current.log 也不再写入 4000 字符、80 行或 500 行窗口。模型没有日志裁剪 serializer，根 current.log 读取完整当前来源；信息树 first_line 及其写入接口已移除。

旧协议的 WS 替换包与前端显示缓冲仍各保留 20 万字符预算，属于传输／显示层。firstLine 在截取替换包时按丢弃换行数计算，前端本地裁剪继续推进显示行号；查询仍能得到完整正文。游标根据完整来源比较增量，初次推送只发窗口后，后续也能正确衔接新增内容。

### 6.4 历史、通知和统计所有者

- 单用户专项给出结果和 HistoryWrite，直接调用 L2 传入的 TaskHistorySession；后者装配 History.record、OBS 附件采集/丢弃能力并复用公共归档管线。
- 失败截图和日志语义仍归专项；TaskHistorySession 按运行 UUID 管采集归属，OBS 服务负责安全清理临时文件，无用户归属的诊断不伪造用户历史。
- 旧 manager 继续生成专项报告并发起通知；L2 的通知批次覆盖其整个生命周期，任务协调器衔接社区签到。L2 不再生成一套重复的单用户专项历史。
- telemetry.observe_script_run 统计一次托管运行，ScriptExpander.final_task 统计一次任务运行及耗时；前端 useTaskApi 记录创建/停止的**请求受理**，不能当成脚本成功或配置保存成功。

### 6.5 动态任务结果

用户结果由日志记录动态生成，托管结果聚合用户；任务根直接按来源框架的摘要格式组合托管名称、完成/未完成数量及用户结果。公共摘要不区分维护跳过，按用户状态统一计数；维护判断及其通知归专项。

所有结果使用 `Virtual[str]` 与 `@virtual_field`，读取或序列化时按当前运行树计算。完成消息直接读取根 `info.result`；运行中查询、WS 树、完成树和最近终态使用同一口径。收尾修改的日志和状态会进入最终结果，不缓存任务开始时或收尾前的摘要。

已删除独立的 `execution.py` 和完成时的详细日志排版路径。`push_log` 和排版模式留在旧执行器内部；专项通知继续使用已有报告过滤与公共排版，不把通知组件依赖引入任务模型。

本次简化验证：后端全量 1240 项通过、3 项跳过、29 项 subtest 通过；27 个相关文件的 Pyright/mypy 均零诊断，lint/format 通过，OpenAPI 的 266 条路径及模型保持不变。回归覆盖动态日志/状态/集合变化、维护跳过，以及成功、异常、取消后的结果与查询和终态树一致。

## 7. timer 现在负责什么

队列 `Info.StartUpMode` 为 Never/Always/DailyFirst，`TimeEnabled` 与 `CycleEnabled` 为独立开关。TimeSet 配置星期与时刻；QueueItem.Schedule.Days 只决定 L2 是否执行该队列项，timer 不逐项派发。

Cycle 的 IntervalMinutes 为队列统一间隔，LastRunAt 是最近循环成功提交时间，NextRunAt 是 LastRunAt + 间隔的虚拟值，ResetTimer 把 LastRunAt 设为当前时间。LastRunAt 为空时首次启用立即到期。隐藏 Data.LastStartTime 是 timer 最近成功提交队列的时间，Data.LastStartupTime 用于启动日期判定。

`MainTimer.start()` 全局只派发一次启动检查异步任务；每秒检查等待它完成后再进入普通检查。与浏览器 WS 建连和重连无关。

`timed_start(startup=...)` 同时判断启动、定时、循环；任一命中创建普通 AutoProxy 要求树，同次检查合并成一个队列任务，不检查正在运行的队列。成功受理后短事务更新对应时间，不等执行开始/结束。队列在创建期间被删不会恢复；创建期间用户重置了 LastRunAt 时不以旧读值覆盖。

定时补跑和去重保留：以本地墙钟区间展开计划时刻；时间槽/计划时刻内存去重 + 持久化 LastStartTime 去重；错过超过 10 分钟不补。循环不积累逐轮债务，也不持有执行会话。关闭定时/循环模块后前端禁用对应控件；模型显隐控制编辑范围，定时项的实际字段写入和集合结构变更由 queue.py 的运行时信号拒绝并回滚，Config 不另行判断开关。

## 8. 检查时需要特别区分的现状

1. 四层运行信息树已经统一；四级插件执行骨架已经存在；正式内建专项没有因此全部变成细粒度 L3/L4。
2. 真实队列下的请求第二层是队列项 UUID，不是托管 UUID；直接运行第二层才是托管 UUID。
3. 旧 manager 可以 set_users 重建用户运行节点；插件发布后的用户快照禁止替换。重复托管的托管运行节点仍彼此独立。
4. L3/L4 的抽象 check/prepare/finish 默认钩子没有实际游戏业务；插件实现必须提供真实 main_logic、结果与原协程提交，游戏资源只有编排注释。
5. 非递归托管锁允许未执行用户修改；旧 manager 的递归锁仍锁全子树。配置层真实票据是修改权限依据，树内不再保存 locked/recursive_lock；前端读取实际配置锁状态。
6. 队列展开清单及 Days 是创建时快照；后续执行读取托管/用户热态字段。L2 和结束路径不再重读来源队列安排前后脚本或完成后动作。
7. API 树类型来自配置投影，执行骨架的主要函数已补类型；旧构造/兼容投影仍有动态边界，前端展示投影只在界面侧保留，HTTP 快照已经使用生成客户端。
8. TaskBase 的 shield 保护收尾等待，不是强杀、无限重试或跨协程提交方案。取消时是否关闭外部进程与恢复成功仍须看对应专项实现。
9. `TaskStatusOut` 声明了 userId/finishedAt 等字段，但当前 get_task_status 只填写 taskId/status/mode/trigger/detail；未赋值字段保持默认，不能当成已实现的完整终态元数据。
10. `WSTaskScriptStartedData.mode` 的旧契约仍接受 CycleRun，当前生产者实际发送 AutoProxy；这不表示公开创建模式仍保留 CycleRun。

## 9. 公共调度方法清单

以下按文件和类列出当前方法及直接职责。属性按“读取/投影”说明，不把它们当作新的存储。源码行号是本文生成时的位置，后续改动可能使行号移动。

<!-- METHOD_INDEX -->

### app/api/dispatch.py

- [TaskCreateIn.validate\_indices](D:/Dev/AUTO-MAS/app/api/dispatch.py:69)：在 Pydantic 解析前要求顶层索引按传入顺序从 0 连续递增。
- [async get\_task\_runtime\_snapshot](D:/Dev/AUTO-MAS/app/api/dispatch.py:130)：返回运行中任务的完整树、当前日志及已启用排期的脚本标识。
- [async get\_task\_status](D:/Dev/AUTO-MAS/app/api/dispatch.py:143)：按根 taskId 查询运行状态或最近终态；不存在时返回业务 404。
- [async get\_tasks](D:/Dev/AUTO-MAS/app/api/dispatch.py:158)：查询指定根或全部运行根的完整树，组装 index/data。
- [async get\_power\_countdown\_snapshot](D:/Dev/AUTO-MAS/app/api/dispatch.py:178)：读取独立电源倒计时的初始快照。
- [async add\_task](D:/Dev/AUTO-MAS/app/api/dispatch.py:191)：拆出 mode/tasks 调用 L1，返回 taskId 或错误外壳。
- [async stop\_task](D:/Dev/AUTO-MAS/app/api/dispatch.py:210)：调用 TaskManager 停止指定根或 ALL，等待生命周期收尾后返回。
- [async get\_power](D:/Dev/AUTO-MAS/app/api/dispatch.py:229)：读取当前待执行电源动作或尚未启动倒计时的全局标志。
- [async set\_power](D:/Dev/AUTO-MAS/app/api/dispatch.py:252)：改全局完成后动作，清队列延时并取消旧待执行电源任务。
- [async cancel\_power\_task](D:/Dev/AUTO-MAS/app/api/dispatch.py:276)：撤销电源任务，错误转为业务错误外壳。

### app/core/task_manager.py

- [\_TaskManager.\_\_init\_\_](D:/Dev/AUTO-MAS/app/core/task_manager.py:55)：初始化执行能力、运行登记、终态缓存，以及创建与停止全部的同步状态。
- [\_TaskManager.bind\_manager\_factories](D:/Dev/AUTO-MAS/app/core/task_manager.py:71)：[兼容旧专项] 仅供现有宿主绑定旧 manager 工厂；新插件执行能力接入 L3/L4。
- [property \_TaskManager.task\_info](D:/Dev/AUTO-MAS/app/core/task_manager.py:84)：[兼容旧调用方] 旧运行表视图；新查询使用 get_task() 或 get_runtime_snapshot()。
- [property \_TaskManager.task\_handler](D:/Dev/AUTO-MAS/app/core/task_manager.py:98)：[兼容旧调用方] 旧执行器表视图；新代码通过 stop() 和任务查询接口操作。
- [\_TaskManager.\_check\_accepting](D:/Dev/AUTO-MAS/app/core/task_manager.py:105)：创建前检查停止全部屏障，并确认宿主已提供旧工厂或插件解析能力。
- [async \_TaskManager.start](D:/Dev/AUTO-MAS/app/core/task_manager.py:112)：按模式、单入口要求树和触发原因创建普通任务，返回运行 UUID。
- [async \_TaskManager.start\_maintenance](D:/Dev/AUTO-MAS/app/core/task_manager.py:131)：[兼容旧专项] 旧手动更新入口；普通任务使用 start()，新专项维护能力放在专项业务入口。
- [async \_TaskManager.\_launch](D:/Dev/AUTO-MAS/app/core/task_manager.py:145)：L1：完整校验单入口要求树、建树和记时，随后登记、通知并启动 L2。
- [async \_TaskManager.stop\_task](D:/Dev/AUTO-MAS/app/core/task_manager.py:324)：[兼容旧调用方] 停止方法旧名；新代码直接调用 stop()。
- [async \_TaskManager.stop](D:/Dev/AUTO-MAS/app/core/task_manager.py:328)：停止指定任务或 ALL，并等待对应执行器完成收尾。
- [\_TaskManager.\_prune\_recent](D:/Dev/AUTO-MAS/app/core/task_manager.py:355)：按最旧记录优先清理最近终态，最多保留 200 项及结束后 30 分钟。
- [\_TaskManager.get\_task](D:/Dev/AUTO-MAS/app/core/task_manager.py:366)：按运行 UUID 查询完整任务树，包含全部日志；找不到时返回 None。
- [\_TaskManager.get\_task\_status](D:/Dev/AUTO-MAS/app/core/task_manager.py:381)：从完整任务树生成轻量状态响应，将 pending 映射为 running。
- [\_TaskManager.get\_runtime\_snapshot](D:/Dev/AUTO-MAS/app/core/task_manager.py:398)：组装初次连接或重连快照：普通运行任务及完整日志基线。
- [async \_TaskManager.drop](D:/Dev/AUTO-MAS/app/core/task_manager.py:432)：顶层 ended 后注销同一执行器、清理日志游标并缓存完整终态。

### app/task/lifecycle.py

- [TaskBase.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/lifecycle.py:55)：初始化顶层句柄、唯一 finalizer、error/cancelled 和 accomplish。
- [async TaskBase.main\_task](D:/Dev/AUTO-MAS/app/task/lifecycle.py:63)：抽象主流程，具体层必须实现。
- [async TaskBase.final\_task](D:/Dev/AUTO-MAS/app/task/lifecycle.py:66)：可覆盖的生命周期收尾钩子，不自带业务配置恢复策略。
- [async TaskBase.on\_crash](D:/Dev/AUTO-MAS/app/task/lifecycle.py:69)：默认记录未处理异常，并保护记录动作本身。
- [property TaskBase.running](D:/Dev/AUTO-MAS/app/task/lifecycle.py:77)：判断 start 创建的顶层 Task 是否仍未结束。
- [TaskBase.start](D:/Dev/AUTO-MAS/app/task/lifecycle.py:80)：重置本轮控制状态，create_task(run) 派发顶层任务，运行中重复启动报错。
- [async TaskBase.spawn](D:/Dev/AUTO-MAS/app/task/lifecycle.py:90)：同 asyncio Task 内直接 await child.run，子任务完整收尾结束才返回。
- [async TaskBase.run](D:/Dev/AUTO-MAS/app/task/lifecycle.py:98)：执行 main_task，区分取消和普通异常，finally 等收尾。
- [async TaskBase.\_finalize](D:/Dev/AUTO-MAS/app/task/lifecycle.py:111)：执行 final_task、处理普通收尾异常，顶层发 ended，最后设置 accomplish。
- [async TaskBase.\_wait\_finalizer](D:/Dev/AUTO-MAS/app/task/lifecycle.py:127)：只创建一次收尾 Task，用 shield 抵挡等待者的重复取消，收尾结束后再传播取消。
- [async TaskBase.stop](D:/Dev/AUTO-MAS/app/task/lifecycle.py:140)：取消并等待顶层 Task；尚未进入 run 就取消时也补齐收尾。

### app/task/context.py

- [TaskContext.with\_params](D:/Dev/AUTO-MAS/app/task/context.py:15)：用 deepcopy 替换当前层 params，返回新上下文，不把父层参数隐式合并进来。

### app/task/script_expander.py

- [ScriptExpander.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/script_expander.py:28)：持有 TaskItem、历史会话、报告协调器与当前旧 manager。
- [async ScriptExpander.stop](D:/Dev/AUTO-MAS/app/task/script_expander.py:43)：在树中记录取消，停止接收回放采集并通知旧 manager，然后沿 TaskBase 取消与等待。
- [async ScriptExpander.main\_task](D:/Dev/AUTO-MAS/app/task/script_expander.py:51)：在任务级遥测 span 内执行 _run_task。
- [async ScriptExpander.\_run\_task](D:/Dev/AUTO-MAS/app/task/script_expander.py:66)：直接遍历根下托管，按星期条件跳过或派发；不按来源队列分段，汇总根终态。
- [async ScriptExpander.\_run\_script](D:/Dev/AUTO-MAS/app/task/script_expander.py:111)：先检查托管存在性，再为插件取得非级联 X 锁；传已锁配置给 L3，等待完整收尾后归还；旧 manager 自持递归锁。
- [async ScriptExpander.\_release\_script\_lock](D:/Dev/AUTO-MAS/app/task/script_expander.py:206)：归还 L2 当前仍持有的托管凭证并清空引用；正常路径和 final_task 共用。
- [async ScriptExpander.on\_crash](D:/Dev/AUTO-MAS/app/task/script_expander.py:213)：给根标异常、发错误提示，再走基础日志兜底。
- [async ScriptExpander.final\_task](D:/Dev/AUTO-MAS/app/task/script_expander.py:225)：兜底解锁、关闭历史、结清报告、发布不含正文的终态树与动态结果，记录原有统计。

### app/task/user_expander.py

- [\_UserLookup.get](D:/Dev/AUTO-MAS/app/task/user_expander.py:22)：只读用户查找契约；允许各具体 ConfigCollection 保留自己的用户类型。
- [UserExpander.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/user_expander.py:26)：接收当前托管运行节点和 L2 已锁的热态托管配置。
- [UserExpander.user\_collection](D:/Dev/AUTO-MAS/app/task/user_expander.py:39)：默认访问公开 UserData；保留真实插件声明配置访问的接入位置。
- [UserExpander.resolve\_user](D:/Dev/AUTO-MAS/app/task/user_expander.py:43)：从已锁托管配置解析本用户，并核对创建时记录的对象身份。
- [UserExpander.can\_run\_user](D:/Dev/AUTO-MAS/app/task/user_expander.py:52)：自动代理检查启用且剩余天数不为 0；配置/查看会话不做该筛选。
- [async UserExpander.record\_user\_state](D:/Dev/AUTO-MAS/app/task/user_expander.py:57)：新增带原因的日志节点，并提交用户状态。
- [async UserExpander.main\_task](D:/Dev/AUTO-MAS/app/task/user_expander.py:66)：执行托管检查和准备，逐用户先检查存在再取级联 X 锁，锁内复核准入并把已锁配置交 L4。
- [async UserExpander.\_release\_user\_lock](D:/Dev/AUTO-MAS/app/task/user_expander.py:117)：归还 L3 当前仍持有的用户凭证并清空引用，不更新任务树锁字段。
- [async UserExpander.check](D:/Dev/AUTO-MAS/app/task/user_expander.py:124)：可覆盖托管级检查，返回非空原因则中止该托管。
- [async UserExpander.prepare](D:/Dev/AUTO-MAS/app/task/user_expander.py:128)：可覆盖托管级准备；主协程暂存应在该协程提交。
- [UserExpander.build\_worker](D:/Dev/AUTO-MAS/app/task/user_expander.py:132)：按真实能力构造 L4，并显式传入已锁用户配置；共享目标传 None。
- [async UserExpander.finish](D:/Dev/AUTO-MAS/app/task/user_expander.py:138)：可覆盖托管恢复与结果保存钩子，仍在持锁期。
- [async UserExpander.on\_crash](D:/Dev/AUTO-MAS/app/task/user_expander.py:141)：提交托管异常和原因日志，基础层记录异常。
- [async UserExpander.final\_task](D:/Dev/AUTO-MAS/app/task/user_expander.py:149)：插件恢复及游戏释放预留后，提交本收尾协程暂存并兜底释放用户锁；托管锁由 L2 释放。

### app/task/mode_worker.py

- [ModeWorker.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/mode_worker.py:20)：接收父 L3、用户运行节点及上层已锁用户配置，不再拥有票据。
- [async ModeWorker.main\_task](D:/Dev/AUTO-MAS/app/task/mode_worker.py:32)：校验模式与已锁配置，设置用户进度，调用 check/prepare/main_logic。
- [async ModeWorker.check](D:/Dev/AUTO-MAS/app/task/mode_worker.py:47)：可覆盖单用户检查，非空原因转异常。
- [async ModeWorker.prepare](D:/Dev/AUTO-MAS/app/task/mode_worker.py:51)：可覆盖单用户脚本准备，修改须本协程提交。
- [async ModeWorker.main\_logic](D:/Dev/AUTO-MAS/app/task/mode_worker.py:55)：抽象真实插件调用，负责给出用户结果并就地提交主流程修改。
- [async ModeWorker.finish](D:/Dev/AUTO-MAS/app/task/mode_worker.py:58)：可覆盖锁内用户恢复和保存。
- [async ModeWorker.on\_crash](D:/Dev/AUTO-MAS/app/task/mode_worker.py:61)：通过 L3 记录当前用户异常及日志。
- [async ModeWorker.final\_task](D:/Dev/AUTO-MAS/app/task/mode_worker.py:70)：完成用户恢复并提交本收尾协程暂存，记录取消或校验结果；返回后由 L3 解锁。

### app/task/legacy.py

- [async LegacyUserState.append\_push\_log](D:/Dev/AUTO-MAS/app/task/legacy.py:43)：[兼容旧专项] 旧通知素材追加接口；新代码将通知素材交通知业务层处理。
- [LegacyCallbacks.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/legacy.py:53)：[兼容旧专项] 仅初始化旧回调桥；新执行树不创建独立的运行态提交消费者。
- [LegacyCallbacks.submit](D:/Dev/AUTO-MAS/app/task/legacy.py:65)：[兼容旧专项] 旧回调排队接口；新执行树在产生暂存的同一协程中提交。
- [async LegacyCallbacks.\_consume](D:/Dev/AUTO-MAS/app/task/legacy.py:99)：[兼容旧专项] 仅消费旧回调队列；新执行树直接 await 下层并就地提交。
- [async LegacyCallbacks.drain](D:/Dev/AUTO-MAS/app/task/legacy.py:114)：[兼容旧专项] 仅等待旧回调桥结清；新执行树使用 TaskBase 的完整生命周期等待。
- [async LegacyCallbacks.close](D:/Dev/AUTO-MAS/app/task/legacy.py:125)：[兼容旧专项] 仅关闭旧回调桥；新背景资源使用 BackgroundTaskManager 的任务组生命周期。
- [maintenance\_requirements](D:/Dev/AUTO-MAS/app/task/legacy.py:133)：[兼容旧专项] 仅解析旧专项手动更新目标；新任务直接构造标准要求树。
- [\_LegacyExecution.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/legacy.py:166)：[兼容旧专项] 仅关联旧执行器；新执行树直接初始化 TaskBase 子类。
- [async \_LegacyExecution.main\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:171)：[兼容旧专项] 仅桥接旧 _run_main_task；新执行器直接实现 TaskBase.main_task。
- [async \_LegacyExecution.final\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:175)：[兼容旧专项] 仅桥接旧收尾和回调排空；新执行器直接实现 TaskBase.final_task。
- [async \_LegacyExecution.on\_crash](D:/Dev/AUTO-MAS/app/task/legacy.py:183)：[兼容旧专项] 仅桥接旧异常处理；新执行器直接实现 TaskBase.on_crash。
- [TaskExecuteBase.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/legacy.py:197)：[兼容旧专项] 仅装配旧专项执行桥与私有状态；新执行树使用 TaskBase 和显式上下文。
- [TaskExecuteBase.user\_state](D:/Dev/AUTO-MAS/app/task/legacy.py:208)：[兼容旧专项] 只读取旧专项私有素材；新代码不依赖此状态容器。
- [property TaskExecuteBase.execution\_mode](D:/Dev/AUTO-MAS/app/task/legacy.py:213)：[兼容旧专项] 将 ScriptView／隐藏更新转换成旧模式；新代码直接使用 TaskMode。
- [async TaskExecuteBase.send\_notice](D:/Dev/AUTO-MAS/app/task/legacy.py:220)：[兼容旧专项] 旧专项通知便捷入口；新代码使用所属业务层的既有通知能力。
- [property TaskExecuteBase.task](D:/Dev/AUTO-MAS/app/task/legacy.py:231)：[兼容旧专项] 旧底层 asyncio Task 别名；新执行树通过 TaskBase 生命周期操作。
- [property TaskExecuteBase.accomplish](D:/Dev/AUTO-MAS/app/task/legacy.py:236)：[兼容旧专项] 旧完成事件别名；新执行器使用自己的 TaskBase.accomplish。
- [property TaskExecuteBase.stopped\_manually](D:/Dev/AUTO-MAS/app/task/legacy.py:241)：[兼容旧专项] 旧停止标记读取；新执行树使用 TaskBase.cancelled。
- [setter TaskExecuteBase.stopped\_manually](D:/Dev/AUTO-MAS/app/task/legacy.py:250)：[兼容旧专项] 旧停止标记写入；新代码通过 TaskBase.stop() 请求中止。
- [async TaskExecuteBase.main\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:255)：[兼容旧专项] 旧专项主流程扩展点；新执行器直接实现 TaskBase.main_task。
- [async TaskExecuteBase.final\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:260)：[兼容旧专项] 旧专项收尾扩展点；新执行器直接实现 TaskBase.final_task。
- [async TaskExecuteBase.on\_crash](D:/Dev/AUTO-MAS/app/task/legacy.py:265)：[兼容旧专项] 旧专项异常扩展点；新执行器直接实现 TaskBase.on_crash。
- [async TaskExecuteBase.\_run\_main\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:269)：[兼容旧专项] 旧主流程转接名；新代码直接实现 TaskBase.main_task。
- [async TaskExecuteBase.\_finalize\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:273)：[兼容旧专项] 旧收尾转接名；新代码直接实现 TaskBase.final_task。
- [async TaskExecuteBase.\_execute\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:277)：[兼容旧专项] 旧运行入口，parent_tg 仅保留签名；新代码使用 TaskBase.run() 或父层 spawn()。
- [async TaskExecuteBase.\_run\_final\_task](D:/Dev/AUTO-MAS/app/task/legacy.py:281)：[兼容旧专项] 旧收尾等待入口；新代码通过 TaskBase.run()/stop() 等待完整生命周期。
- [async TaskExecuteBase.spawn](D:/Dev/AUTO-MAS/app/task/legacy.py:285)：[兼容旧专项] 旧子任务上下文转接；新层级通过 TaskBase.spawn() 派发并显式传入上下文。
- [TaskExecuteBase.execute](D:/Dev/AUTO-MAS/app/task/legacy.py:303)：[兼容旧专项] 旧启动方法名；新顶层执行器使用 TaskBase.start()。
- [async TaskExecuteBase.stop](D:/Dev/AUTO-MAS/app/task/legacy.py:307)：[兼容旧专项] 旧停止接口；新执行器直接使用 TaskBase.stop()。
- [TaskExecuteBase.\_on\_finalize\_cancel\_requested](D:/Dev/AUTO-MAS/app/task/legacy.py:313)：[兼容旧专项] 旧专项取消钩子；新执行树在所属层响应取消并由 final_task 收尾。
- [TaskExecuteBase.is\_log\_stalled](D:/Dev/AUTO-MAS/app/task/legacy.py:317)：[兼容旧专项] 旧专项日志停滞判断；新执行树的超时策略归相应业务层。

### app/models/task.py

- [async RuntimeEntry.set\_state](D:/Dev/AUTO-MAS/app/models/task.py:74)：需要时激活节点，按 info 字段赋值后 await commit。
- [property RuntimeEntry.task\_info](D:/Dev/AUTO-MAS/app/models/task.py:83)：[兼容旧专项] 旧任务根别名；新代码通过 root 或执行层显式上下文获取任务根。
- [property RuntimeEntry.name](D:/Dev/AUTO-MAS/app/models/task.py:88)：[兼容旧专项] 旧平铺名称；新代码读取具体节点的 info.name。
- [property RuntimeEntry.status](D:/Dev/AUTO-MAS/app/models/task.py:94)：[兼容旧专项] 旧平铺状态；新代码读取具体节点的 info.status。
- [property RuntimeEntry.result](D:/Dev/AUTO-MAS/app/models/task.py:100)：[兼容旧专项] 旧平铺结果；新代码读取具体节点的 info.result。
- [LogRecord.\_\_init\_\_](D:/Dev/AUTO-MAS/app/models/task.py:117)：[兼容旧专项] 旧平铺日志构造参数；新代码使用 info 分组载荷或 logs.add()。
- [async LogRecord.append\_content](D:/Dev/AUTO-MAS/app/models/task.py:133)：在短事务中复制追加日志行并提交整字段。
- [property LogRecord.content](D:/Dev/AUTO-MAS/app/models/task.py:138)：[兼容旧专项] 旧正文别名；新代码读取 info.content，追加使用 append_content()。
- [property LogRecord.phase](D:/Dev/AUTO-MAS/app/models/task.py:143)：[兼容旧专项] 旧阶段别名；新代码读取 info.phase。
- [TaskUserItem.\_\_init\_\_](D:/Dev/AUTO-MAS/app/models/task.py:162)：[兼容旧专项] 旧平铺用户构造及 Default 归一；新代码使用 info 载荷和 default。
- [TaskUserItem.iter\_history\_logs](D:/Dev/AUTO-MAS/app/models/task.py:180)：[兼容旧专项] 旧按本地时间读取日志的投影；新代码遍历 logs 并读取各记录的 info。
- [async TaskUserItem.add\_log\_record](D:/Dev/AUTO-MAS/app/models/task.py:186)：[兼容旧专项] 旧时间加记录的登记签名；新代码使用 logs.add(LogRecord, payload=...) 后提交。
- [TaskUserItem.compute\_result](D:/Dev/AUTO-MAS/app/models/task.py:197)：由日志轮次时间和状态计算虚拟用户结果。
- [property TaskUserItem.user\_id](D:/Dev/AUTO-MAS/app/models/task.py:206)：[兼容旧专项] 旧用户标识及 Default 大小写；新代码读取 info.user_id，使用 default。
- [property TaskUserItem.log\_record](D:/Dev/AUTO-MAS/app/models/task.py:211)：[兼容旧专项] 旧按时间索引的日志字典；新代码使用有序 logs 集合和运行 UUID。
- [TaskScriptItem.\_\_init\_\_](D:/Dev/AUTO-MAS/app/models/task.py:237)：[兼容旧专项] 旧平铺托管构造参数；新代码使用 info 分组载荷。
- [async TaskScriptItem.set\_current\_index](D:/Dev/AUTO-MAS/app/models/task.py:253)：[兼容旧专项] 旧整数位置转运行 UUID；新代码设置 current.index 为用户运行 UUID 后提交。
- [async TaskScriptItem.set\_users](D:/Dev/AUTO-MAS/app/models/task.py:258)：[兼容旧专项] 仅旧 manager 可重建用户列表；新执行链消费 L1 固定的 users 快照。
- [async TaskScriptItem.set\_log](D:/Dev/AUTO-MAS/app/models/task.py:281)：[兼容旧专项] 旧托管字符串日志写法；新代码写当前 LogRecord，流程日志按 current.log 提交。
- [async TaskScriptItem.append\_log](D:/Dev/AUTO-MAS/app/models/task.py:286)：[兼容旧专项] 旧托管字符串日志追加；新代码追加当前 LogRecord 的按行正文。
- [TaskScriptItem.compute\_result](D:/Dev/AUTO-MAS/app/models/task.py:291)：由各用户虚拟结果拼成托管虚拟结果。
- [property TaskScriptItem.script\_id](D:/Dev/AUTO-MAS/app/models/task.py:300)：[兼容旧专项] 旧平铺配置 ID；新代码读取 info.script_id，运行身份使用 uid。
- [property TaskScriptItem.script\_type](D:/Dev/AUTO-MAS/app/models/task.py:305)：[兼容旧专项] 旧平铺类型；新代码读取 info.script_type。
- [property TaskScriptItem.user\_list](D:/Dev/AUTO-MAS/app/models/task.py:310)：[兼容旧专项] 旧列表投影；新代码使用 users 有序集合。
- [property TaskScriptItem.current\_index](D:/Dev/AUTO-MAS/app/models/task.py:315)：[兼容旧专项] 旧整数进度位置；新代码使用 current.index 的用户运行 UUID。
- [property TaskScriptItem.log](D:/Dev/AUTO-MAS/app/models/task.py:323)：[兼容旧专项] 旧字符串日志别名；新代码根据当前来源读取日志记录或 current.log。
- [TaskItem.clear\_log\_cursor](D:/Dev/AUTO-MAS/app/models/task.py:355)：清理已发送日志的私有基线，保留完整运行树正文。
- [TaskItem.get\_log\_snapshot](D:/Dev/AUTO-MAS/app/models/task.py:360)：查询完整日志；只有当前来源与已发基线相符才提供可追加序号。
- [TaskItem.get\_update](D:/Dev/AUTO-MAS/app/models/task.py:381)：按 effective 配置分组和有序集合生成不含正文的元数据投影。
- [async TaskItem.set\_current\_index](D:/Dev/AUTO-MAS/app/models/task.py:428)：[兼容旧专项] 旧整数位置转运行 UUID；新代码设置 current.index 为托管运行 UUID 后提交。
- [property TaskItem.instance\_idx](D:/Dev/AUTO-MAS/app/models/task.py:434)：[兼容旧专项] 旧平铺启动参数；新代码从对应托管 info.params 或执行上下文读取。
- [TaskItem.is\_target\_user](D:/Dev/AUTO-MAS/app/models/task.py:445)：[兼容旧专项] 供旧 manager 再展开时筛选；新 L3 直接派发 L1 已选定的用户运行节点。
- [TaskItem.compute\_result](D:/Dev/AUTO-MAS/app/models/task.py:457)：直接遍历根的托管集合，动态汇总用户数量和托管结果。
- [TaskItem.current\_log\_source](D:/Dev/AUTO-MAS/app/models/task.py:475)：按运行指针找到当前用户最近日志，缺少用户日志时回退至当前托管流程日志。
- [TaskItem.compute\_log](D:/Dev/AUTO-MAS/app/models/task.py:485)：读取完整当前日志正文，不按行数或字符数截尾。
- [property TaskItem.mode](D:/Dev/AUTO-MAS/app/models/task.py:492)：[兼容旧专项] 旧平铺模式别名；新代码使用 info.mode 的 TaskMode 枚举。
- [property TaskItem.task\_id](D:/Dev/AUTO-MAS/app/models/task.py:497)：[兼容旧调用方] 旧字符串任务 ID 投影；新代码以 uid 保存身份，在接口边界转字符串。
- [property TaskItem.view\_only](D:/Dev/AUTO-MAS/app/models/task.py:502)：[兼容旧专项] 旧查看开关；新代码比较 info.mode 与 TaskMode.SCRIPT_VIEW。
- [property TaskItem.script\_list](D:/Dev/AUTO-MAS/app/models/task.py:507)：[兼容旧专项] 旧托管列表投影；新代码使用 scripts 有序集合。
- [property TaskItem.current\_index](D:/Dev/AUTO-MAS/app/models/task.py:512)：[兼容旧专项] 旧整数进度位置；新代码使用 current.index 的托管运行 UUID。
- [property TaskItem.script\_id](D:/Dev/AUTO-MAS/app/models/task.py:524)：[兼容旧调用方] 首个托管的旧平铺 ID；新代码按 scripts 各运行节点读取 info.script_id。
- [property TaskItem.current\_script\_id](D:/Dev/AUTO-MAS/app/models/task.py:529)：[兼容旧专项] 旧当前配置 ID 投影；新代码用 current.index 定位运行节点后读取 info。
- [property TaskItem.user\_id](D:/Dev/AUTO-MAS/app/models/task.py:538)：[兼容旧调用方] 单目标会话的旧平铺用户 ID；新代码从目标用户运行节点读取 info.user_id。
- [property TaskItem.notification\_state](D:/Dev/AUTO-MAS/app/models/task.py:549)：读取同一根私有持有的通知协调状态。
- [property TaskItem.is\_queue\_task](D:/Dev/AUTO-MAS/app/models/task.py:553)：[兼容旧专项] 仅供旧专项次数策略识别队列项；新框架在所属层处理准入和执行条件。
- [async \_info\_changed](D:/Dev/AUTO-MAS/app/models/task.py:570)：模型定义完成后直接声明的配置类订阅，按运行登记过滤、生成元数据并通过既有 Publisher 发送。
- [async \_log\_changed](D:/Dev/AUTO-MAS/app/models/task.py:609)：模型定义完成后直接声明的配置类订阅，按私有行基线计算增量或替换，实际发送后推进游标。
- [\_\_getattr\_\_](D:/Dev/AUTO-MAS/app/models/task.py:706)：[兼容旧专项] 仅保留 TaskExecuteBase 的旧导入路径；新执行器继承 app.task.lifecycle.TaskBase。

### app/task/manager_base.py

- [property UserRunSummary.uncompleted\_count](D:/Dev/AUTO-MAS/app/task/manager_base.py:40)：汇总失败和等待用户数。
- [ScriptManagerBase.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/manager_base.py:57)：初始化维护全跳过标志、开始时间及实际执行过的用户集合。
- [ScriptManagerBase.is\_user\_selected](D:/Dev/AUTO-MAS/app/task/manager_base.py:63)：[兼容旧专项] 旧 manager 重展开用户时筛选；新 L3 按固定运行节点在锁内复核准入。
- [overload ScriptManagerBase.selected\_user\_configs](D:/Dev/AUTO-MAS/app/task/manager_base.py:72)：[兼容旧专项] 旧 manager 读取当前配置并重筛用户；新执行树不重新展开 L1 用户清单。
- [overload ScriptManagerBase.selected\_user\_configs](D:/Dev/AUTO-MAS/app/task/manager_base.py:79)：[兼容旧专项] 旧 manager 读取当前配置并重筛用户；新执行树不重新展开 L1 用户清单。
- [ScriptManagerBase.selected\_user\_configs](D:/Dev/AUTO-MAS/app/task/manager_base.py:85)：[兼容旧专项] 旧 manager 读取当前配置并重筛用户；新执行树不重新展开 L1 用户清单。
- [ScriptManagerBase.build\_proxy\_user\_list](D:/Dev/AUTO-MAS/app/task/manager_base.py:100)：[兼容旧专项] 旧用户列表构造；新代码保留 L1 已生成的用户运行 UUID 与参数。
- [ScriptManagerBase.collect\_user\_results](D:/Dev/AUTO-MAS/app/task/manager_base.py:111)：按专项声明的成功状态把用户分为完成/失败/等待/跳过/其他。
- [property ScriptManagerBase.all\_users\_maintenance\_skipped](D:/Dev/AUTO-MAS/app/task/manager_base.py:130)：判断非空运行用户是否全因维护跳过。
- [property ScriptManagerBase.has\_proxy\_run](D:/Dev/AUTO-MAS/app/task/manager_base.py:137)：判断是否实际进入过自动代理用户执行。
- [ScriptManagerBase.record\_user\_run\_start](D:/Dev/AUTO-MAS/app/task/manager_base.py:140)：记录实际执行的原用户 ID。
- [async ScriptManagerBase.run\_user\_task](D:/Dev/AUTO-MAS/app/task/manager_base.py:143)：记用户已开始，await 旧适配 spawn，等待完整用户收尾。
- [ScriptManagerBase.build\_proxy\_report](D:/Dev/AUTO-MAS/app/task/manager_base.py:149)：按专项成功口径组装报告标题、时间、人数和已有结果文本。
- [async ScriptManagerBase.\_record\_user\_result](D:/Dev/AUTO-MAS/app/task/manager_base.py:167)：记录用户跳过/异常、日志、脚本文本及任务提示。
- [async ScriptManagerBase.skip\_user](D:/Dev/AUTO-MAS/app/task/manager_base.py:183)：设置维护标志后按跳过记录原因。
- [async ScriptManagerBase.notify\_user\_check\_failure](D:/Dev/AUTO-MAS/app/task/manager_base.py:189)：保留专项已判跳过状态，必要时标异常并发检查失败提示。
- [ScriptManagerBase.maintenance\_game](D:/Dev/AUTO-MAS/app/task/manager_base.py:195)：专项覆盖以声明用户所属游戏/区服公告对象，默认不查询。
- [async ScriptManagerBase.update\_game\_before\_run](D:/Dev/AUTO-MAS/app/task/manager_base.py:199)：专项覆盖的既有游戏更新流程入口。
- [async ScriptManagerBase.skip\_maintenance\_user](D:/Dev/AUTO-MAS/app/task/manager_base.py:202)：查公告维护并按维护跳过当前用户。
- [async ScriptManagerBase.check\_user\_before\_run](D:/Dev/AUTO-MAS/app/task/manager_base.py:214)：自动代理逐用户复查公告及需手动更新的失败，其他执行模式直接放行。
- [async ScriptManagerBase.notify\_maintenance](D:/Dev/AUTO-MAS/app/task/manager_base.py:235)：发送维护通知，通知失败只记警告。
- [async ScriptManagerBase.\_run\_main\_task](D:/Dev/AUTO-MAS/app/task/manager_base.py:243)：[兼容旧专项] 旧 manager 主流程转接；新执行层按 TaskBase.main_task 实现。

### app/task/base.py

- [\_running\_inflight\_detection](D:/Dev/AUTO-MAS/app/task/base.py:37)：回收完成的维护检测任务、取回异常；返回同事件循环内仍在途检测。
- [ScriptAutoProxyBase.\_on\_finalize\_cancel\_requested](D:/Dev/AUTO-MAS/app/task/base.py:75)：[兼容旧专项] 仅桥接旧专项取消；新执行器在所属层响应取消。
- [property ScriptAutoProxyBase.run\_timeout\_seconds](D:/Dev/AUTO-MAS/app/task/base.py:102)：将当前专项 HardTimeLimit 分钟转换为秒。
- [async ScriptAutoProxyBase.run\_user\_scripts\_before](D:/Dev/AUTO-MAS/app/task/base.py:105)：每用户一次执行前置脚本，并标记后置配对责任。
- [async ScriptAutoProxyBase.run\_user\_scripts\_after](D:/Dev/AUTO-MAS/app/task/base.py:115)：前置已经进入时只执行一次后置脚本，失败写提示而非重新执行用户。
- [async ScriptAutoProxyBase.skip\_on\_game\_maintenance](D:/Dev/AUTO-MAS/app/task/base.py:134)：调用单次画面检测，命中则记录维护跳过并通知。
- [async ScriptAutoProxyBase.\_detect\_game\_maintenance](D:/Dev/AUTO-MAS/app/task/base.py:158)：同脚本仅允许一个在途线程检测；15 秒超时放弃等待，实际线程继续持有句柄。
- [async ScriptAutoProxyBase.notify\_maintenance\_skip](D:/Dev/AUTO-MAS/app/task/base.py:186)：发布维护跳过通知，失败不改变跳过结论。
- [async ScriptAutoProxyBase.watch\_game\_maintenance](D:/Dev/AUTO-MAS/app/task/base.py:195)：后台周期检测并连续命中确认，写原因后置停止 Event；最终结论由专项主流程消费。
- [async ScriptAutoProxyBase.clear\_maintenance\_hit](D:/Dev/AUTO-MAS/app/task/base.py:241)：已成功时清除晚到维护标志，避免覆盖成功。
- [async ScriptAutoProxyBase.\_finalize\_task](D:/Dev/AUTO-MAS/app/task/base.py:246)：[兼容旧专项] 旧收尾方法名；新执行器在 TaskBase.final_task 完成所属资源恢复。
- [async ScriptAutoProxyBase.\_run\_main\_task](D:/Dev/AUTO-MAS/app/task/base.py:260)：[兼容旧专项] 旧主流程加超时保护；新 L4 的业务超时在执行器所属层实现。

### app/task/registration.py

- [build\_script\_capabilities](D:/Dev/AUTO-MAS/app/task/registration.py:65)：校验配置与运行类型登记唯一及完整性，创建只读工厂映射、配置 handler 和恢复解析器。

### app/task/builtin_registration.py

- [build\_builtin\_script\_capabilities](D:/Dev/AUTO-MAS/app/task/builtin_registration.py:31)：正式宿主显式导入内建专项声明，绑定本次服务依赖并构造三份能力索引。

### app/core/notify/lifecycle.py

- [async NotificationTaskBase.lock\_script\_config](D:/Dev/AUTO-MAS/app/core/notify/lifecycle.py:19)：[兼容旧专项] 仅旧 manager 取递归锁；新 L2 取托管非级联 X 锁，L3 取用户级联 X 锁。

### app/models/schema.py

- [TaskSelectionNode.validate\_indices](D:/Dev/AUTO-MAS/app/models/schema.py:48)：逐层要求 children 是按顺序从 0 连续递增的索引字典。

### app/models/config/queue.py

- [TimeSet.time\_visibility](D:/Dev/AUTO-MAS/app/models/config/queue.py:145)：有父队列时按 TimeEnabled 禁用整组，未挂父级时正常展示。
- [QueueConfig.next\_cycle\_run](D:/Dev/AUTO-MAS/app/models/config/queue.py:264)：由 LastRunAt 和 IntervalMinutes 计算虚拟下次触发，无上次时间返回 None。
- [QueueConfig.cycle\_visibility](D:/Dev/AUTO-MAS/app/models/config/queue.py:272)：按 CycleEnabled 决定整组可编辑或禁用。
- [async QueueConfig.reset\_cycle\_timer](D:/Dev/AUTO-MAS/app/models/config/queue.py:276)：Trigger 回调将 LastRunAt 设为本地现在，并在本协程提交。
- [QueueConfig.normalize\_payload](D:/Dev/AUTO-MAS/app/models/config/queue.py:284)：兼容旧 StartUpEnabled 布尔字段，缺少 StartUpMode 时转换为 Always/Never。
- [reject\_disabled\_time\_writes](D:/Dev/AUTO-MAS/app/models/config/queue.py:296)：订阅时间项字段与所属集合结构的运行时信号，禁用时抛错并由事务回滚；初始化加载不受限制。

### app/core/timer.py

- [\_local\_now](D:/Dev/AUTO-MAS/app/core/timer.py:50)：返回本机带时区现在，独立入口便于验证注入。
- [\_timed\_slots\_in\_window](D:/Dev/AUTO-MAS/app/core/timer.py:56)：按本地墙钟区间展开配置 HH:MM，回拨空区间不生成槽。
- [\_MainTimer.\_\_init\_\_](D:/Dev/AUTO-MAS/app/core/timer.py:85)：持有各定时后台句柄、启动仅一次标志、定时去重和检查游标。
- [async \_MainTimer.start](D:/Dev/AUTO-MAS/app/core/timer.py:103)：只启动一次启动队列检查异步任务及秒/小时/日历循环，按配置安排社区签到。
- [async \_MainTimer.stop](D:/Dev/AUTO-MAS/app/core/timer.py:130)：取消并等待组件持有的未完成后台任务，不修改队列触发开关。
- [async \_MainTimer.second\_task](D:/Dev/AUTO-MAS/app/core/timer.py:154)：先等启动检查，再每秒依次做队列触发和到期日历通知。
- [async \_MainTimer.\_run\_loop\_step](D:/Dev/AUTO-MAS/app/core/timer.py:234)：保护单次循环步骤，取消继续抛，同一连续故障去重记录。
- [async \_MainTimer.timed\_start](D:/Dev/AUTO-MAS/app/core/timer.py:259)：独立计算启动、定时、循环命中并分别提交单一原因的普通任务，只维护定时槽去重，不写队列运行时间。
- [\_MainTimer.\_due\_timed\_slots](D:/Dev/AUTO-MAS/app/core/timer.py:333)：按时间项开关/星期、去重、持久化水位和 10 分钟补跑窗返回到期槽。

### app/api/scripts/operations.py

- [async start\_operation](D:/Dev/AUTO-MAS/app/api/scripts/operations.py:23)：独立维护 HTTP 入口；调用 start_maintenance，参数/状态冲突分别转业务 400/409。

### `app/core/__init__.py`

- [\_\_getattr\_\_](D:/Dev/AUTO-MAS/app/core/__init__.py:73)：按显式导出表延迟导入真实组件并缓存到 globals；静态提示来自 TYPE_CHECKING 分支。

### app/core/ws/publisher.py

- [async \_WSPublisher.send](D:/Dev/AUTO-MAS/app/core/ws/publisher.py:40)：将 Pydantic/字典数据变为 WS 信封交主连接发送；未连接返回 False，不持久排队。

### app/core/notify/commands.py

- [async execute\_notification\_command](D:/Dev/AUTO-MAS/app/core/notify/commands.py:36)：把通知渠道名称解析为唯一托管或队列，构造 AutoProxy 要求树直接调用 L1。

### app/task/history_core.py

- [async save\_user\_history](D:/Dev/AUTO-MAS/app/task/history_core.py:40)：依原顺序归档专项条目、追加末条附件，并最终释放采集副本。
- [TaskHistorySession.\_\_init\_\_](D:/Dev/AUTO-MAS/app/task/history_core.py:77)：持有根引用、类型化采集句柄、受管临时文件和运行 UUID 去重集合。
- [TaskHistorySession.\_capture\_group](D:/Dev/AUTO-MAS/app/task/history_core.py:86)：按任务根申请失败附件采集组；文件所有权独立保存到历史会话。
- [TaskHistorySession.observe](D:/Dev/AUTO-MAS/app/task/history_core.py:91)：确认仍为托管异常且没有用户采集归属时请求诊断。
- [TaskHistorySession.begin\_user\_history\_capture](D:/Dev/AUTO-MAS/app/task/history_core.py:105)：以托管/用户运行 UUID 去重，异步采集失败副本。
- [async TaskHistorySession.save\_user\_history](D:/Dev/AUTO-MAS/app/task/history_core.py:136)：装配 History.record、附件与错误反馈，再复用公共归档管线。
- [async TaskHistorySession.\_report\_history\_save\_failure](D:/Dev/AUTO-MAS/app/task/history_core.py:163)：发送归档告警，不改执行结论。
- [async TaskHistorySession.collect\_user\_history\_attachments](D:/Dev/AUTO-MAS/app/task/history_core.py:170)：等待对应用户采集，只为有效失败返回附件。
- [async TaskHistorySession.\_discard\_history\_capture\_file](D:/Dev/AUTO-MAS/app/task/history_core.py:206)：委托 OBS 服务执行受管临时文件清理。
- [async TaskHistorySession.discard\_user\_history\_capture](D:/Dev/AUTO-MAS/app/task/history_core.py:211)：归档后丢弃该运行用户的采集副本。
- [async TaskHistorySession.close](D:/Dev/AUTO-MAS/app/task/history_core.py:221)：注销采集组并等待取消收尾，再清理所有受管副本；结果过期不丢失文件归属。
- [TaskHistorySession.\_request\_unassigned\_replay](D:/Dev/AUTO-MAS/app/task/history_core.py:231)：使用托管运行 UUID 去重诊断原件，不伪造用户历史。

### app/services/common/obs_replay.py

- [async ObsReplayService.discard\_temporary](D:/Dev/AUTO-MAS/app/services/common/obs_replay.py:338)：校验受管目录与链接边界后删除临时副本，保留 OBS 原件。

### app/services/common/telemetry.py

- [\_publish\_script\_observation](D:/Dev/AUTO-MAS/app/services/common/telemetry.py:548)：申请 32 并发的背景任务组，以完成事件和发送标志保证 started/finished 顺序，不缓存发送结果。
- [task\_trigger\_category](D:/Dev/AUTO-MAS/app/services/common/telemetry.py:582)：仅在统计消费边界将 TaskTriggerReason 归入既有来源分类。
- [observe\_script\_run](D:/Dev/AUTO-MAS/app/services/common/telemetry.py:596)：上下文观察一次托管运行，统一原有计数和 started/finished 本地消息。

### app/core/background_tasks.py

- [TaskOutcome.unwrap](D:/Dev/AUTO-MAS/app/core/background_tasks.py:31)：提取成功值（可为 None）；失败、取消或执行超时则抛出对应异常。
- [BackgroundTaskHandle.\_\_init\_\_](D:/Dev/AUTO-MAS/app/core/background_tasks.py:56)：保存类型化组归属、任务 UUID 和完成事件，不暴露 asyncio.Task。
- [BackgroundTaskHandle.done](D:/Dev/AUTO-MAS/app/core/background_tasks.py:61)：查询执行是否真正退出，不读取或提取结果。
- [BackgroundTaskHandle.cancel](D:/Dev/AUTO-MAS/app/core/background_tasks.py:64)：向仍在执行的任务请求取消，不提前释放执行容量。
- [async BackgroundTaskHandle.wait\_done](D:/Dev/AUTO-MAS/app/core/background_tasks.py:67)：有限等待完成事件；等待者取消与超时不取消背景执行。
- [async BackgroundTaskHandle.wait\_take](D:/Dev/AUTO-MAS/app/core/background_tasks.py:76)：委托所属组等待并一次性提取结果。
- [BackgroundTaskGroup.\_\_init\_\_](D:/Dev/AUTO-MAS/app/core/background_tasks.py:93)：校验容量与期限策略，建立当前组的执行和结果记录集合。
- [BackgroundTaskGroup.spawn](D:/Dev/AUTO-MAS/app/core/background_tasks.py:120)：先检查关闭、事件循环与两种容量，再创建执行工厂的任务；可选择不保留结果。
- [BackgroundTaskGroup.query](D:/Dev/AUTO-MAS/app/core/background_tasks.py:154)：读取任务元信息；不消费结果、不续期，已清理时返回 None。
- [BackgroundTaskGroup.try\_take](D:/Dev/AUTO-MAS/app/core/background_tasks.py:166)：未完成返回 PENDING；已完成则原子移除并返回 TaskOutcome，不存在抛 KeyError。
- [async BackgroundTaskGroup.wait\_take](D:/Dev/AUTO-MAS/app/core/background_tasks.py:180)：等待后调用 try_take；多个提取者只有一个成功，等待超时不影响任务。
- [async BackgroundTaskGroup.drain](D:/Dev/AUTO-MAS/app/core/background_tasks.py:193)：在共同期限内等待组内执行退出，覆盖等待期间新接纳的任务；不消费、不取消。
- [BackgroundTaskGroup.\_check\_owner](D:/Dev/AUTO-MAS/app/core/background_tasks.py:208)：验证句柄属于当前组，防止相同名称的新组混用旧句柄。
- [BackgroundTaskGroup.\_cancel](D:/Dev/AUTO-MAS/app/core/background_tasks.py:212)：请求取消未退出的执行，已有取消请求时避免再次打断异步收尾。
- [BackgroundTaskGroup.\_timeout](D:/Dev/AUTO-MAS/app/core/background_tasks.py:217)：记录执行超时并请求取消；容量仍占用到执行真正退出。
- [BackgroundTaskGroup.\_finish](D:/Dev/AUTO-MAS/app/core/background_tasks.py:223)：读取唯一执行结果，释放运行容量；按策略保留并启动 TTL，或直接丢弃。
- [BackgroundTaskGroup.\_discard](D:/Dev/AUTO-MAS/app/core/background_tasks.py:251)：释放结果记录与到期计时器，记录未提取的异常；不清理业务文件。
- [BackgroundTaskGroup.\_close](D:/Dev/AUTO-MAS/app/core/background_tasks.py:267)：封闭提交、取消执行、清理已完成记录；最后一个执行退出后移除组。
- [BackgroundTaskRegistry.\_\_init\_\_](D:/Dev/AUTO-MAS/app/core/background_tasks.py:281)：持有名称唯一的应用级任务组和关闭屏障。
- [BackgroundTaskRegistry.register\_group](D:/Dev/AUTO-MAS/app/core/background_tasks.py:285)：按显式策略申请任务组；重复名称或管理器已关闭时报错。
- [BackgroundTaskRegistry.get\_group](D:/Dev/AUTO-MAS/app/core/background_tasks.py:310)：按名称查找现存组，不隐式申请。
- [async BackgroundTaskRegistry.unregister\_group](D:/Dev/AUTO-MAS/app/core/background_tasks.py:313)：验证归属、封闭组并取消等待；超时返回 False，组保持关闭及持有状态。
- [async BackgroundTaskRegistry.shutdown](D:/Dev/AUTO-MAS/app/core/background_tasks.py:322)：先封闭全部组，再以同一期限等待退出；超时不丢失引用。
- [BackgroundTaskRegistry.\_remove](D:/Dev/AUTO-MAS/app/core/background_tasks.py:337)：按对象身份移除真正退出的组，允许之后重新申请同名组。

### app/core/notify/tasks.py

- [NotificationTasks.group](D:/Dev/AUTO-MAS/app/core/notify/tasks.py:49)：申请当前通知服务的任务投递组，完成即释放结果。
- [NotificationTasks.community\_group](D:/Dev/AUTO-MAS/app/core/notify/tasks.py:56)：申请社区通知组，允许短暂等待结果及迟到投递。
- [async NotificationTasks.close](D:/Dev/AUTO-MAS/app/core/notify/tasks.py:62)：注销已申请的通知组，等执行退出后才能释放渠道资源。
- [NotificationTasks.spawn\_notification](D:/Dev/AUTO-MAS/app/core/notify/tasks.py:69)：接受协程工厂并向通知组提交，不自行维护在途任务集合。
- [NotificationTasks.task\_notification\_batch](D:/Dev/AUTO-MAS/app/core/notify/tasks.py:125)：为当前专项保存通知批次和 L2 提供的报告协调器，子账号与收尾继承同一上下文。
- [NotificationTasks.current\_task\_report\_coordinator](D:/Dev/AUTO-MAS/app/core/notify/tasks.py:148)：读取当前批次的协调器，退出批次后不再持有该引用。
- [async NotificationTasks.drain\_notifications](D:/Dev/AUTO-MAS/app/core/notify/tasks.py:172)：委托任务组有限等待投递；超时不取消发送。

### app/core/notify/task_report.py

- [prepare\_task\_report](D:/Dev/AUTO-MAS/app/core/notify/task_report.py:137)：复用当前任务批次的报告协调器；任务 ID 不匹配或独立调用时按原策略单独装配。

## 10. 前端任务链的方法职责

本节按调度职责列出前端方法；标签页拖拽、滚动、音效、表单布局等纯界面辅助不纳入公共执行框架方法清单。

### 10.1 页面选择与创建/停止请求

在 [useTaskOptions.ts](D:/Dev/AUTO-MAS/frontend/src/composables/useTaskOptions.ts)：

- `fetchTaskTargets()`：通过现存队列和托管配置接口读取带显式类型的候选，Vue Query 共享在途查询；不按文案判断类型、不隐藏已锁定的目标。
- `configuredTaskRequest()`：快捷入口按真实配置类型生成默认要求树。
- `fetchTaskScope()`：按队列项 UUID 和顺序展开本次选择，重复托管共享用户名单读取但选择互相独立；禁用和天数不足的用户仍保留。
- `configSessionRequest()`：标记为兼容旧专项，由目标 UUID 反查托管归属；新入口直接提供规范要求树。

在 [taskSelection.ts](D:/Dev/AUTO-MAS/frontend/src/composables/taskSelection.ts)：

- `indexed()`：把有序节点数组转为连续索引字典。
- `targetRequest()`：构造整队列、直接托管或唯一 default 配置目标的要求树。
- `selectedScopeUsers()`：按 all／explicit／none 选择意图读取草稿用户。
- `scopeRequest()`：按原配置顺序编码标准 mode/tasks 请求；动态全选用空 children，显式全选仍列出原选中的用户；清空或失效选择拒绝启动。
- `reconcileScope()`：刷新展示配置并保留队列项级选择；新增对象不扩大显式范围，删除或替换的已选对象显示失效。
- `persistScope()`：只持久化会话内选择意图，不复制配置展示、日志或脚本参数。

在 [useTaskApi.ts](D:/Dev/AUTO-MAS/frontend/src/composables/useTaskApi.ts)：

- `taskRequestError()`：优先从生成客户端 ApiError 的 body 提取后端 message，其他错误转 Error。
- `nativeScriptType()`：从运行状态或目标标识查询有限统计类型。
- `requestTaskStart()`：接收标准要求树并调用生成创建客户端；统一记录任务请求、配置会话、范围恢复的受理统计，返回原始响应。
- `requestScriptConfigStart()`：由查看开关选择 ScriptView 或 ScriptConfig，仍走统一请求。
- `requestUserUpdateStart()`：包装专项用户更新入口的配置操作统计。
- `requestMaintenanceStart()`：请求独立专项维护接口；旧 Update 统计分类不改变公开模式集合。
- `stopNativeConfig()`：停止配置会话并记录请求受理；不从 HTTP 成功推断原生配置已保存。
- `useTaskApi()`：返回面向页面的 startTask/stopTask。
- `useTaskApi.startTask()`：统一转换请求错误，业务 code 不成功或没有 taskId 则抛错。
- `useTaskApi.stopTask()`：调用生成停止客户端，检查业务 code，记录一次停止请求结果。

### 10.2 应用级运行数据、订阅与恢复

[useTaskRuntimeState.ts](D:/Dev/AUTO-MAS/frontend/src/composables/useTaskRuntimeState.ts) 是运行数据的唯一所有者。每个运行 UUID 对应一份任务信息、日志、序号和终态，页面或标签不再复制这些数据。

- `bootstrapTaskRuntimeState()` / `disposeTaskRuntimeState()`：在应用生命周期内订阅任务创建、重连事件并定期清理未绑定的已完成缓存；关闭时释放订阅、定时器和缓存。
- `ensureTaskSubscriptions()` / `releaseTaskSubscriptions()`：按运行 UUID 统一管理信息、日志、通知和完成订阅。
- `handleTaskCreated()`：合并创建元数据，建立本轮订阅，广播低频生命周期事件。
- `handleLogUpdated()`：直接更新该运行对象的日志字段；日志不触发整张运行表替换或生命周期广播。漏包时去重拉取快照。
- `handleTaskCompleted()`：记录服务端终态、结果和任务树，保留已收日志，释放本轮订阅。
- `loadTaskRuntimeSnapshot()` / `stateFromSnapshot()`：首次进入、重连及漏包时对账。元数据事件与请求冲突时重试；日志按序号独立比较，较旧快照不能覆盖请求期间的新日志。已不在运行列表中的任务只标记为结束，不伪造结果。
- `registerAcceptedTask()`：HTTP 受理仅在尚无该运行对象时补建订阅；早于 HTTP 返回的日志或终态原样保留。
- `reconcileStoppedTask()`：停止后先等待 1500ms 接收正式完成事件，仍无终态时查询快照确认。
- `retainTaskRuntime()` / `releaseTaskRuntime()` / `pruneCompletedStates()`：标签绑定期间保留完成结果；解除绑定后沿用五分钟缓存清理。
- `onTaskRuntimeEvent()`、`getTaskRuntimeState()`、`getTaskRuntimeStates()`、`useTaskRuntimeState()`：供应用反馈、统计和界面按需读取同一份数据。

[taskLogBuffer.ts](D:/Dev/AUTO-MAS/frontend/src/composables/taskLogBuffer.ts) 负责旧日志协议的追加、替换、序号连续性与首行号维护。`applyTaskLogUpdate()` 在缺少基线或序号跳跃时返回 `resync`；保留既有前端 200000 字符尾部缓存限制，此限制不改变后端查询的完整任务信息。

[taskTreeProjection.ts](D:/Dev/AUTO-MAS/frontend/src/composables/taskTreeProjection.ts) 的 `projectTaskTree()` 按配置树 `order` 读取 `data`，生成只读托管／用户展示投影。节点 ID 使用运行 UUID，`config_id` 使用原配置 UUID。

[useTaskFeedback.ts](D:/Dev/AUTO-MAS/frontend/src/composables/useTaskFeedback.ts) 单独承接应用级任务通知、完成提示、音效及专项反馈弹窗；通过 `bootstrapTaskFeedback()` / `disposeTaskFeedback()` 订阅运行生命周期，不依赖调度页是否打开。失败判定继续复用 [taskFailures.ts](D:/Dev/AUTO-MAS/frontend/src/utils/taskFailures.ts) 的 `resolveTaskCompletionFeedback()` 等函数；任务遥测继续由原有 API／运行生命周期入口负责，日志不产生生命周期统计。

[useScriptConfigLock.ts](D:/Dev/AUTO-MAS/frontend/src/composables/useScriptConfigLock.ts) 直接读取资源锁查询接口，按目标共享 Vue Query 缓存并每秒刷新；锁权限不从任务展示状态推断。

### 10.3 标签草稿与调度页

[stores/scheduler.ts](D:/Dev/AUTO-MAS/frontend/src/stores/scheduler.ts) 只保存标签、选择草稿、活动页和运行 UUID 绑定。`panels` 从公共运行对象派生名称、模式和状态，不依赖日志正文。

- `addTab()` / `removeTab()`：管理标签和活动页。
- `bindRun()`：按确切运行 UUID 合并 WS 先建的标签，仅调整绑定，不迁移、重置日志。
- `trackStartedTask()`：供主页、托盘、桌宠等入口跟踪已启动任务，复用合适的空闲标签；不同运行 UUID 始终是不同运行。
- `bootstrap()` / `shutdown()`：应用级监听创建与快照事件，恢复运行标签并保存草稿；不订阅日志。
- `persist()`：结构变更、绑定和活动页立即写入 sessionStorage；草稿修改合并延迟 800ms 保存。持久化内容不含日志、运行树副本或终态。
- UUID 绑定变化时申请／释放运行缓存保留。刷新后通过快照恢复仍在运行的任务；已结束且仅有本地绑定的标签显示未知结果，不伪造日志和结果。

[useSchedulerLogic.ts](D:/Dev/AUTO-MAS/frontend/src/views/scheduler/useSchedulerLogic.ts) 仅处理页面交互：

- `loadTaskOptions()` / `loadTaskScope()`：加载配置候选及当前运行范围，协调已有草稿并拒绝过期异步响应。
- `handleTaskSelectionChange()`：切换目标并加载对应草稿。
- `startTask()`：校验草稿、构造要求树、调用公共 API、绑定返回的运行 UUID；不再清空日志或重新订阅。
- `stopTask()`：调用公共停止入口及既有音效；完成确认由公共运行模块处理。
- `removeSchedulerTab()` / `removeAllNonRunningTabs()`：保持原有运行保护和确认弹窗。
- `getPowerState()` / `onPowerActionChange()`：读取、修改现有完成后电源操作。
- `initialize()` / `setSchedulerViewActive()` / `cleanup()`：维护页面配置刷新及电源订阅；页面离开不销毁应用级运行数据和任务订阅。

[SchedulerRunScope.vue](D:/Dev/AUTO-MAS/frontend/src/views/scheduler/SchedulerRunScope.vue) 继续承接启动前的大面积运行范围弹窗；运行时隐藏。目标选择与要求树生成仍复用现有配置 API 和 `taskSelection`，本轮未新增后端接口。

[SchedulerRunPanels.vue](D:/Dev/AUTO-MAS/frontend/src/views/scheduler/SchedulerRunPanels.vue) 保留原总览／日志分栏布局，按运行对象派生展示内容。[TaskOverviewPanel.vue](D:/Dev/AUTO-MAS/frontend/src/views/scheduler/TaskOverviewPanel.vue) 直接接收只读任务信息 prop，不再通过 ref 回放或维护第二份快照。[SchedulerLogPanel.vue](D:/Dev/AUTO-MAS/frontend/src/views/scheduler/SchedulerLogPanel.vue) 只维护供编辑器显示的文本：首条日志、切换运行、恢复可见及完成结果立即刷新，连续输出合并为 200ms 更新；隐藏标签或离开页面时停止渲染，公共运行模块仍持续收集日志。既有 120000 字符渲染限制、行号、跟随、主题和操作按钮保持原行为。编辑器作为异步组件先等待既有 configureLocalMonaco() 完成，避免刷新恢复日志时抢在空闲预热之前初始化并退回 CDN。

应用组合根 [realtimeResidents.ts](D:/Dev/AUTO-MAS/frontend/src/bootstrap/realtimeResidents.ts) 分别注册运行数据、反馈和标签草稿常驻生命周期。App、主页、托盘及桌宠直接访问 store，不再导入调度页控制器；关闭窗口的运行判断读取公共运行状态。

## 11. 对照检查入口

- [test\_task\_tree\_dispatch.py](D:/Dev/AUTO-MAS/tests/core/test_task_tree_dispatch.py)：要求树、参数传递、重复队列项、创建通知顺序、删除后快照、热态配置、插件锁范围、提交失败解锁、停止全部创建屏障。
- [test\_maintenance\_cycle\_review.py](D:/Dev/AUTO-MAS/tests/core/test_maintenance_cycle_review.py)：三种触发独立派发、运行中继续提交、失败不推进时间、本地日期、启动一次、虚拟下一次/重置、模块禁用、星期跳过和重置竞争。
- [test\_task\_state\_changes.py](D:/Dev/AUTO-MAS/tests/core/test_task_state_changes.py)、[test\_task\_log\_updates.py](D:/Dev/AUTO-MAS/tests/core/test_task_log_updates.py)：运行状态和日志变化。
- [test\_ws\_message\_contract.py](D:/Dev/AUTO-MAS/tests/api/test_ws_message_contract.py)：WS 公共契约覆盖。
- [useTaskRuntimeState.test.ts](D:/Dev/AUTO-MAS/frontend/src/composables/useTaskRuntimeState.test.ts)、[taskSelection.test.ts](D:/Dev/AUTO-MAS/frontend/src/composables/taskSelection.test.ts)：前端树转换、运行身份、快照/实时更新和锁状态。

以上是检查定位，不声称每条异常路径都已做真实游戏验证。后续类型修复记录见第 12 节；自动化回归结果不能代替具体专项的真实设备中止/恢复验证。

## 12. 类型问题的分类与本次处理

### 12.1 应当修复的调度框架问题

- **要求树键类型不兼容**：Mapping 的键是不可变型参数，Mapping[int | str, ...] 不能准确接收 dict[int, TaskSelectionNode]。TaskRequirements 改为整数键映射或字符串键映射；运行校验仍只由原有连续索引规则决定。
- **建树中间规格推断错误**：该阶段曾用 UserSpec、ScriptSpec、QueueSpec 明确中间结构；第 18 节已删除中间规格，改为直接创建运行节点，相关类型问题随之消除。
- **L1/L2 宿主与工厂缺少契约**：补全 TaskManager 和 ScriptExpander 的签名，PluginExpander 明确输入/输出，资源与 manager 句柄明确可选类型。
- **公共执行 mixin 依赖未声明**：该 mixin 已移除：附加脚本归 L2，专项观察归 telemetry；统计结果和社区触发来源使用已有有限取值。
- **登记表和分支集合推断过宽**：CLASS_BOOK 明确为脚本配置类映射；通知命令的目标集合声明为脚本集合或队列集合，避免同一变量被错误推断为只能承接其中一种。
- **旧公共选择函数的重载不一致**：selected_user_configs 的实现返回声明改为协变的 Sequence，两个公开重载仍精确返回 list；实际构造与返回的仍是原列表，不改变调用行为。
- **L3 把可能不存在的根继续向下传**：构造时拒绝没有根的托管运行节点，后续 TaskContext 和 worker 始终持有非空根。
- **L3 工厂被推断为返回 None**：build_worker 标注 ModeWorker，并保持抽象方法；默认体明确抛 NotImplementedError，不提供假成功实现。
- **L3/L4 解析与锁范围类型不明**：解析函数返回当前配置类型或 None，用户查找用只读协议；持票收尾处明确配置必然已取得的成对不变量，finally 解锁顺序不变。
- **停止状态不再依赖宿主属性**：L2 在 TaskItem 中记录 cancelled；插件遵守自身 TaskBase 生命周期，旧专项在兼容层读取任务树终态，回放采集由历史会话独立控制。
- **配置变更接收者确认归属**：调度器从字段或集合事件取得根，确认 TaskItem 类型并查运行索引后才推送；模型不再声明宿主回调接口。
- **虚拟 bool 的声明可为空**：当时 is_cycle 的公开属性按已激活虚拟字段的保证收窄为 bool；第 30 节已将该派生字段及属性一并移除。
- **传输层混淆原始字典与模型实例**：快照、完成消息和电源信号在边界用 model_validate 接收原始数据，保留 Pydantic 原有值校验，避免把合法字典输入硬冒充模型对象。
- **可选队列引用未判空**：完成后动作先确认原队列 ID、弱引用和当前对象有效再访问，不假定所有运行节点都来自真实队列。
- **静态导入意外成为运行时依赖**：新增跨模块注解使用 TYPE_CHECKING 和延迟注解，避免为类型提示提前装配组件；导入和回归已验证。

### 12.2 临时兼容边界：保留并逐行抑制

位置：[RuntimeEntry](D:/Dev/AUTO-MAS/app/models/task.py) 的 name、status、result 三个平铺属性。

这些属性为旧专项调用形状保留，部分新编排目前也复用它们。底层 ConfigEntry 不固定名为 info 的分组，更不保证日志分组具有 name/result；每个具体运行节点才声明自己的分组。为了保留旧读取方式，不给通用配置基类伪造这些字段，只在三个返回表达式上分别使用 mypy 的 attr-defined 和 Pyright 的 reportAttributeAccessIssue 局部抑制，旁边写明原因及旧兼容移除时的清理位置。

旧 LogRecord/TaskUserItem/TaskScriptItem 的平铺构造参数、TaskExecuteBase 的动态用户任务衔接继续保留；asdict 后端展示副本已移除。RuntimeEntry 的静态构造签名镜像 ConfigEntry 已支持的开放字段传入，不在 Pydantic 模型中新增虚假的字段。没有对 legacy 文件或整个 task 目录关闭类型检查。

### 12.3 动态配置投影的工具限制：单独标明

位置：[TaskGetOut.data](D:/Dev/AUTO-MAS/app/api/dispatch.py)。TaskTreeData 是 config_contract 在运行时生成的 Pydantic 类；Pyright 不允许把普通工厂调用的结果直接当注解类型。

此处不属于旧专项兼容，也不是缺少运行时校验。保留真实动态投影以保证 OpenAPI 和配置声明同源，只在这一条注解上使用 Pyright 的 reportInvalidTypeForm 和 mypy 的 valid-type 局部抑制并写明原因；不重写一份手工树模型，不用 Any 替换整个 API 契约，也不把该规则全局关闭。

### 12.4 验证范围和命令

Pyright 使用本机已缓存的 1.1.414，基础诊断覆盖 21 个文件：task_manager 包、任务模型、dispatch、timer、L2/L3/L4、context、lifecycle、legacy、旧公共 manager/base、通知启动入口、专项维护入口、注册及宿主登记。该范围没有包含所有专项内部实现或整个 app；不据此声称全仓类型检查清零。

```powershell
npx --offline pyright --pythonpath .venv/Scripts/python.exe app/core/task_manager app/task/lifecycle.py app/task/context.py app/task/script_expander.py app/task/user_expander.py app/task/mode_worker.py app/task/legacy.py app/task/manager_base.py app/task/base.py app/models/task.py app/api/dispatch.py app/core/timer.py app/core/notify/commands.py app/api/scripts/operations.py app/task/registration.py app/task/builtin_registration.py

uv run --no-sync mypy --follow-imports=silent --ignore-missing-imports --check-untyped-defs --warn-unused-ignores --show-error-codes app/core/task_manager app/task/lifecycle.py app/task/context.py app/task/script_expander.py app/task/user_expander.py app/task/mode_worker.py app/task/legacy.py app/task/manager_base.py app/task/base.py app/models/task.py app/api/dispatch.py app/core/timer.py app/core/notify/commands.py app/api/scripts/operations.py app/task/registration.py app/task/builtin_registration.py
```

类型整理阶段只检查新调度调用关系时也额外看过 desktop_guard；它的虚拟显示能力内部已有五条诊断，不是本次调度签名改动引入，未扩大本次修改范围。前述“调度范围清零”不含这五条。

本次没有新增用户操作、统计维度或外部行为，因此沿用原有遥测边界，不新增事件。

类型整理阶段验证结果：同一调度范围 Pyright 与 mypy 均为 21 个文件、0 诊断；核心/契约/维护定向回归 74 项通过；全量 pytest 1222 项通过、3 项跳过、29 项 subtest 通过。公开 OpenAPI 与修复前完全一致，因此不重新生成前端客户端；未进行真实游戏或设备验证。

## 13. 队列附加脚本的简化（历史阶段，当前已移除，见第 25 节）

L2 的线性队列流程各调用一次前置和后置脚本，以调用位置保证顺序。删除 `_queue_before_script_ran`、`_queue_after_script_ran` 和 `_queue_script_task`，也删除只是重复投影 cancelled 的 is_closing/stopped_manually 两个 L2 属性。

`_run_queue_extra_script(queue_id, before=...)` 只做业务选择和提示：重新查队列 → 读取对应开关及路径 → 发布开始提示 → 直接 await execute_script_task → 发布结果提示。开关/路径通过明确字段读取，不再传入动态字段名。

脚本类型识别、进程等待、超时和取消时清理继续复用现有 CustomScriptExecutor/ProcessRunner。附加脚本不再 create_task，不持有第二个取消句柄，不捕获并吞掉后置阶段的 CancelledError。TaskBase 仍使用来源生命周期实现，执行库返回后才进入任务最终收尾。

旧专项的用户前后脚本配对、timer 的进程启动一次标记保持原有职责；未新增通用 run_once 包装或脚本任务类。任务和专项运行统计继续由原观察位置负责。

回归覆盖：多队列项被同一组前后脚本包围且各执行一次；停止前置/后置脚本时，等待执行库清理完成后才发布唯一取消终态并移除任务。后置取消的用例在简化前复现“队列被标为完成”，简化后按取消处理。

简化后的定向回归 85 项通过，覆盖要求树、调度与状态、WS 契约、旧专项前后脚本和基础进程超时/取消清理；同一 21 个调度文件的 Pyright 与 mypy 均无诊断。两个实现文件合计净减 52 行。

## 14. 分支能力整合后的边界

- 删除没有消费者的 `script_user_scope`、`TaskContext.task_info` 和 `_run_script` 的 `queue` 参数；要求参数继续按层隔离复制。
- 普通/维护共用 `_launch` 和同一运行索引，复用创建屏障、查询、停止和 ended 清理。`maintenance_requirements` 留在旧专项适配中；维护仍不创建普通调度面板，也不进入插件模式。
- 删除 `_replay_runs`；托管和用户运行 UUID 直接标识每次采集归属。`TaskHistorySession` 复用已有归档管线，拥有待诊断变化、去重与采集句柄；OBS 服务统一校验并清理受管副本。通用任务模型不再缓存回放专用状态事件。
- 快照和 `task.completed` 只发送完整 `task` 树，移除后端 `asdict`、`task_info` 和对应旧传输模型。前端统一 `projectTaskTree`；面板内部 `TaskCompletionView` 的平铺数据不再冒充 WS 契约。OpenAPI 客户端已由生成器更新。
- 删除 `TaskOperations` mixin；队列附加脚本直接归 L2，专项统计归既有 telemetry。`BackgroundTaskManager` 通过独立任务组持有、限流和回收旁路任务；保留 32 个在途上限及 `started` 成功后才允许 `finished` 的顺序。

本阶段保留取消、热态配置、业务锁、旧 manager 执行与恢复、统计事件名及有限维度的职责。这里新增的是实际有状态的历史会话。后续第 17 节已删除本阶段仍存在的独立资源预约。

整合验证：后端全量 pytest 1228 项通过、3 项跳过、29 项 subtest 通过；前端 151 项测试通过。OpenAPI 已重新生成，当前任务快照的 `task` 为必填且不再带 `task_info`。

最终整合检查：Pyright 与 mypy 覆盖 25 个相关文件且均零诊断；renderer/Electron 类型检查、lint、format、前端构建及 3 项隔离浏览器流程通过。浏览器已有组件属性警告与整合前日志一致，未进行真实游戏或设备运行。

## 15. 删除 TaskInfo 宿主兼容层

`app/core/task_manager/state.py` 和 `TaskInfo` 子类已删除。L1 直接构建 `TaskItem`，L2/L3/L4、旧 manager、查询、快照和完成消息持有同一运行树。没有把原宿主接口复制进 `TaskItem`，也没有改动来源 `TaskBase`。

当前职责分配：

- `TaskItem` 及子节点只提供运行信息、配置节点操作和旧专项必要的平铺属性；删除宿主方法占位、发布标记、旧执行模式映射和回放取消属性。
- `_TaskManager` 订阅运行节点与集合的类级配置变更信号。以根 UUID 查询运行索引，完整建树并登记前不推送；事务回滚后的推送读取已结算的树。
- 推送后来进一步按来源简化：TaskUpdates 与 publishing.py 已删除，信号内直接发送树和日志，详见第 6.1 节。
- `ScriptExpander` 拥有本轮 `TaskHistorySession` 和报告协调器；旧专项直接使用传入的历史会话。托管收尾直接判断诊断，最终关闭历史会话并发送完成树。
- `LegacyCallbacks` 只服务旧专项：同步/线程回调交付协程，由同一消费者赋值并提交；子任务共享当前 manager 的桥，旧收尾前后排空，L2 在 manager 返回后关闭入口。失败不会丢掉后续写入，错误仍影响任务终态。插件 L3/L4 不调用它。
- `TaskExecuteBase.execution_mode` 仅在旧专项中将 `SCRIPT_VIEW` 映射到配置执行、将维护入口映射为 `Update`；运行树始终保留标准 `TaskMode`。热态用户查询和维护查询直接调用既有配置/服务，不再经过根模型。
- 社区签到报告协调器由 L2 持有，经既有通知批次传给旧专项和子任务收尾；批次退出后恢复上下文，不同任务 ID 不复用协调器。

中止使用 `TaskBase` 生命周期和树中的 `cancelled` 终态。旧专项通过适配层感知根任务取消，历史会话独立控制是否接受采集；停止发生在子任务收尾期间也不需要额外的根模型取消标记。

本次只调整内部职责，HTTP/WS 的路径和 OpenAPI 模型对比均未变化，前端不需要重新生成。原有任务与专项统计边界、事件和维度保持不变，未增加重复采集。

本节验证：后端全量 1237 项通过、3 项跳过、29 项 subtest 通过，收集到 1240 项测试；28 个相关文件的 Pyright/mypy 均零诊断，后端 lint/format 和本文 Markdown 检查通过。新增回归覆盖跨线程同协程提交、排空与关闭拒收、失败后继续提交、取消终态等待回调、事务回滚与集合信号、旧模式映射及报告协调器隔离。未执行真实游戏、账号或设备流程。

## 16. 按来源方案直接推送

`publishing.py` 和 `TaskUpdates` 已删除。该阶段曾将树导出函数归入 tree.py，第 18 节进一步内联并删除该文件；调度器类级信号接收者直接 await Publisher，保留事务内过程态通知，未新增配置框架接口。日志从根 `current.log` 虚拟字段读取，每次发送全文，不维护差量、基线、发布任务或关闭屏障。

历史会话不再缓存配置变更事件；L2 托管收尾直接调用 observe，再由根收尾关闭会话。前端调度台及三个维护入口全部采用日志全文替换；保留已有 HTTP 重连恢复与请求防陈旧保护，删除日志序号断裂重同步。OpenAPI 已重新生成，日志消息只含 log，快照移除 logSeq/logFirstLine，并新增根 current.log。

旧推送合并和增量协议已移除，对应测试由同协程即时信号、回滚过程态、集合变化、全文替换、空日志清空、当前指针和裁剪边界的回归替代。此前各节的验证数量是对应阶段记录；本次全量后端 1236 项通过、3 项跳过、29 项 subtest 通过，前端 153 项通过；26 个相关文件 Pyright/mypy 零诊断，renderer/Electron 类型检查、lint、format 和前端构建通过，3 项隔离浏览器流程通过。未执行真实游戏、账号或设备流程。

鸣潮编辑组件的日志协议属于局部维护：1206 → 1170 行，未增加独立业务区域；其余前端改动位于 TypeScript 模块，未新增 Vue 组件。

## 17. 删除独立资源预约，回到执行层等锁

`app/core/task_manager/resources.py`、`_ScriptTaskReservations`、`ManagerBuildContext`、`ScriptTaskResources` 及配置服务的任务资源查询已删除。六个只为资源声明服务的专项文件也已删除；模拟器配置绑定字段直接保留在各专项原有的配置能力声明中。没有把预约表移入其他模块。

L2 不再预读目录和设备、登记资源键、轮询预约或统一释放。它只重新解析托管、校验身份并选择执行路径。内建工厂统一接收一个 `ScriptItem`，原来的参数树和 `TaskContext` 传递保持不变。

插件路径保留 L3 托管本体非递归 X 锁和 L4 当前用户级联 X 锁，等待、校验和释放都归对应执行层。旧路径保持 manager 原有递归锁范围，在原有 `lock_script_config()` 位置尝试取锁并等待；每次重试检查删除或替换，取消沿 TaskBase 传播。目录操作使用已有配置保护；SRC 取得配置锁后才读取并固定本轮路径，删除启动前目录预约、路径比较及恢复目录追加预约。原有历史快照归属和安装标识校验仍保留。

未来游戏和设备的订阅、等待与释放仍只在 L3 取得托管锁后、派发用户前及对应收尾处留注释，由真实资源提供方处理，不增加专门接口。旧 manager 仍复用已有设备与安装访问能力，未进行游戏模块迁移。

新增回归直接使用真实配置锁，覆盖竞争后读取热态字段、等待取消、等待期间配置删除，以及 SRC 等锁后读取最新路径。原预约算法测试已删除；队列并发触发、工厂装配、配置绑定及专项冷导入验证继续保留。

本节验证：全量后端 1239 项通过、3 项跳过、29 项 subtest 通过，收集到 1242 项测试；29 个相关文件的 Pyright/mypy 均零错误，后端 lint/format、后端差异空白检查、本文 Markdown 检查通过，289 个源码链接存在。OpenAPI 全量对比未变化，未修改前端客户端。来源 TaskBase 与修改前逐字节相同。未执行真实游戏、账号或设备流程。

## 18. 内联要求树解析与建树

`app/core/task_manager/tree.py` 已删除。解析与创建归入 `_TaskManager._launch()`：先校验要求节点及触发来源，再在一个短事务内激活根、校验配置/查看会话、按配置顺序展开并直接创建队列、托管和用户运行节点。只保留局部 `select()` 复用各层的单向顺序匹配，不再生成 UserSpec、ScriptSpec、QueueSpec，也不再二次遍历中间规格。

`TaskRequirements` 归入已有 `schema.py`，允许内部调用传模型节点或字典，公开参数仍是 mode 和 tasks。旧专项维护入口共用同一受理流程。查询、最近终态和即时推送在原调用位置直接导出并校验契约；快照与完成消息复用外层响应模型的校验，不再经过单独的 export_task_tree 包装。

所有配置读取和运行树创建在同一事务内完成，失败在登记前回滚，不调用未启动执行器的完成推送；登记后失败仍沿原有 TaskBase 停止与收尾。创建屏障覆盖整个建树过程。新增两项回归覆盖已经建立前序用户后，后续用户不存在或层数不合法时仍不发布半棵树，且下一次创建正常受理。

本节验证：全量后端 1241 项通过、3 项跳过、29 项 subtest 通过，收集到 1244 项测试；16 个相关执行文件的 Pyright/mypy 零错误。共享 schema 单独检查的 4 项既有诊断与修改前一致，未新增诊断。OpenAPI 对比未变化；后端 lint/format、后端差异空白检查通过。未执行真实游戏、账号或设备流程。

## 19. 合并为单文件组件

原 task_manager 包的实现与单例合并为 `app/core/task_manager.py`，同文件定义 `_TaskManager` 并创建 `TaskManager`。原 manager.py 与包入口已删除，不保留转发模块。业务继续通过 `from app.core import TaskManager` 获取同一单例；内部类型提示及隔离测试直接引用 `app.core.task_manager`。

本轮只调整文件归属和引用，执行逻辑保持原样，未新增统计或改变外部契约。方法清单、冷导入检查、组件单例检查与 E2E 入口文档已同步。相关 80 项回归通过，完整收集到 1244 项测试；15 个相关执行文件的 Pyright/mypy 零错误。

## 20. 定时写入约束归入模型信号

`queue.py` 的 `reject_disabled_time_writes()` 同时订阅 TimeSet.Info 字段和配置集合的运行时信号，仅作用于 QueueConfig.TimeSet。定时关闭时，字段提交及新增、删除、排序等结构提交抛出 ValueError，由配置框架回滚并聚合上抛；初始化事件不受此限制，禁用状态的已有设置可正常加载。父队列开关按当前事务的热态值读取，同事务启用后可直接新增，后续操作被拒绝时前序变更一并回滚。

Config 的四个时间项 CRUD/排序方法已删除开关判断。更新方法交由模型信号判断可写性，避免界面显隐静默跳过业务错误；API 接收 ConfigAggregateError 并保留现有 409 错误外壳。循环配置继续使用已有模型显隐逻辑，本轮没有增加循环状态或计时机制。队列设置的现有统计入口保持唯一所有者，未重复采集。

模型拒绝写入同时暴露了原有信号分发的协程清理问题。分发仍先同步调用包装器，再逐个等待返回值；改为显式持有这些临时结果，在同步/异步订阅拒绝或取消时关闭其余已创建协程。静音语义、原异常和事务内通知顺序均保留，没有新增后台推送或提交后通知机制。两项回归验证同步和异步拒绝时的协程关闭及静音行为。

模型回归覆盖字段赋值、显式更新、集合增删排序、禁用状态普通/快速加载、事务开关变更和不相关配置写入；API 回归覆盖四种写入拒绝与重新启用后的成功执行。共享默认星期列表只整理类型声明与重复值，OpenAPI 对比保持一致。

本节验证：全量后端 1255 项通过、3 项跳过、29 项 subtest 通过，无协程告警；收集到 1258 项测试。相关 28 项回归在 RuntimeWarning 按错误处理时通过；模型、API、信号节点三个文件的 Pyright/mypy 零错误。后端 lint/format、后端差异空白检查及 286 个源码链接检查通过。未执行真实游戏、账号或设备流程。

## 21. 统一集合构造泛型

剩余 10 处未绑定泛型的 `ConfigCollection.build()` 调用已统一，包括模拟器、计划、脚本根集合，社区账号默认工厂，以及相关测试夹具。社区账号的私有字段和属性返回注解也绑定 GameSignAccountGroup。队列根此前已绑定 QueueConfig；目前源码与测试中已没有裸 build 调用。字段快捷声明 collection() 的内部构造仍由其泛型签名和字段注解提供类型。

混合计划集合使用 PlanConfigType 联合，脚本集合沿用 ScriptConfigType 联合；PLAN_BOOK 只补充 TypedDict 类型声明，成员及业务关系不变。测试夹具按允许后续登记的实际范围绑定类型，避免将支持多专项的夹具错误限定为 GeneralConfig。

混合配置的动态更新通过 ConfigEntry 基类视图调用，补丁仍由目标的实际类型创建；动态用户新增在 handler 选择用户类后，通过基类集合视图交给原有登记表核验。这些局部视图保留实际方法派发，不引入 Any、重复分支或新执行接口。旧 related_config 兼容元数据改为动态取值后绑定，不再依赖联合类属性的错误推断。

静态断言确认四个配置根、社区账号集合、迭代和取项返回类型，Pyright/mypy 均通过；相关 11 个文件的 Pyright 诊断由原有 7 项降至 2 项，剩余为此前已有的 SSL 缓存签名诊断，本轮无新增诊断。全量后端 1255 项通过、3 项跳过、29 项 subtest 通过，相关最小回归 85 项通过。OpenAPI 对比保持一致，未修改客户端；未执行真实游戏、账号或设备流程。

## 22. 背景任务组替换原注册表

单文件 [background\_tasks.py](D:/Dev/AUTO-MAS/app/core/background_tasks.py) 定义实现类 `BackgroundTaskRegistry`，模块底部建立 `BackgroundTaskManager` 单例；业务统一从 `app.core` 导入。`TYPE_CHECKING` 引用真实单例，组和句柄的泛型参数把工厂返回值保留到 `TaskOutcome[T]`。它独立于任务执行树，来源 `TaskBase` 没有增加背景任务职责。原 `runtime_tasks.py` 已删除，不保留兼容别名。

基本用法：

```python
from app.core import BackgroundTaskManager

group = BackgroundTaskManager.register_group(
    "resource-preparation",
    max_running=4,
    max_retained=8,
    execution_timeout=30,
    result_ttl=300,
)
handle = group.spawn(lambda: prepare_resource())
if handle is not None:
    outcome = await group.wait_take(handle, timeout=5)
    resource = outcome.unwrap()
await BackgroundTaskManager.unregister_group(group, timeout=10)
```

`spawn` 接受协程工厂；拒绝时返回 None，工厂不会执行。`max_running` 限制尚未真正退出的执行，`max_retained` 限制全部未清理的任务记录（运行中和已完成待提取），两项均为申请组时明确给定的正整数。组满时直接拒绝，不另建等待队列。名称在管理器内唯一；组注销完成后可再次申请同名组，旧句柄仍只属于原组。一个组只用于一个事件循环。

`query(handle)` 只读元信息，不消费、不续期；`try_take(handle)` 未完成返回 `PENDING`，完成后原子移除并返回结果。`wait_take()` 等待后执行相同的唯一提取，多个等待者只有一人能成功；已提取、已过期、未保留结果均抛 KeyError。成功的 None 与待完成状态明确区分。结果状态为成功、失败、取消或执行超时；`unwrap()` 返回成功值或抛出对应异常。

等待超时和等待方取消不取消背景任务，也不消费结果。`execution_timeout` 默认不设置，设置后到期请求取消；任务若正在异步清理或抑制取消，继续占用执行容量，直到真正退出，再记录执行超时。`handle.cancel()` 同样请求协作取消，不负责强制终止线程或进程。重复关闭不重复 cancel 已在取消中的任务，以免打断清理。

未提取结果默认从完成时保留 300 秒，通过 `call_later` 丢弃；不创建清扫协程。`retain_result=False` 的任务完成即清理，只保留可查询完成状态的句柄，不缓存业务返回值。普通异常按任务隔离，不取消同组其他任务；未提取的异常在丢弃时记录。管理器释放的是任务及结果引用，不主动删除返回值所指向的文件。

`drain(timeout)` 只等待执行，不提取、不取消，也覆盖等待期间新增的执行。`unregister_group()` 封闭提交、取消执行、清空已完成结果并等待退出；超时返回 False，组保持关闭状态和强引用，最后一项退出后才从管理器移除。`shutdown()` 先封闭所有组，再以同一等待期限回收。宿主仍在回放服务停止后、通知资源关闭前执行全局 shutdown。

接入归属与当前容量：

- 启动资源预加载：应用级单项组，运行和记录容量均为 1，完成即释放。
- 旧专项回调：每个 manager 独立组，容量均为 2；一个消费者串行执行全部回调。第二个名额仅容纳前消费者退出到完成回调之间的新批次，不增加业务并行。桥关闭时排空、注销；启动前取消也释放队列中的未开始协程。
- 用户失败回放：每个历史会话独立组，运行 32、记录 64。采集成功后先把临时路径登记到历史会话，再作为结果返回。提取超时、结果过期或取消等待都不会丢失清理归属；会话关闭先注销采集组，等采集退出后删除受管临时副本。
- 无用户归属的诊断回放：应用级组，容量均为 32，完成即释放，允许晚于任务根结束。只保存 OBS 原件，文件仍归 OBS，不会被管理器删除。
- 任务通知与反馈：每个通知服务独立组，容量均为 128，完成即释放。业务批次和报告协调器仍由通知模块持有，在途集合与等待委托给任务组。
- 社区通知：每个通知服务独立组，运行 32、记录 64；短暂等待窗口内提取渠道结果，迟到结果按 TTL 丢弃。失败反馈在业务投递中安排，不再同时从完成回调和请求等待方重复读取结果。通知服务关闭时先注销两组，再关闭渲染器和渠道。
- 托管统计旁路：应用级组，容量均为 32，完成即释放。开始消息的完成事件和成功标志归本次观察上下文持有，避免长时间执行耗尽结果缓存；结束消息仍等待开始消息成功。原有匿名计数的唯一所有者和隐私字段不变，管理器不新增业务统计。

本轮验证：全量后端 1273 项通过、3 项跳过、29 项 subtest 通过，收集到 1276 项测试。背景任务及接入点的 28 项最小回归在 RuntimeWarning 作为错误时通过；相关 9 个文件 Pyright 零错误，7 个文件 mypy 零错误。后端 lint、842 个文件 format 检查、源码链接检查通过；TaskBase 与本轮改动前逐字节相同，OpenAPI 对比一致。未执行真实通知渠道、OBS、账号、游戏或设备流程。

## 23. 后端对齐已确认的调度设计

删除队列运行节点，任务根直接包含托管；来源元数据不形成运行树。L1 解析队列项并统一提交通用、启动及循环时间，trigger 原因枚举只表达一个独立原因，各触发路径分别派发。L2 为插件持托管本体锁，L3 持用户级联锁，L4 仅使用已锁配置执行并恢复；正常路径与取消收尾都由持票层释放。旧 manager 保持独立递归锁，插件探测返回旧能力时先归还探测锁。TaskBase 实现保持原样。

后端日志仅按行截尾，原有统计仍由实际任务和托管终态的唯一观察入口承担，不增加重复采集。API/WS 通过真实 OpenAPI 重新生成客户端，前端只同步运行树读取投影。任务启动表单、恢复起点、用户选择以及前端日志显示容量本轮不调整；重复队列项的独立选择仍待前端阶段处理。

本阶段验证：后端全量 1280 项通过、3 项跳过、29 项 subtest 通过，收集到 1283 项。相关 52 项回归在 RuntimeWarning 作为错误时通过；六个主干文件 Pyright/mypy 零错误，后端 lint 与 843 个文件 format 检查通过。前端 153 项测试、lint、typecheck、format 和 vp build 通过，没有执行应用打包。HTTP 路径和创建请求契约保持一致，运行树契约通过生成器更新；TaskBase 和暂缓的前端启动／显示缓冲文件逐字节保持不变。曾有一次全量中的 HSR 子进程退出检查失败，单独复核 26 项通过，随后完整回归通过，未修改 HSR 实现。未执行真实通知、OBS、账号、游戏或设备流程。

## 24. 触发原因保持单值

TaskTriggerReason 仅保留 MANUAL、STARTUP、TIMED、CYCLE，删除组合值和组合判断方法。timer 各触发条件独立判定、分别提交普通任务，不合并为多原因任务；某一路受理失败不阻断其他触发路径。L1 统一更新通用上次运行时间，只有 STARTUP 更新启动记录，只有 CYCLE 更新循环基准，不因其他机制启用而更新其专属时间。

Skill、生成契约和回归断言同步采用单一触发语义。前端启动选择仍保持原样，未增加新的控制项或兼容分支。

本轮验证：相关 58 项回归通过；三个变更主干文件 Pyright/mypy 零错误，后端 lint/format、Skill 校验和前端 typecheck 通过。全量收集 1288 项，结果为 1284 项通过、3 项跳过、29 项 subtest 通过，另有 HSR 子进程退出检查一项失败；该项单独复核通过，与前一阶段出现过的失败相同，未修改 HSR 实现，不能据此声称本轮全量无失败。OpenAPI 与生成客户端均仅有四个原因，TaskBase 和前端启动选择保持不变。

## 25. 移除队列来源分组

TaskQueueSource、私有来源列表、来源区间和 queue_running 已删除，不引入替代包装。L2 只按根下托管顺序循环，现有星期限制、插件／旧 manager 分叉、锁与取消收尾不变。队列级前后附加脚本和结束时读取队列 AfterAccomplish 的路径一并移除；托管／用户脚本操作仍使用其原业务链，独立全局电源动作仍由 dispatch 配置、任务全数结束后由既有电源服务执行。二者不等同于保留原队列级配置语义。

L1 用受理函数内的队列对象列表完成原子记时，记时后不保留对象或区间；空队列同样记时。创建消息名称在受理时读取；运行树和状态查询不保存或反查队列来源。查询、重连和 WS 继续使用同一任务树，公共契约不新增字段。

本节验证：相关回归 56 项通过；完整后端 1284 项通过、3 项跳过、29 项 subtest 通过，收集到 1287 项测试。三个修改模块的 Pyright/mypy 零错误，后端 lint/format 和 Skill 校验通过，OpenAPI 导出前后相同。未修改前端任务启动方案，未运行真实游戏、账号或设备流程。

## 26. 专项运行进度不进入公共任务树

删除 UserTaskProgress、用户 info.progress 和将其移入用户 current 的中间实现。用户节点只保留公共身份、状态、日志等信息；快照、查询和 WS 继续直接从任务树导出，不另建专项进度契约。调度台同步移除对应的类型、投影、签名和进度文本，API 客户端由 OpenAPI 重新生成。

MaaFWRunRecorder.apply 只归并 worker 事件，不再向调度器返回进度对象；runner 不再提交或清空公共用户进度。尝试编号、重试跳过数、任务序号／名称、开始／结束及结果仍保存在 MaaFW 的运行记录，用于原有历史快照与专项报告，不扩充公共模型。

本节验证：相关后端回归 66 项通过，完整后端 1285 项通过、3 项跳过、29 项 subtest 通过，收集到 1288 项测试；前端 153 项测试通过，lint/typecheck/format 和 `yarn exec vp build` 通过。后端 lint/format、两个修改模型模块的 Pyright 和 Skill 校验通过。扩大检查的 Mypy 在 MaaFW 记录模块报告 4 处结果常量与 Literal 的类型错误；使用修改前的模型及记录模块副本复查，仍为同样 4 处，未在本次移除中扩展处理。TaskTree.vue 从 405 行减至 380 行，TaskOverviewPanel.vue 从 152 行减至 148 行，符合组件大小约束。未验证真实游戏或设备运行。

## 27. 配置锁与专项报告数据移出公共树

删除用户与托管信息中的 locked/recursive_lock，删除维护跳过标记、通知明细及排版模式；保留来源的虚拟 result。L2/L3 仍持有凭证、等待资源并在下层恢复之后解锁，旧 manager 仍自行管理递归锁，不再为这些流程维护运行树投影。公共结果与统计只依据状态，不读取维护专用标记。

LegacyUserState 位于 app/task/legacy.py，维护判断和通知素材按用户运行 UUID 保存在旧执行链的字典中；spawn 将同一字典交给子执行器。各专项原有过滤、汇总／逐条、账号路由和回调排空继续使用这些素材；对象不附着于信息树，不进入查询、WS 或任务历史树附件。它只有专项素材，没有第二套任务状态、进度、结果或锁。

配置锁查询位于 app/api/scripts/management.py 的 get_script_lock：按托管及可选用户解析当前配置，返回配置基类 is_locked，目标遗失返回业务 404。useScriptConfigLock 使用共享 Vue Query 缓存并每秒读取当前目标，不依赖任务快照；后端配置锁继续负责拒绝冲突修改。用户／托管保存入口移除按任务树猜测权限的前置判断。此处没有修改配置框架，也没有为缺失的游戏／插件增加占位 API。

本节验证：完整后端 1287 项通过、3 项跳过、29 项 subtest 通过，收集到 1290 项测试；收尾针对性回归 67 项通过。前端 153 项测试、lint/typecheck/format 与 `yarn exec vp build` 通过。核心七个修改模块 Pyright 零诊断，六个调度／兼容模块 Mypy 通过；扩大到 23 个修改模块的旧专项检查，修改前为 491 条、当前为 487 条诊断，无新增，未在本次重写存量专项的类型体系。两个既有 API 动态 ConfigPayload 联合返回契约的 Pyright 局部抑制已附原因。后端 lint/format、Skill 校验通过。未执行真实游戏、账号、设备或浏览器交互验证。

## 28. 移除托管节点的队列副本

TaskScriptItem.info 的 queue_id、queue_item_id、queue_params 已删除，L1 不再写入，未改为私有映射、重建队列层或转存到 params。运行树内父级信息经 ConfigNode.parent/root 访问，TaskScriptItem 的父链为托管集合与任务根；原队列在 L1 展开后不属于运行父链，不能用该父链反推出原队列。队列解析、顺序与重复次数校验、星期快照和受理记时仍由原层负责。

依赖这几个字段的 TaskItem.queue_id 兼容属性及 HTTP/WS/前端运行缓存中的 queueId 也已移除；script_id 投影直接读首个托管的原配置 ID，查询与重连不猜测来源队列。旧专项的 is_queue_task 仅用于次数上限策略，复用当前托管的 _run_days 是否存在来区分队列／直接运行，不增加字段；混合选择时按当前托管判断。

本节验证：原相关回归 76 项通过，新增混合队列／直接运行用例通过；完整后端 1288 项通过、3 项跳过、29 项 subtest 通过，收集到 1291 项测试。前端 153 项测试、typecheck/lint/format 和 `yarn exec vp build` 通过。任务模型与管理器 Pyright/Mypy 通过；扩大检查的共享 schema 有 4 处既有诊断，修改前副本的诊断类别、首行与数量均一致。公开树 schema 与任务元数据均无上述队列字段；来源 TaskBase 和暂缓的前端选择文件保持不变。未执行真实游戏、设备或浏览器交互。

## 29. 完整日志树与独立增量推送

本次设计取代早期“树导出尾部 1000 行＋每次全文替换”。移除模型裁剪及旧专项写入窗口，信息树 first_line 同步移除；旧协议 firstLine 由传输层计算。当前来源由 TaskItem.current_log_source 统一解析，独立游标记录来源 UUID，切换到正文相同的新来源也会替换。插件路径读取当前用户完整记录；旧专项由 manager 的托管展示日志承接流程提示与原生日志镜像，避免提前建立的用户记录遮住流程提示。未选中用户的正文变化不发包。

信息、日志分别订阅，完成消息也使用不含正文的投影。查询、重连与最近终态保存完整树；只有 WS 替换包和前端显示窗口受原有预算约束。配置框架及来源 TaskBase 没有改动。相关规范已经同步到调度 Skill。

WS 发送返回 False（例如离线）时仍记录本次序号，重连通过快照建立基线；发送抛出异常则不推进。前端的 task-runtime 仅保存 HTTP 日志基线，实时日志仍由调度面板的独立订阅合并，信息与完成消息不覆盖该基线。

本节验证：完整后端 1293 项通过、3 项跳过、29 项 subtest 通过，收集到 1296 项测试；最终信号与增量回归 10 项通过，完成树／完整查询补充断言通过。前端 156 项测试通过，typecheck/lint/format 与 `yarn exec vp build` 通过。三个核心修改模块 Pyright/Mypy 零错误，后端 lint/format 与 Skill 校验通过。覆盖完整长日志、只推新增片段、重置／清空、相同正文切换来源、非当前正文不推、替换包预算、发送异常释放游标锁、事务过程态及回滚查询、完成消息无正文而查询保留正文。未执行真实游戏、设备或浏览器交互验证。

显式 logSeq=null 的过程态快照复用 task-runtime 已有的有界重试取得可追加基线，不新增后台调度器。新增前端回归确认取得提交后基线即停止重试。

## 30. 触发原因只保留枚举

移除 TaskItem.Info.trigger_source、is_cycle 及对应虚拟计算、平铺属性和 TaskTriggerSource 别名。info.trigger 是唯一触发事实；创建通知、单点状态、重连快照使用 trigger 字段，前端运行缓存保存 TaskTriggerReason，循环展示在使用处比较 CYCLE。队列配置中的循环启用设置不受影响。

社区签到在 L2 调用边界根据枚举选择 task_manual、task_startup、task_scheduled；匿名统计在 telemetry.task_trigger_category 转换为原有 manual_task、startup_task、scheduled_task 分类，保持既有统计口径，不新增收集。客户端通过 OpenAPI 重新生成，未调整暂缓的前端启动选择方案。

四种原因的回归覆盖创建推送、完整查询、元数据更新、重连快照和终态查询，确认均不含派生字段，且通知与统计分类保持一致。

本节验证：相关后端回归 69 项通过；完整后端 1297 项通过、3 项跳过、29 项 subtest 通过，收集到 1300 项测试。前端 156 项测试、typecheck/lint/format 和 `yarn exec vp build` 通过。三个核心模块 Pyright/Mypy、后端 lint/format 与调度 Skill 校验通过。未执行真实游戏、设备或浏览器交互。

## 31. 模型信号与私有日志游标

删除调度器的 _LogState、_logs、额外日志锁以及元数据／日志快照辅助方法。TaskItem 提供 connect_updates、disconnect_updates、get_update 和 get_log_snapshot，内部配置类订阅独立处理信息与日志；TaskManager 登记后绑定发送回调，注销与创建失败时解除回调，查询和 L2 完成消息直接读取模型投影。

模型不导入 core、services 或共享 schema，宿主在发送边界校验契约并调用 Publisher。信号仍在配置事务内、同协程直接等待；不添加发布队列。配置全局事务入口已串行保护信号链，不再另加推送锁。发送游标只写 live 节点私有属性，不跟随配置回滚。

按行日志只浅拷贝上次已发送的行列表，保留字符串引用；追加时按行数、切片及前缀判断，只拼接新增行。来源切换、清空、替换、超大追加和与事件旧值不匹配的基线改发替换包。查询与发送基线不匹配时继续返回空序号，前端沿用完整快照恢复。实际 WS 字段和统计口径不变。

本节验证：最小相关回归 56 项通过，新增用例后的信号／日志与模型独立导入回归 14 项通过；完整后端 1300 项通过、3 项跳过、29 项 subtest 通过，收集到 1303 项测试。三个核心模块 Pyright/Mypy 零错误，后端 lint/format、调度 Skill 校验及本次文件差异检查通过。真实路由导出的 OpenAPI 与修改前完全相同，前端及生成客户端未改动；未执行真实游戏、设备或浏览器交互。

## 32. 导入即生效的模块级订阅

取代第 31 节的逐任务发送回调注入。调度模块导入时，_info_changed、_log_changed 通过配置类 connect 装饰器统一安装；_TaskManager 构造和任务启动均不执行推送订阅。接收者按当前运行表筛选任务根，受理前的建树过程和注销后的修改不发布。

移除 _subscribe_updates、模型的 connect_updates／disconnect_updates 和实例发送回调属性。模型仅保留 clear_log_cursor、日志基线、get_update／get_log_snapshot 及 publish_log 的增量计算；宿主订阅按既有契约实际发送。发送回调只作为 publish_log 当次调用参数，不保存到实例。结束与创建失败路径只清理私有游标。

Publisher 在调度模块安装订阅前已可用，实际调用发生在运行期信号内，不要求 WebSocket 服务端已经监听。任务模型不依赖 core、services 或共享 schema，独立导入测试保持成立。字段、日志协议和统计行为未变化，不增加发布队列、推送锁或公开配置开关。

本节验证：相关回归 57 项通过；完整后端 1300 项通过、3 项跳过、29 项 subtest 通过，收集到 1303 项测试。三个核心模块 Pyright/Mypy、后端 lint/format、调度 Skill 校验和本次文件差异检查通过。真实路由导出的 OpenAPI 与修改前完全一致；前端及生成客户端未改动，未执行真实游戏、设备或浏览器交互。

## 33. 随模型声明直接绑定推送业务

取代第 32 节将订阅放在 core/task_manager 模块作用域的实现。TaskItem 等模型定义结束后，直接通过配置类 connect 装饰器声明 `_info_changed`、`_log_changed`。仅导入 app.models.task 即完成绑定，不依赖调度模块导入、管理器构造或逐任务注册回调。

信息／日志筛选、元数据生成、增量计算与 WS 发送均由模型文件内的接收者处理；管理器只维护实际运行登记及结束时的游标清理。移除 publish_log 的单次回调参数、TaskUpdateHandler 别名及管理器模块中的接收者，不新增发布模块或注入层。

绑定时不访问 Publisher。实际回调需要发送时才解析已有宿主和传输契约，避免 WS 契约导入任务模型的循环；模型声明导入仍不初始化 core。按运行登记过滤、事务内同协程通知、私有游标不随配置回滚、完整查询与旧增量协议保持不变。相应模型边界规范已经按本次确认同步，仅允许任务推送这一业务例外，不迁入 L1 或专项执行。

本节验证：扩展模型独立导入回归，确认导入阶段不初始化 core 且各任务配置类已经安装订阅；新增断言在修改前失败、修改后通过。相关回归 57 项通过；完整后端 1300 项通过、3 项跳过、29 项 subtest 通过，收集到 1303 项测试。三个核心模块 Pyright/Mypy、后端 lint/format、三项相关 Skill 校验和本次文件差异检查通过。真实路由导出的 OpenAPI 与修改前完全一致，前端及生成客户端未改动；未执行真实游戏、设备或浏览器交互。

## 34. 兼容接口的定义标记

兼容专用方法／属性定义的 docstring 首行统一标注 [兼容旧专项] 或 [兼容旧调用方]，同时给出新代码入口；本次标记 83 个方法／属性定义及 7 个兼容类，方法数包含重载声明和属性 setter。方法清单优先显示这些标记，类型别名、工厂字段、隐藏维护标志及混合流程的兼容分支使用对应注释。

范围包括 TaskManager 的旧运行视图、旧工厂绑定、stop_task 和 start_maintenance；任务模型的平铺构造／属性、整数位置、旧时间索引日志与用户重建；legacy 模块的旧执行基类及同步回调桥；旧 manager 的用户筛选和递归锁、单用户旧生命周期及日志 sink。start_maintenance 等既有入口继续工作，不改变模式、调用签名、告警或执行分支。

新代码按标记使用 info/current 分组、scripts/users/logs 有序集合和运行 UUID，标准创建／停止入口及来源 TaskBase，插件按 L3/L4 派发。基础 set_state、append_content、虚拟结果、模型订阅与标准查询能力保持正常用途标注；当前主链已有的兼容调用留待后续迁移，本次只加标记。

本节验证：逐文件比较去除 docstring 后的完整 AST，10 个 Python 文件的可执行结构与修改前一致；OpenAPI 导出与修改前完全相同。相关回归 46 项通过，三个核心模块 Pyright 零错误；后端 lint/format、调度 Skill 校验与本次文件差异检查通过。本次只改注释、docstring 与说明文档，未新增测试、修改调用或执行完整后端／前端回归。

## 35. 单顶层入口与 L1 外层循环移除

一次要求树必须且只能包含索引 0 一个入口：自动代理为一个队列 UUID 或 -，会话为一个托管 UUID。HTTP 契约使用 minProperties/maxProperties 限制，内部创建也在激活与建树前拒绝空或多个入口。要求树结构与返回一个任务 UUID 的契约保持一致。

_launch 直接解析唯一 node，删除顶层遍历、真实队列顺序比较、队列引用列表和队列时间遍历；按一个 queue 或 None 处理记时与展示名称。托管／用户选择仍循环，队列项的顺序、重复托管独立身份、空子树展开及参数传递保持原语义。

旧多队列与队列／直接混合请求用例按新约束调整：分别拒绝多来源，在单队列内验证三个托管项顺序；旧次数策略改用两次独立任务验证。记时回退用例改为同一个队列的原因专属字段提交失败，验证通用时间与整体建树一并回退。定时和 QQ 入口现场确认已经每次构造单入口，无需改变触发机制。前端启动选择方案继续保留，仅按生成器同步 API 文档。

本节验证：相关回归 69 项通过；完整后端 1311 项通过、3 项跳过、29 项 subtest 通过，收集到 1314 项测试。前端 156 项测试、typecheck/lint/format 与 `yarn exec vp build` 通过；三个核心模块 Pyright/Mypy、后端 lint/format、调度 Skill 校验及本次差异检查通过。OpenAPI 导出确认根节点 minProperties/maxProperties 均为 1，客户端仅通过生成器更新 TaskCreateIn 文档。来源 TaskBase 与暂缓的两个前端启动选择文件字节校验一致；未执行真实游戏、设备或浏览器交互。

## 36. 托管标识投影直接内联

移除 _TaskManager._identities。普通任务创建通知与运行快照在使用处遍历 info.scripts.values()，直接从各节点 info.script_id／info.script_type 构造标识列表；不再经过旧 script_list、script_id、script_type 平铺投影。顺序、重复项及既有消息字段保持一致，已安排托管的收集逻辑不受影响。

本节验证：68 passed in 5.97s；task_manager 的 Pyright 零错误，lint/format 与本次文件差异检查通过。未修改公开契约或前端代码，未新增测试或执行完整回归。

## 37. TaskManager 方法职责注释

补齐 16 个管理器方法／属性及局部 select 的 docstring，保留原有兼容标记。注释交代受理、事务与登记边界、停止全部屏障、最近终态缓存、查询和结束动作，方法清单同步采用定义处的职责摘要。

以下是第 37 节当时的实现，已由第 38 节移除：_scheduled_script_identities 曾为快照的 scheduledScripts 提供展示名单：启用循环，或启用定时且存在启用、星期非空的时间项时，纳入队列中的托管；缺失配置跳过，按原托管配置 UUID 跨队列去重。前端 collectScriptStatuses 将这些配置标识标为 queued，驱动卫星的已安排状态。此名单不表示已创建运行任务；当前是否到期、队列项当日条件、用户准入由实际触发与执行层处理，仅启动触发的队列不纳入名单。

本节只修改文档字符串和方法说明；去除 docstring 后的完整 AST 与修改前一致，全部管理器方法覆盖检查、lint/format 和本次文件差异检查通过，未新增或执行功能回归。

## 38. 卫星展示回归配置与持久化历史

TaskManager 只管理实际执行任务。删除 _scheduled_script_identities 和 TaskRuntimeSnapshot.scheduledScripts，运行快照只含 tasks；实际任务中的 scripts 仍用于标识本轮执行的托管。前端运行缓存移除排期名单、会话级失败摘要及 collectScriptStatuses/scriptStatusesBy，既有调度面板与任务事件协议继续使用实际运行树。

新增只读 GET /api/info/scripts/status，由以下职责链提供展示数据：

- [AppConfig.get\_script\_status\_overview](D:/Dev/AUTO-MAS/app/core/config/manager.py)：读取当前托管标识、类型、名称与队列排期关系，调用历史查询后返回概览；不读取 TaskManager、不修改配置、不更新时间。
- [HistoryStore.get\_latest\_script\_results](D:/Dev/AUTO-MAS/app/core/history.py)：使用已有 script_name 索引，在一个数据库连接内查询每个名称最近一条结果；不读取日志正文或附件。
- [get\_script\_status\_overview](D:/Dev/AUTO-MAS/app/api/info.py)：返回统一信封；历史读取失败返回业务错误，不能伪造“最近成功”。
- [ScriptStatusOverviewItem](D:/Dev/AUTO-MAS/app/models/schema.py)：共享字段为 scriptId、scriptType、scheduled、lastRunAt、lastFailed；接口响应模型留在所属 API 模块。前端客户端只通过实际 OpenAPI 导出和生成器更新。
- [useSatelliteStatus](D:/Dev/AUTO-MAS/frontend/src/composables/useSatelliteStatus.ts)：Vue Query 缓存配置／历史概览，按卫星的脚本类型或 MaaFW 项目映射聚合。排期取任一托管已安排，失败取组内最近历史结果；同一时间有失败即标失败。查询失败保留上次成功结果。

已安排沿用配置含义：启用循环，或启用定时且存在启用、星期非空的时间项。这里只展示排期关系，不推断是否到期、当日队列项是否执行或用户是否准入；只启用软件启动触发的队列不算定时／循环排期。

历史库目前只记录托管名称，按当前 Info.Name 关联；同名配置的历史归属无法区分时保持未知。改名后不会沿旧名称追溯，删除／重建同名配置也无法仅凭现有历史识别为不同对象。本次不扩展历史存储契约，也不借运行内存补造结果。

两个卫星组件保留既有每 10 秒刷新、窗口后台暂停及回到前台立即查询的节奏；移除“WS 连通则停止轮询”的旧条件。WS 仅作为现有启动就绪门槛，不向卫星提供任务事件。卫星提示和动效只使用“已安排／最近失败”；删除运行中／重试中显示与脚本开始触发的彩蛋。手动交互彩蛋保留。

全局性能设置中的“脚本运行时暂停主页动效”属于已有性能策略，由 performance store 直接读取实际任务状态；它不参与卫星配置／历史的聚合。调度终态统计仍由既有执行入口负责；内部高频只读概览轮询不新增遥测事件。

本节验证：完整后端 1319 项通过、3 项跳过、29 项 subtest 通过，收集到 1322 项测试；前端 160 项测试通过，typecheck、lint、format:check 与 `yarn exec vp build` 通过。后端 lint/format、任务管理器与历史服务 Pyright 零错误，扩大到共享配置／API／schema 的扫描仍有 8 项诊断，与本次改动前文件快照的诊断消息一致，且均不在新增方法内。Markdown、调度 Skill、OpenAPI 字段及生成产物一致性、本次差异检查通过。

Vue 文件均按原组件局部维护规则核对：SatelliteAnimation 505 → 488 行，SatelliteClassic 466 → 451 行，SatelliteHoverLabel 75 → 68 行，未新增界面区域。两个暂缓的前端启动选择文件及来源 TaskBase 字节不变。未启动真实 Electron 桌面环境，未做明暗主题视觉验收或真实游戏／设备运行；构建仍提示已有调度入口混用静态和动态导入，不影响完成构建。

## 39. 配置驱动的候选与本次运行范围

本节对应当前前端适配；前文历史记录中的平铺选择与旧任务下拉接口已由本节取代。

- 不增加专用可选任务 API；移除原 `/api/info/combox/task`。队列、队列项、托管及用户均从配置接口读取，锁状态不决定候选是否可见。
- `SchedulerTaskControl` 只负责目标、运行模式展示及启动／停止；`SchedulerRunScope` 负责一份有序草稿的编辑。队列 A → B → A 的最后一个 A 由自己的队列项 UUID 定位。
- all 表示受理时全部，explicit 表示指定名单，none 表示不运行；显式选中当前所有用户仍不自动变成动态全选。按配置顺序编码，空选择不发送请求，配置失效显式提示。
- `TaskItem.info.name` 由 L1 完整受理时生成名称快照；队列名或直接托管名来自同一根，查询、WS 和刷新恢复一致。运行 UUID 只作运行身份，不能代替原配置 UUID 或名称。
- 首页、托盘、桌面助手也使用同一要求树构造器；旧专项的单 UUID 配置入口局部保留并标注兼容。
- 统计继续由公共请求包装器记录受理结果；范围操作复用既有有限维度，配置查询、勾选和浮层开合不增加事件或业务 ID。
- 浮层沿用 Ant Design，常规窗口按下方空间限高，低窗口改向侧方展开，组标题随列表滚动保持可见；支持明暗主题、小高度窗口、加载、错误和失效配置提示。


本节验证：后端 1319 项通过、3 项跳过、29 项 subtest 通过，收集 1322 项；前端 172 项测试通过，lint、typecheck、format、构建及 E2E 入口校验通过。调度相关浏览器 7 项通过，覆盖候选读取、A → B → A 最后一次独立选择、清空禁止启动、禁用用户仍可选、删队列后刷新保持任务名称；此前完整隔离 General 流程还验证执行日志、锁冲突、中止释放、成功与失败收尾。浏览器明暗主题及 480／720px 高度均已人工查看截图。无真实游戏、账号或模拟器运行。

额外运行的两条设置页用例仍查找旧的 Hide the close button 控件，当前页面已采用关闭确认设置，故未通过；相关测试和设置组件与本任务起点相同，未扩展修改该页面。构建仍有既有动态／静态混合导入提示。后端两处核心模型／管理器 Pyright 零诊断，CSS 变量审计无未定义项，OpenAPI 生成的三个文件与生成目录一致。来源 TaskBase 保持字节不变。

组件范围按本次开工快照计：SchedulerTaskControl 653 → 156 行，范围业务抽出为 SchedulerRunScope（356 行）。index.vue 555 → 542 行与 Scripts.vue 995 → 989 行仅调整连接和调用签名，仍超 500 行，未加入独立业务区域。本地一次性流程脚本与截图归档在 .dev/task-scope-evidence，未放入提交范围；未提交或推送。


## 40. 恢复原有调度布局并导入安装目录数据

上一轮范围适配同时改写了控制卡片及控件分布，按确认要求撤回这部分样式调整。页面头部、标签页、总览／日志面板的布局与样式原本未改变，本次继续保持。控制栏恢复原有 control-card／control-row、左侧 a-space、弹性间隔与右侧 a-space；任务选择框回到 200px，继续起点恢复在右侧的 260px 选择框，启动／停止按钮仍在最右。

- SchedulerTaskControl 恢复卡片外边距、圆角、阴影、背景、运行信息字号与移动端排列；本次从 156 行到 228 行，仍低于 500 行。
- SchedulerRunScope 保留新要求树，恢复原 460px 浮层和紧凑横向托管／账号分组；从 356 行到 314 行。不再采用侧向浮层、独立大标题、竖排用户及吸顶分组标题。
- resumeOptions 用队列项 UUID 定位每次出现；resumeFromUid 从现有草稿派生；onResumeChange 直接修改同一草稿的 all／explicit／none 选择，不恢复平铺的继续起点存储或第二份用户数组。
- 已从 C:/Program Files/AUTO-MAS 复制配置、当前托管数据及历史到 .dev/installed-scheduler-data，7 个托管、4 个队列均通过真实配置接口读取；不复制历史脚本备份池、Temp 恢复记录和缓存。38 个无读取权限的历史图片附件跳过，导入清单位于 .dev/scheduler-installed-import.json。原安装目录配置 SHA256 保持不变。
- 测试副本关闭启动／定时／循环、通知、签到、遥测、自动更新及虚拟显示器；调试后端 36174 已改为使用该副本，前端仍为 5174。未启动真实任务或设备。
- 使用安装数据的浏览器验证通过，明暗主题截图已查看；测量得到选择框 200px、卡片外边距 16px、圆角 12px，验证继续起点选择 A → B → A 的最后一个 A 时只编码该队列项。创建请求在浏览器拦截，后端运行根始终为空。截图与一次性脚本保存在 .dev/scheduler-layout-evidence，测试目录不保留一次性脚本。
- 复用原请求统计边界，恢复布局及导入本地副本不增加遥测事件；前端 172 项单测通过，lint、typecheck、format 和 E2E 入口检查通过。只改调度控制／范围两个组件及本说明，没有后端业务或生成契约改动。


## 41. 本次运行范围改为大面积弹窗

按新的界面要求，将范围编辑从 Popover 改为 1120px 宽的 Ant Design Modal，参考早先的分组标题、逐组选择、用户计数和“从此处开始”样式；用户区域使用自适应多列。选择仍即时更新同一要求草稿，关闭不会丢失选择，也不新增另一份提交状态。原控制栏与主页布局文件保持字节不变，右侧继续起点继续读取同一草稿。

弹窗复用共享 appOverlays 的窗口控制区预留。标题、说明、工具栏及底部关闭按钮不参与滚动；只有 scope-entries 列表持有垂直滚动，弹窗体保持 min-height:0 和 overflow:hidden。列表支持滚轮与键盘、预留滚动条槽位并限制滚动链，长用户名换行，复选框对齐首行，失效／禁用／天数不足状态保持原选择语义。无标题栏窗口也有独立高度上限。

styles/scrollbar.css 已有统一的明暗主题滚动条，但被 style.css 中旧的全局隐藏 !important 覆盖。本次删除旧隐藏及重复外观规则，使用共享滚动条，不在范围组件重复定义浏览器伪元素样式。该清理会让其他正常滚动区域也按共享样式显示滚动条，不改组件分布。

本次组件 314 → 391 行，低于 500 行。浏览器验证使用 18 个托管、648 位用户，覆盖 720／480／300px 高度的明暗主题和 760px 窄窗口；检查单一滚动所有者、无横向溢出、滚轮和 End 键、固定操作、窗口最大化按钮的 IPC stub 可达、无标题栏、加载／失败／重试／空态，以及要求树选择和关闭后保留状态。另以导入配置的独立副本完成真实配置接口显示验证；没有启动脚本、游戏或模拟器，也未宣称原生 Electron 操作的实际结果。

两项本地浏览器流程通过，前端 172 项单测通过，lint、typecheck、format 和构建通过；没有改动后端或生成契约。弹窗开合和只读选择不增加统计，任务请求继续复用原统计边界。截图、滚动测量及一次性测试脚本在 .dev/scope-modal-evidence，测试目录不保留这些脚本。


## 42. 范围弹窗精简文案与放大字号

移除用户旁“未启用／天数不足，执行时判断”等注解、顶部说明和底部规则说明，保留配置失效及请求失败等实际反馈。标题调整为 18px，托管／用户名单为 16px，计数为 14px；复选框按文字首行重新对齐。底部使用统一“确定”文案，选择仍沿同一草稿更新；刷新仅显示图标，保留 aria-label 和悬停提示。控制栏和调度主页布局未改。

组件由 391 行缩减到 367 行。648 位用户长列表浏览器流程通过，包括字号测量、注解移除、仅图标刷新、确认文案、明暗主题与 720／480／300px 高度、滚动、重试和选择保留；172 项前端单测、lint、typecheck、format、E2E 入口检查及构建通过。未改后端、生成契约或统计边界，样式和文案调整不新增事件。一次性脚本与截图在 .dev/scope-copy-evidence，不保留在测试目录。


## 43. 修复分组半选图标叠加

分组头原先把所有非 none 选择都传为 checked=true，导致显式部分选择同时带 ant-checkbox-checked 与 ant-checkbox-indeterminate，叠加选中外观与旋转图形。现在仅动态全选或有效的显式完整名单为 checked，半选只使用 indeterminate；不覆盖 Ant Design 的图标 CSS。点击半选框会按标准行为全选当前组。

改前浏览器复现确认两类同时存在；改后验证中间态仅存在半选类，伪元素矩阵无旋转，并验证全选、未选、逐项全选及关闭重开后的状态。明暗主题已查看，前端 172 项单测、lint、typecheck、format、E2E 入口检查与构建通过。组件从 367 到 373 行。截图及一次性脚本在 .dev/scope-checkbox-evidence，测试目录不保留该私有配置验证脚本；没有后端或统计变更。


## 44. 队列布尔设置采用来源按钮

引入 refactor/plugin-migration-v3 的 SettingToggleButton，保持来源 props、更新／change 事件、蓝色启用／红色禁用样式、加载／禁用保护和 aria-pressed 语义；仅将翻译键适配为当前 core.comp 命名空间。队列定时与循环使用该组件，仍独立保存；定时项状态由原选择框改为小尺寸按钮；额外脚本组件仅在 queue scope 使用按钮，其他调用方继续原开关。布尔值没有恢复为队列类型枚举，启动策略仍是三值枚举。

QueueTriggerSettings 和 ExtraScriptSection 根据当前表单使用 middle 尺寸，定时行使用 small，组件默认 large 与来源保持一致；不重新分配页面各区域。字段继续走 queueApi／useTimeSetApi 及原保存／回滚链，重用既有统计边界，不新增按钮点击事件。

组件行数：QueueTriggerSettings 126 → 139，TimeSetRow 123 → 119，ExtraScriptSection 165 → 182，新 SettingToggleButton 83，均不超过 500；不修改队列主页大组件。队列持久化 E2E 改为按按钮 aria-pressed 验证状态，并保留定时／循环同时启用、关闭定时后的禁用以及刷新恢复检查；queue-bool.pw.ts 覆盖拒绝保存回滚、加载防重复请求、定时行失败回滚、空格键切换、明暗主题和窄窗口不重叠。两个浏览器流程通过，原安装配置未使用或执行，无真实脚本／游戏运行。截图保存在 .dev/queue-bool-evidence。


本节最终验证：来源 SettingToggleButton 除命名空间／格式外文本一致；两个队列流程通过，172 项前端测试、lint、typecheck、format、E2E 入口检查和前端构建通过，CSS 变量无未定义项。新组件与三个适配组件均低于 500 行，队列主页文件保持未改；无后端或生成客户端改动。


## 45. 纠正队列表单控件高度

上一轮主动给布尔按钮设置 middle（32px），并误判路径选择器也是该尺寸；实际 PathPickerField 使用 large（40px）。本次去掉这些 middle 覆盖，恢复 SettingToggleButton 的来源默认 large；QueueTriggerSettings 的启动策略、间隔、时间展示和重置按钮也显式使用 large，与页面其余表单统一。定时表格中的 small 状态按钮继续与同排 small 输入保持一致，没有修改来源按钮的 CSS 高度。

队列前后脚本区域只补充窄窗口分栏／换行，避免恢复 88px 最小宽度的大按钮后挤压路径选择器；常规桌面仍为 4／20 分栏，其他 scope 的排列不变。浏览器新增实际尺寸断言：七个触发表单控件、前后脚本按钮及路径输入框均为 40px；窄窗口无重叠，保存／失败回滚和键盘操作仍通过，两条队列流程通过。截图在 .dev/queue-height-evidence。组件行数已核对低于 500，没有后端或统计改动。


## 46. 调整队列设置分组与顺序

确认第一排为启动时执行、定时执行、循环执行、完成后操作（含延时）。常规窗口四项同行，窄窗口将完成后操作与延时整体换行，保持 40px 控件高度；不再挤压下拉框。其后依次为定时列表组、循环设置组、任务列表、额外脚本组。

- QueueTriggerSettings 负责顶部四项及其实际字段保存；完成后操作与延时从主页移入该组件，不再保留主页的第二份草稿、选项和保存转发方法。
- 新 QueueCycleSettings 独立承接间隔、上次／下次运行、重置计时和保存；读取原 Cycle 字段，使用原 queueApi 及日期格式化能力，不更改循环触发语义。
- index.vue 按 Info.TimeEnabled／CycleEnabled 条件挂载两个组。禁用时整个组消失，后台配置不删除；两种触发可同时启用。任务列表保持显示，额外脚本移到最下方并沿用原字段保存与禁用保护。
- 主页由 1039 行减至 901 行（HEAD 为 1116 行），仍超过 500 行；仅抽出受影响的循环表单及完成后操作职责，保留其他既有管理逻辑。顶部组件由 148 到 156 行，新循环组 116 行。

两条队列浏览器流程通过：断言组的实际垂直顺序、顶部四项同行、隐藏／重新启用后定时项状态保留，循环间隔改为 90 后关闭／重开及刷新仍保留；同时覆盖保存拒绝回滚、加载防重复、键盘及 760px 窄窗口控件不越界。明暗主题截图已查看。无真实脚本、游戏或设备运行；统计继续由原请求包装器观察，不新增显示／隐藏事件。截图在 .dev/queue-layout-evidence。


## 47. 完成后操作与延迟分钟拆为独立配置项

外层继续使用原有完成后操作的列宽（常规窗口 9／24），内部拆为两个独立 form-item。NoAction 时只渲染完成后操作并占满内部 24 列；选择其他操作时分别分配 14／10 列，合计仍为 24，不挤占前三项。延迟隐藏不清空存储，切回后读取原分钟数；控件仍为 large 40px。

新增 queue-after-action.pw.ts 检查初始隐藏、操作启用后显示、字段分别提交、隐显后保留、切换前后外层列宽一致及明暗主题。涉及电源动作的选择仅在浏览器响应中模拟，实际后端始终保持 NoAction 和原来的 7 分钟，没有触发电源操作或运行脚本。三条队列流程和 172 项前端测试通过，类型、lint、format、E2E 入口检查与构建通过。组件 156 → 163 行；截图在 .dev/queue-after-evidence，无后端或统计改动。


## 48. 统一队列小标题与执行周期样式

完成后操作／延迟拆分已收尾，保留上一节的列宽与隐显规则。队列顶部和循环设置的表单标签统一为 600 字重，与既有卡片标题、表头和额外脚本标签一致，不改变布局和控件高度。定时列表与任务列表的星期列均命名为“执行周期”，中英日词条同步。

QueueWeekdaysSelect 由两个列表共用，沿用 origin/dev 定时列表的 multiple small、无边框、最多七个标签配置及透明标签／隐藏删除叉号样式。样式由选择器自身持有，修复 TimeSetRow 拆分后父组件 scoped 规则未命中的问题；原 TimeSetManager 中失效的规则删除。两个调用方保留各自的排序、提交和回滚职责，接口与日期语义不变。本次仅展示样式与组件复用，无需新增统计，仍沿用原有请求观察边界。

验证：三条既有队列浏览器回归通过；一次性本地流程通过，检查两个列表在明暗主题下均为透明标签、无叉号和加粗标题，分别取消一个星期并通过公共接口确认保存，刷新仍保留各自选择。已查看桌面明暗截图和 760px 窄窗口截图；窄窗口保留原来的纵向行布局。本地探针及截图归档至 .dev/queue-period-evidence，探针不进入提交。前端 172 项测试、lint、typecheck、format、E2E 入口检查和 vp build 通过；构建仍提示既有调度模块混合静态／动态导入，浏览器输出仍含 Ant InputNumber 的 mask 属性警告。没有运行游戏、脚本或电源动作。

组件规模（HEAD／本次开始／结束）：TimeSetManager 617／588／577，QueueItemManager 747／517／501；二者仍超过 500 行，本次为局部样式维护并抽出重复选择器，均较本次开始缩短，未增加独立业务区域。TimeSetRow 119 → 105，QueueTriggerSettings 163 → 167，QueueCycleSettings 116 → 120，新 QueueWeekdaysSelect 为 53 行。


## 49. 修正分割位置与循环时间展示

定时列表保持 dev 原本居中、不连续的短分割线。实际错位来自行内操作列随内容扩宽约 8px，而表头固定为 120px；TimeSetRow 的操作列改为同样的 120px 并缩减横向内边距容纳按钮。星期列允许缩至剩余宽度并自然换行，避免小桌面宽度下挤出表格。DraggableTableShell 保持原样，没有拉长或连通分割线。

循环设置不再渲染上次执行时间；原 LastRunAt 字段和重置逻辑保留。下次运行用 output 元素纯展示，沿用主题正常文字／背景／边框颜色和 40px 高度，不使用禁用输入框；重置按钮紧邻展示框右侧，合并在同一表单项下。间隔占原 6 列，展示及按钮占剩余 18 列；窄窗口整组换行。保存、错误提示和 loading 仍由原 queueApi 流程负责，展示调整不新增统计。

本地浏览器验证在 1000、1280、1440px 下逐列比较表头与内容边界，相差均小于 1px；恢复短分割线后再次通过。已查看明暗主题和 760px 截图，纯展示文字保持正常颜色，按钮与展示框等高且不溢出；重置请求成功。三条既有队列回归及一次性本地流程通过，lint／typecheck／format／E2E 入口检查／vp build 通过。没有运行真实脚本、游戏或电源动作。本地探针与证据归档至 .dev/queue-columns-evidence，探针不进入提交。

组件规模（HEAD／本次开始／结束）：TimeSetManager 617／577／577，仍大于 500 行，本次仅修改既有列的最小宽度，没有新增业务区域；TimeSetRow 105 → 107，QueueCycleSettings 120 → 128。共享表格组件与 HEAD 内容一致。


## 50. 状态短分割线、分钟精度与居中删除确认

状态按钮实际高度为 32px，加上原上下内边距后撑满整行，因而其右侧分割线仍连到行边界。仅将状态格上下内边距改为 8px，使边线与其他短分割线一样在上下留空；继续保持上一节的横向列宽修正，共享表格仍为原实现。浏览器在 1000／1280／1440px 下同时验证列边界对齐和状态格上、下至少 3px 空隙。

Cycle.NextRunAt 由上次真实触发时刻加间隔后截到本地分钟，秒与微秒为零，timer 直接使用该虚拟值判定；LastRunAt 仍保留真实受理时刻。UI 元数据使用 hm，页面按本机时区展示 YYYY-MM-DD HH:mm。无新增参数、字段或 HTTP 结构。新增边界回归先在旧实现失败，再验证整分钟前不触发、整分立即触发、同分钟不重发；16 项相关后端测试通过。

下次运行与“重置”合为一个 40px 外框，按钮仅保留内部左分割线；与间隔使用相同响应式列宽，不占满剩余整行。上次执行时间继续隐藏，下次时间仍用正常主题文字纯展示。重置沿用原 Trigger 提交，没有额外计时状态。

队列、定时项、任务项的删除统一用 QueueDeleteButton 的 480px 居中确认弹窗；通过 Modal.useModal 继承主题上下文，取消不提交，确认沿用原删除函数。既有全局遮罩／窗口控件预留规则继续生效。queue-delete.pw.ts 作为公共删除确认边界回归保留，覆盖三种对象的取消无请求、确认一次请求及刷新删除结果；样式探针留在本地。统计继续由既有请求入口负责，不上报弹窗展示或取消。

三条既有队列回归通过，删除回归与本地布局／弹窗流程通过。已查看明暗主题、760px 窄窗口和 720／480／300px 高度下的弹窗；检查标题栏命中并通过浏览器桩确认最大化点击仍送达。证据与临时探针归档至 .dev/queue-minute-evidence。当前用户测试后端正在执行任务，未重启或打断；后端分钟判定需下次重启加载，隔离后端已验证新实现。

组件规模（HEAD／本次开始／结束）：index.vue 1116／901／896，仍超过 500 行，本次仅替换现有删除入口且缩短；QueueItemManager 747／501／496，TimeSetRow 107 → 102，QueueCycleSettings 128 → 137，新 QueueDeleteButton 38 行。

最终检查：lint、typecheck、format、E2E 入口检查、CSS 变量审计及前端构建通过；pytest 全量收集通过。


## 51. 锁等待状态、日志与占用者

L2 取托管锁时保持托管节点“等待”，L3 实际进入 main_task 后再置“运行”；L3 在尝试用户锁前先将 current.index 指向对应用户，L4 实际启动后才将用户置“运行”。兼容旧 manager 的等待同样使用“等待”，其首次派发下一层旧任务时再切为“运行”。TaskBase 和配置锁机制保持原样。

三处等锁循环在第一次冲突及等待消息变化时，把等待配置名称和占用者追加到托管 current.log，并在所属协程提交。既有模型订阅负责 task.info.updated 与 task.log.updated，无独立发布队列或新 WS 类型；一秒一次的取锁重试不重复追加相同日志。用户等待时当前指针已切换，日志可按当前节点路径推到前端。

TaskManager.describe_lock_holders 只读当前配置节点实际 S／X token，并与运行执行器现有票据匹配：L2 托管锁、当前 L3 用户锁、旧 manager 的 config_locks。ScriptExpander 的 _plugin 仅保留实际执行中的 L3 引用，供查询现有用户票据，结束后清理；不另建锁登记或在公开信息树增加字段。可识别时写任务名称和运行 UUID；未登记占用写“其他配置操作（占用者未知）”，不凭同一托管的运行状态推测占用者。级联申请会检查全部覆盖节点，因此不会把某个未关联的用户锁误记为托管本体锁持有者。

新增 test_task_lock_waiting.py 覆盖插件及旧专项争用、已知占用者、重复重试日志去重、WS 正文、运行状态切换、未知 S 锁占用、等待取消和只释放自有锁；同步调整原有取消／配置删除测试，等待原因从日志断言，不再作为状态文案。全量 pytest：1324 passed、3 skipped、29 subtests passed；9 个涉及文件的 Ruff 检查通过，5 个后端实现文件的 Pyright 为 0 错误、0 警告。请求树复制改为保持原顺序的逐项复制，消除 Mapping 联合类型对 dict 构造重载的静态诊断，创建契约不变。日志未新增匿名统计，继续复用任务生命周期观察。证据在 .dev/task-wait-evidence。

运行验证：用户任务自然结束后，确认没有到期排期才重启测试后端；health 为 ready，运行任务数为 0，已加载的新循环计算导出的 NextRunAt 秒数为 0。测试配置与触发开关保持原值。

## 52. 调度台前端数据链路简化

原页面同时维护公共运行缓存、标签运行副本、日志缓冲、概要 ref 和启动事件暂存；WS 先到、HTTP 后返回时，合并标签会清空已收到的启动／等待日志。本轮改为公共运行对象唯一持有信息、日志和序号，标签只绑定 UUID，页面只负责交互和展示。HTTP 受理不再重置先到数据；快照与日志分别对账。后端调度、接口契约、运行范围设计和现有布局未变。

受影响的调度实现合计由 3076 行降至 2300 行（含新增拆分文件，不含测试）；页面控制器由 1520 行降至 235 行。组件“本轮开始 → 完成”：index.vue 542 → 498，TaskOverviewPanel 148 → 91，SchedulerLogPanel 321 → 366；新增 SchedulerRunPanels 73 行。运行模块 444 行、标签 store 256 行、应用反馈 215 行、日志协议处理 55 行。不是通过把旧控制器原样搬到新文件来缩小页面。

验证结果：33 个文件共 178 项单元测试通过；7 项浏览器流程通过，覆盖 WS／HTTP 两种先后顺序、等待日志、后续追加、切页继续收集、刷新恢复、漏包补快照、停止终态、原调度保护和四项队列回归。补充明暗主题截图核对，主题切换等待动画结束后样式正常。浏览器通过隔离 E2E 入口，仅使用空队列与受控任务响应，没有启动真实脚本、游戏或模拟器。

typecheck、lint、format、E2E 入口检查、CSS 变量审计和 `yarn exec vp build` 通过。lint 保留已有 QueueDeleteButton.text 缺少默认值警告，本轮未修改该组件。后端及生成客户端未变，未重复执行后端全量测试；此前后端锁等待验证记录见第 51 节。完成日志留存仍限于当前应用缓存；刷新后无法从仅列出活动任务的接口重建已经结束的完整结果。

本地证据归档在 `.dev/scheduler-simplify-evidence`，原始检测日志及改前快照留在 `.dev`，不进入提交。没有创建提交、推送或 PR。

## 53. 旧专项启动前等待日志恢复

前端启动合并简化修复了 HTTP 返回时清空早到日志的问题，但没有解决后端来源选择：MAA 在启动模拟器前已建立一个空用户日志记录，原有推送优先选择该记录，忽略旧专项通过 `script_info.set_log()` 写入的启动、更新、等待退出等流程提示。因此前端收到的第一条非空日志仍然可能是 MAA 原生日志。

`TaskItem.current_log_source()` 在旧 manager 承接期间复用已有兼容标志，使用托管 `current.log` 作为展示来源；专项继续按原写法更新原生日志记录并镜像展示，无需逐专项改调用或添加另一套日志状态。插件链保持直接读取当前用户 LogRecord。HTTP 快照、虚拟 current.log 和 WS 增量均使用同一来源，用户记录仍保存原始正文，不被流程提示覆盖。

MAA 的 prepare 在配置 X 锁之前还可能等待安装写入互斥与安装访问锁，这两处此前没有流程日志。本轮在真实等待处补提示，安装访问锁复用既有 progress 回调且争用期间只报告一次；没有可靠占用者信息时明确显示未知，不增加锁登记或改变取锁、释放和取消规则。

新增的公共日志回归在修复前失败，修复后通过。MAA 隔离验证执行真实 main_task 的建记录／提示／启动顺序，设备 open 保持挂起，确认原生日志为空时已有非空 WS 日志与相同 HTTP 快照；另覆盖安装写入等待、访问锁提示去重、取得锁及取消退出。没有启动真实模拟器、MAA 或游戏。等待日志不进入匿名统计，继续复用既有任务生命周期观察入口。

本轮验证：全量 pytest 为 1329 passed、3 skipped、29 subtests passed，耗时 197.76s；5 个涉及文件的 Ruff 与格式检查通过。Pyright 的 MAA 旧实现基线和修复后均为 76 条已有诊断，对照无新增诊断，运行模型文件无诊断。测试输出与前后静态诊断留在 `.dev/wait-log-*`、`.dev/maa-wait-log.log`。确认调试后端空闲且队列自动触发均关闭后，经正常关闭接口重启，继续使用原导入测试数据；未启动真实专项。

## 54. 提交前同步 dev 与冲突适配

本次同步基线为 `origin/dev` 的 `76eac7930`，保留上游 MCP 可选服务拆分、专项程序更新、定时唤醒和托管／账号展示语义。新调度模式、要求树、运行 UUID、L2 兼容分叉及 timer 所有权继续遵守本文主干，没有恢复旧循环会话、旧任务参数或目录预约器。

上游新增的专项更新进度与异常状态改用运行模型的提交方法；MaaEnd 更新准备已持有的配置锁在 prepare 中复用，不重复等待自身。SRC 的原生安装访问保护从已锁定的热态路径建立。用户配置预处理返回的 guard 在提交保护范围内复核，保留上游并发编辑保护。

MCP 服务自行长期持有加载 Task 并负责停止收尾；MaaEnd 资源预热沿 BackgroundTaskManager 挂载，没有重新引入 RuntimeTasks。定时唤醒改读 LastStartTime，定时与循环开关独立，开启循环不移除已启用的定时唤醒。唤醒启动沿用 dev 的定时补跑与普通启动队列分流。

浏览器刷新验证发现，本地 Monaco 空闲预热尚未完成时挂载日志编辑器会启动 CDN 加载。日志组件现复用本地初始化 Promise 后再挂载，页面其余内容不等待；组件规模为 372 行。运行回归主动阻断远程 Monaco 请求，检查两种启动顺序、刷新、切页、漏包恢复和停止结果。上游新增队列 UI 用例保留创建、拖排、范围选择和删除验证，已有触发设置验证独立保留。重连与真实运行验证按 config_id 查业务对象，按运行 UUID 定位运行节点。

合并后 Windows 全量后端回归为 1262 passed、1 skipped、15 subtests passed；前端 46 个文件共 246 项测试通过。保留的 Pydantic 依赖弃用警告不影响运行；未执行真实账号、MAA、游戏或模拟器验收。类型、格式、构建与浏览器验证的原始记录在本地 `.dev/pr-*`，不进入提交。
