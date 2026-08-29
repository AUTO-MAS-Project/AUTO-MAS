---
name: mas-script-specialized-adapter
description: >-
  Review, add, or refactor AUTO-MAS specialized script adapters by upstream
  architecture, including MAA, SRC, MaaEnd/MXU, M9A/MFAA, General, ok-script
  adapters such as Okww and OkNte, and multi-engine adapters such as HSR. Use when
  lowering user setup friction, deciding whether MAS should fill a script
  capability gap, or changing ScriptType registration, task lifecycle, config
  ownership, ScriptConfig sessions, Electron integration, frontend edit
  surfaces, and verification.
---

# 专项适配

本 Skill 只写**读代码推不出来的东西**：判据、陷阱、不变量、产品意图。文件清单、字段枚举、端点签名一律现场 `rg` / 读代码确认，不在文档里维护副本——文档里的事实表会过期，过期的表比没有表更危险。

## 核心要义

专项适配不是把外部脚本字段逐项搬进 MAS，而是围绕用户完成任务的最短路径做产品化承接。每次适配先回答两件事：

1. **降低用户使用门槛**：优先消除安装导入、路径选择、首次配置和高频任务编排中的手工步骤。不要把上游原始配置面板原样搬进来当作完成。
2. **必要时由 MAS 补位**：脚本原生能力完整稳定时优先调用脚本；脚本无法提供而 MAS 能可靠编排的能力，才在适配层补足。补位只负责用户价值和调度编排，不复制脚本引擎，也不重复暴露脚本已有的权威设置。

**若一个改动既没减少用户手动步骤，也没补足明确的脚本能力缺口，先停下来重新确认范围。**

能力 owner 判定（决定代码放哪、谁是事实来源）：

| owner | 判定 | 实施规则 |
| --- | --- | --- |
| 脚本原生 | 已有稳定入口、配置、结果判定 | 复用脚本能力；脚本配置是唯一事实来源 |
| MAS 适配层 | 脚本有能力但入口分散或难安全调用 | 最小封装（路径发现、默认值、配置会话、原子写回）；不建平行配置模型 |
| MAS 补位 | 脚本明确无法提供，MAS 能依稳定数据可靠完成 | 在 manager / AutoProxy / 计划层实现，必须有输入、失败提示、回退、清理 |
| 暂不支持 | 需猜上游内部状态或无法稳定验证 | 显式提示限制，**不加运行时不消费的字段** |

## 开工顺序

0. 列出用户当前的手工步骤与脚本明确缺失的能力，标注 owner。
1. 读上游仓库/发行版：CLI、`--help`、进程、日志、配置目录、配置 UI。
2. 按 [架构线判据](references/script-frontend-architectures.md) 归类，**让用户确认架构线**后再动手。
3. 读 [代码规范](references/adapter-code-norms.md)（必遵守）+ 对应案例：
   [SRC](references/examples-src.md) ·
   [MaaEnd/MXU](references/examples-maaend.md) ·
   [M9A/MFAA](references/examples-m9a.md) ·
   [Okww](references/examples-okww.md) ·
   [OkNte](references/examples-oknte.md) ·
   [HSR](references/examples-hsr.md)
   需要画面文本识别（登录/切号/按钮定位）时另读 [OCR 工具](references/ocr-tools.md)
4. 现场反查全部注册调用者与相邻实现，再定最小改动。**不要从旧 Skill 文案推断当前行为。**
5. 用用户场景验收：少了哪段手工配置？补位有无明确输入、失败提示、回退路径？

前端任务同时加载 `mas-frontend-standards`；涉及 UI、表单、遮罩、反馈时再加 `mas-frontend-ui`。

## 落点自查

新增 / 维护 `ScriptType` 时按需核对下列切面（**具体文件现场 grep 确认，不要照文档抄路径**）：配置与 schema、注册与 API（含 `TYPE_BOOK` 展示文案，漏则调度 KeyError）、任务模块、前端入口（Hub 分支 + 路由 + 创建流片段 + 类型 + 编辑页）、Electron 能力（仅当需注册表/文件系统/进程发现）、OpenAPI 生成代码（**禁止手改**）。

**不要机械要求所有类型拥有相同文件**——先确认架构契约，再补真实调用链。

- 配置与 schema：`app/models/config.py`、`app/models/schema.py`
- 注册与 API：`app/core/config.py`、`app/api/scripts.py`、`app/core/task_manager.py`、`app/utils/constants.py`
- 任务模块：`app/task/Xxx/` 的 `manager`、`AutoProxy`，按架构需要增加 `ScriptConfig`
- 日志采集推送：需要把脚本运行日志关键节点推送至任务报告时，用通用组件 `log_box`（用法见 [logbox-api.md](references/logbox-api.md)），专项只喂参数（日志路径/规则/处理器）并注入 sink；报告聚合与追加复用通用工具 `app/tools/push_log.py`（`build_user_result_text` 按用户交错组装「用户结果行+节点」并入 result / `append_push_log`），专项不要自行拼接实现。「是否展示节点详情」由专项（或其用户配置）的开关在**是否创建/启用 log_box 的入口**消费（关闭即不创建，省采集开销），不要给 log_box 加通用开关，也不要在聚合层采后过滤（参考 okww 用户级 `Notify.PushLogEnabled`）
- 视觉识别：专项需要画面文本识别时，**新逻辑用共享工具 `app/tools/ocr.py`**（用法见 [ocr-tools.md](references/ocr-tools.md)），交互层（截图/激活/点击）专项自持；MaaEnd 登录仍为历史私有 OCR，未迁移前不强制改造
- 前端入口：`Scripts.vue`、`ScriptTable.vue`、router、`types/script.ts`、相关 composable、脚本/用户编辑页
- Electron 能力：仅当需要注册表、文件系统或进程发现时增加 `electron/services`、IPC、preload 与类型声明
- 生成代码：后端 schema 变更后运行生成器，禁止手改 `frontend/src/api/**`

