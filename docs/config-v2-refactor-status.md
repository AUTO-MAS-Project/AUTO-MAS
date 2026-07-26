# Config v2 重构现状报告：已做 / 未做 / 怎么接着做

> 生成时间：2026-07-26。基于四路只读调研（外部框架归档、项目配置现状、插件系统现状、前端现状）。
> 目的：给后续参与者（人或 agent）划清边界，**避免重复造轮子**。
> 工作树：`D:\AM6R`（detached @ aceb651a，384 脏文件，禁 commit/打包）。

---

## 〇、最重要的一句话

**用户提供的 `config_framework_v2` 归档，其核心思想已经以生产化形态进入本项目**：
`app/configuration/v2/` 自述"基于 config_framework_v2 参考实现"，并且**默认模式就是
authoritative（v2 原生权威）**，全套 539 项配置测试通过。

因此"将配置基类替换为新版本"这个任务 **不是从零开始，而是收尾清理 + 增量补齐**。
任何人从 `config_framework_v2_archive_20260722-153123 (1)` 重新向项目移植框架本体，
都是重复造轮子，且会做出一个**功能更弱**的版本（归档版没有原子写、没有世代存储、
没有加密 entropy 绑定，见下文对照表）。

---

## 一、已经做完的（有证据，勿重做）

### 1. v2 配置内核（= 归档框架的生产化超集）

位置：`app/configuration/v2/`。与归档逐项对照：

| 能力 | 归档 config_framework_v2 | 项目内 app/configuration/v2 |
|---|---|---|
| 基类体系 Collection→Entry→Group | 有 | 有（同构） |
| pydantic 2 校验 / Annotated 字段类型 | 有（11 内置类型） | 有 |
| blinker 信号 FieldChange/CollectionChange | 有 | 有，且分 validator（可否决）与 after-commit（不可否决）两相位 |
| Virtual / Trigger / Ref / encrypted 字段 | 有 | 有（shortcuts.py 同名工厂） |
| 事务 | 有（COW workspace） | 有，加 owner-task 校验、Init 事务、snapshot_barrier |
| TOML 落盘 | `write_text` 直写（**无原子写**） | 临时文件 + fsync + 原子替换 + 备份 |
| 持久化形态 | 每根一个 TOML 散文件 | **世代仓库** `.config-v2-authoritative/`：CURRENT 指针 + 不可变世代目录 + manifest sha256 + CAS |
| 崩溃恢复 | 无 | fail-closed（损坏即 GenerationRecoveryRequiredError，`.pending-*` 永不自动选取），6 个注入故障点有认证 |
| 加密 | DPAPI 明文前缀 | `DPAPI:v1:` + 应用绑定 entropy + 旧密文自动 rewrap + 内存常态密文 |
| 回滚 | 无 | 四模式开关 + `export_r6_rollback_bundle()` 导出 r6 JSON |

### 2. 八生产根 schema 全部迁移完

`app/configuration/roots/`：Config、EmulatorConfig、PlanConfig、ScriptConfig（多态 8+1 类，
含 PluginScript）、QueueConfig、ToolsConfig、PluginConfig、GameSignAccounts。
每根带 legacy JSON ↔ wire 双向纯函数。**"根据项目使用字段补充预设字段"这条要求，
对这八根而言已经完成**——完整字段权威清单见调研报告 §3（约 500+ 字段），不需要再挖。

### 3. authoritative 已是默认生产路径

- `AUTO_MAS_CONFIG_V2_MODE` 默认与非法值回退均为 authoritative；正式链**不再构造 legacy 图**。
- 首启迁移：冻结 r6 原始快照（sha256 manifest）→ 纯转换 → 单事务激活八根 → 提交首世代；
  之后永不回读可变 legacy JSON。
- 两阶段提交：`configure_prepare_commit_hook` → 世代 CAS 提交成功后才内存 COMMIT → outbox。
- WS 推送：事务提交后经 outbox 发 `config.changed`（加密字段不带值）。
- 门面：`app/core/native_config.py`（NativeConfigFacade，约 90 个业务方法）保持
  `get/set/set_many/toDict`、`ScriptConfig[uid]` 等旧 API 面，60+ 后端模块零改动。
- 测试：`tests/configuration` 539 passed + 81 subtests；含 cert 认证套件
  （原子写故障、事务故障、outbox 故障、损坏恢复、加密暴露、迁移 round-trip、回滚矩阵）。

### 4. 插件配置的 v2 承载已存在（但不是目标形态）

PluginConfig 根（`roots/plugin_config.py`）承载插件实例列表，实例配置是
`Data.ConfigRaw`（JSON 字符串，可加密）+ `Data.Config`（虚拟校验投影）。
——注意：这是**现状**，目标形态是 `config/plugins/<插件名>.toml`（见"未做"）。

---

## 二、还没做的

### A. Config 替换任务的收尾（旧任务余量）

1. **真实机 GUI 回归**：旧 profile 首迁、保存/重启、任务停止、后端重启、窗口关闭、
   连接替换——已转交另一台 Windows 真实机，待回传（unverified）。
2. **legacy 清理**：`app/models/ConfigBase.py`（1845 行）、`app/models/config.py`（3212 行）、
   `app/core/config.py`（3773 行）仍在，仅供 off/shadow/canary 与存量反序列化。
   何时删除取决于是否保留模式回退逃生门，需要决策，不要擅自删。
3. **游离 MultipleConfig 残留**：`app/task/{MAA,M9A,general}/manager.py` 在 authoritative
   下构造不落盘的 legacy 内存视图（非双权威，但属技术债）。
4. 当前用户文档与迁移说明（docs/experimental-alpha 是历史证据，不能改写）。

### B. 本轮新需求（18 条要求）中全新的部分

1. **UI 组件提示虚拟字段**（要求 3）：两边都没有。归档无字段级 UI 元数据；项目内
   schema 下发走的是另一套（PluginSchemaManager / script_adapter_schema 双管线 +
   前端 SchemaForm 12 列 grid）。需要新写 introspect 层：从 Entry 的
   `model_fields` + `_cfg_virtual_specs/_cfg_trigger_specs/_cfg_ref_specs` 反射出
   组件提示字典（键=组名，值=组件提示列表：组件类型、可选项值；无文案、无宽度；
   触发器→button）。纯增量，不动 v2 内核。
2. **插件系统重设计**（要求 4-18）：现状 `app/plugins/` 约 15,700 行自研体系
   （自研 EventBus、多实例、生命周期状态机、schema 推导、pypi 市场、系统插件白名单），
   与目标形态（单例、blinker 原生、core 核心插件、4 拓展基类、简化 ctx、
   `config/plugins/*.toml`）差距全面，属重写而非修补。
3. **历史记录独立模块**（要求 15.1）：现状耦合在 Config 双门面上（两套实现重复维护、
   写侧硬编码 cwd、`/api/history/data` 无路径沙箱）。抽 `HistoryStore` 全局单例的
   条件成熟：只依赖 history_path、HistoryRetentionTime、用户名三个输入。
4. **游戏管理组件升级**（要求 15.3）：现状 emulator/game_center 是服务槽 + 宿主兜底，
   无"每配置项一个管理实例、进程未释放拒绝删除"的机制。前端删除报错路径已具备
   （非 200 + message 即可直达用户），后端要新做。
5. **前端 i18n 层**（要求 3 的前置）：前端零 i18n 框架，文案全部由后端 schema 下发或
   硬编码中文。按组名+字段名查 i18n 需要从零搭（无迁移包袱，可直接按新 key 约定设计）。
6. **插件配置 → `config/plugins/<插件名>.toml`**：用 v2 基类声明插件配置类、由插件
   系统实例化落盘，取代 ConfigRaw JSON 字符串双层编码。

---

## 三、要怎么做（推进顺序与边界）

### 原则

- **不动 v2 内核**（`app/configuration/v2/`）：事务/信号/世代存储语义被整套认证测试锁定，
  新能力一律外挂（introspect 模块、HistoryStore、插件配置根）。
- **不从归档重新移植**。归档唯一的增量价值是 examples 与设计文档（配置基类.md）可作
  API 语义参考。
- **门面兼容优先**：任何重构不得破坏 `NativeConfigFacade` 的 API 面
  （authoritative_api_cert 逐 endpoint 锁定）。

### 建议推进序（依赖关系）

1. **设计文档定稿**（进行中，见 `docs/design/config-plugin-redesign.md`）——
   覆盖 18 条要求的完整方案，先评审再动手。
2. **UI 组件提示虚拟字段**（新模块 `app/configuration/introspect.py` 之类）：
   独立、无依赖、可先行。产出组件提示字典 + 前端 24 栅格渲染改造 + i18n key 约定。
3. **历史记录独立模块**：从双门面抽出 `HistoryStore` 单例，顺带修 cwd 分叉与
   路径沙箱。低风险、收益立现，可与 2 并行。
4. **插件系统重写**（最大件）：core 插件包 → 4 拓展基类 → 单例加载器（双通道：
   已安装包 entry points + 本地 plugins 目录）→ blinker 信号命名空间 → 简化 ctx →
   `config/plugins/*.toml` → 版本预检查。适配器插件随之迁移。
5. **游戏管理组件升级**：依赖 4 的游戏适配基类定义，排在其后。
6. **legacy 清理与真实机回归收尾**：等真实机结论回传后决策。

### 防重复造轮子清单（做之前先查这里）

| 你想做的事 | 已存在的实现，直接用 |
|---|---|
| 移植/改进 config_framework_v2 | `app/configuration/v2/`（生产化超集） |
| 梳理项目全部配置字段 | 调研报告 §3 + `app/configuration/roots/*.py` |
| 配置原子写/崩溃恢复 | `persistence/generation_store.py` |
| 配置变更推前端 | outbox `config.changed`（已通 WS） |
| 加密字段 | `v2/encrypted.py`（DPAPI v1 + rewrap） |
| 跨根外键/级联删除 | `ref()` + RefDeleteAction（三具名集合已注册） |
| 插件 schema 渲染 | 前端 `SchemaForm.vue` + `schemaFormCore.ts`（字段判定/敏感策略可复用，布局层待改 24 栅格） |
| 服务注册/发现 | `app/plugins/service_registry.py`（重设计中保留语义） |
| 热重载文件监视 | `app/plugins/dev_hmr.py`（保留，监视目标改 `config/plugins/*.toml`） |