## 审查方法

1. 从 `ScriptType`、任务注册、UI 入口**反查全部调用者**。
2. 对照运行时实际读取的字段查 config / schema / 生成类型 / 表单：**schema 里存在但运行时不消费的字段不是功能，是债**。
3. 自动发现、手动选择、后端 `check()` 三条路径判定：同一资源必须用**同一组哨兵文件**。
4. 配置会话的启动、WebSocket 状态、停止、超时、卸载、异常六条路径：确保任务结束、进程退出、锁释放、配置写回。
5. `final_task` / `on_crash` 的原子配置恢复、用户状态落盘、独立进程清理。
6. 按 `tests/AGENTS.md` 本地编写并运行最小专项测试验证改动；提交时功能/bug 边界测试不提交，**测试缺口写进结果，不编造验证结果**。
7. 反查产品边界：没重复实现脚本已有能力，没把 MAS 补位伪装成脚本原生字段，没为"字段齐全"加无价值入口。

## 配置来源模式：按专项确认，不存在统一三态

这是最容易被错误套用的一处。来源模式由真实配置 owner 决定：

| 专项 | 模式 |
| --- | --- |
| Okww | 脚本 / 用户 / 直控 三态 |
| General | 用户 / 直控 两态 |
| MaaEnd | 脚本 / 用户 两态 |
| OkNte | 两态（`Info.Mode` 简洁 / 详细） |
| M9A | 不使用这套模式 |

采用三态时：**脚本**=脚本级共享配置；**用户**=当前用户独立配置；**直控**=直接使用脚本原有配置、由原生 GUI 维护、不回写 MAS 独立配置。三态只决定 owner。

**不要为了界面或术语对齐机械增加"直控"或第三态。** 若专项有"快速配置"，它是独立覆盖层：开启时只用面板高频字段覆盖当前配置，关闭时保留来源配置的完整任务设置。运行前必须备份原配置，成功/失败/取消/超时/异常五条路径都要恢复或按已确认策略回写。

## ok-script 家族：两种并行范式

`ok-script` 是脚本家族，不是单一专项。家族级原则可复用，但 CLI、配置目录、原生 GUI、任务语义必须**逐子项目确认**。当前 Okww 与 OkNte 同用 `-t N -e`，但配置方案是两条并行且都有效的路：

| | Okww | OkNte |
| --- | --- | --- |
| 字段来源 | 静态可确定 → 固定 schema | 上游打包后源码不可读 → 从 JSON 值动态推断类型 |
| 中文标签 | 写在 config / 前端 | 从安装目录 `.po`/`.mo`/`.ts` 自动加载 |
| 配置入口 | 仅 ScriptConfig 遮罩（调本体 GUI） | 动态表单经 REST 端点直读写 + ScriptConfig 遮罩，**两条并存** |
| 来源模式 | 三态 | 两态 |

**选型判据：上游字段可静态确定 → Okww 式；上游打包不可读、字段随版本漂移 → OkNte 式。** 两者都不是禁止项，审查任一专项时不得用另一方的标准判其违规。

各自陷阱见 [examples-okww.md](references/examples-okww.md) 与 [examples-oknte.md](references/examples-oknte.md)。

## HSR：唯一的一对多专项

`HSR` 是唯一「一个 `ScriptType` 编排两个上游程序」的专项，不要按其他线的一对一心智读它。只有当上游确实需要多个可互换引擎协同完成同一批任务模块时才归入此线；单一上游即使功能复杂也不属于。

- 编排 M7A 与 SRA 两个独立发行物，各有原生配置，两个路径可只配其一。
- **没有** `ScriptConfig.py`，没有原生编辑器遮罩会话；不要按 MAA/MaaEnd/Okww 的配置会话模式改造它。任务模式只有 `AutoProxy` 与 `ManualReview`。
- 任务模块在 `task_mapping.py` **单点声明**，配置项、`check()` 校验、能力快照的 tasks 全从这里派生；新增模块只改这一处。
- 引擎分配四级回落，每级取值都要过 `supported_scripts` 校验。
- 托管字段由后端定义下发、前端动态渲染；**新增字段扩展后端定义，不在 Vue 里加硬编码分支**。
- 直接读写两个上游的真实配置：任务前备份，`final_task` 与 `on_crash` 都要原子恢复。**备份清单中 `existed=False` 的目标在恢复阶段需删除任务期新增路径，而不是跳过。**
- 路径锁防止多脚本或直控导入并发操作同一安装；冲突抛错要转成可读错误而非静默等待。
- 关卡字段存脚本原生字段 JSON，**不建 MAA 式统一关卡词表**。
- 切号统一走 SRA StartGame（M7A 模块也依赖该登录路径）。

完整陷阱见 [examples-hsr.md](references/examples-hsr.md)。

## 验证

按 `tests/AGENTS.md` 选被改专项的最小测试入口。没有对应测试时**不为填目录新增脚本**，在结果中说明测试缺口。仅在实际涉及前端时才从 `frontend` 跑前端最小测试；跨模块契约或用户明确要求时才扩大范围。文档修改至少用 `rg` 确认不存在相互冲突的旧规则。
