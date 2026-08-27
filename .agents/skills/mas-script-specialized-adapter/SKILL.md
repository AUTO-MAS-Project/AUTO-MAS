---
name: mas-script-specialized-adapter
description: >-
  Review, add, or refactor AUTO-MAS specialized script adapters by upstream
  architecture, including MAA, SRC, MaaEnd/MXU, M9A/MFAA, General, and
  ok-script adapters such as Okww. Use when lowering user setup friction,
  deciding whether MAS should fill a script capability gap, or changing
  ScriptType registration, task lifecycle, config ownership, ScriptConfig
  sessions, Electron integration, frontend edit surfaces, and verification.
---

# 专项适配

## 核心要义

专项适配不是把外部脚本的字段逐项搬进 MAS，而是围绕用户完成任务的最短路径做产品化承接。每次适配先回答两件事：

1. **降低用户使用门槛**：优先消除安装导入、路径选择、首次配置和高频任务编排中的手工步骤。典型目标是 Okww 的脚本与游戏启动器双路径一键导入、MaaEnd 的快速配置；不要把上游原始配置面板原样搬进来当作完成。
2. **必要时由 MAS 补位**：脚本原生能力完整且稳定时优先调用脚本；脚本无法提供但 MAS 能可靠编排的能力，由 MAS 在适配层补足。典型目标是 MAA 的活动关优先和将剿灭、日常拆成两段执行。补位只负责用户价值和调度编排，不复制整个脚本引擎，也不重复暴露脚本已有的权威设置。

详细判断表、实施顺序和验收项见 [专项适配完整说明](references/guide.md#核心要义围绕用户最短路径做适配)。若一个改动既没有减少用户手动步骤，也没有补足明确的脚本能力缺口，应先停下来重新确认范围。

## 开工顺序

0. 先列出用户当前需要手动完成的步骤，以及脚本明确缺失的能力；标注哪些由脚本负责、哪些由 MAS 负责。
1. 获取上游仓库或发行版信息，确认 CLI、进程、日志、配置目录和配置 UI。
2. 对照 [脚本前端架构](references/script-frontend-architectures.md) 归类，并让用户确认架构线与展示文案。
3. 读取 [专项适配代码规范](references/adapter-code-norms.md) 和对应案例：
   - SRC：[examples-src.md](references/examples-src.md)
   - MaaEnd / MXU：[examples-maaend.md](references/examples-maaend.md)
   - M9A / MFAA：[examples-m9a.md](references/examples-m9a.md)
   - Okww / ok-script：[examples-okww.md](references/examples-okww.md)
4. 检查相邻实现与所有注册调用者，再决定最小改动。不要从旧 Skill 文案推断当前行为。
5. 用用户场景验收：是否少了一段手工配置，MAS 补位是否有明确输入、失败提示和回退路径。

前端任务同时加载 `mas-frontend-standards`；涉及 UI、表单、遮罩或反馈时再加载 `mas-frontend-ui`。

## 完整落点

新增或维护 `ScriptType` 时，按实际需要核对以下切面：

- 配置与 schema：`app/models/config.py`、`app/models/schema.py`
- 注册与 API：`app/core/config.py`、`app/api/scripts.py`、`app/core/task_manager.py`、`app/utils/constants.py`
- 任务模块：`app/task/Xxx/` 的 `manager`、`AutoProxy`，按架构需要增加 `ScriptConfig`
- 日志采集推送：需要把脚本运行日志关键节点推送至任务报告时，用通用组件 `log_box`（用法见 [logbox-api.md](references/logbox-api.md)），专项只喂参数（日志路径/规则/处理器）并注入 sink；报告聚合与追加复用通用工具 `app/tools/push_log.py`（`build_push_log_text` / `append_push_log`），专项不要自行拼接实现。「是否展示节点详情」由专项（或其用户配置）的开关在**是否创建/启用 log_box 的入口**消费（关闭即不创建，省采集开销），不要给 log_box 加通用开关，也不要在聚合层采后过滤（参考 okww 用户级 `Notify.PushLogEnabled`）
- 前端入口：`Scripts.vue`、`ScriptTable.vue`、router、`types/script.ts`、相关 composable、脚本/用户编辑页
- Electron 能力：仅当需要注册表、文件系统或进程发现时增加 `electron/services`、IPC、preload 与类型声明
- 生成代码：后端 schema 变更后运行生成器，禁止手改 `frontend/src/api/**`

不要机械要求所有类型拥有相同文件。先确认架构契约，再补齐真实调用链。

## 审查方法

1. 从 `ScriptType`、任务注册和 UI 入口反查全部调用者。
2. 对照运行时读取的字段检查 config、schema、生成类型和表单；schema 中存在但运行时未消费的字段不代表有效功能。
3. 对照自动发现、手动选择和后端 `check()` 的路径判定；同一资源必须使用同一组哨兵文件。
4. 对照配置会话的启动、WebSocket 状态、停止、超时、卸载和异常路径；确保任务结束、进程退出、锁释放、配置写回。
5. 对照 `final_task` / `on_crash` 的原子配置恢复、用户状态落盘和独立进程清理。
6. 按 `tests/AGENTS.md` 运行最小专项测试；非必要不新增测试，测试缺口写进结果，不编造验证结果。
7. 反查产品边界：没有重复实现脚本已有能力，没有把 MAS 补位伪装成脚本原生字段，也没有为了“字段齐全”增加无用户价值的入口。

## ok-script 家族与 Okww 当前基线

`ok-script` 是脚本大类，不是单一专项。当前至少区分 `Okww` 与 `OkNte`；家族级原则可以复用，但 CLI、配置目录、原生 GUI 和任务语义必须逐子项目确认。以下内容只约束 Okww，不自动约束 OkNte。

配置来源模式按专项需要选择，并不是统一强制三态：Okww 采用 **脚本 / 用户 / 直控** 三态，General 采用 **用户 / 直控** 两态，MaaEnd 采用脚本 / 用户两态，M9A 不使用这套来源模式。新专项应先确认真实配置 owner，不要为了界面或术语对齐机械增加“直控”或第三种状态。

Okww 已落地为 `ok-script` 专项，当前不是表单化 JSON 编辑器方案：

- 自动代理使用 `ok-ww.exe -t N -e`，MAS 只开放任务 `1` 和 `7`；少量高频字段由独立的快速配置面板控制。
- 配置使用 `ScriptConfig.py` 无参数启动本体 GUI，通过 WebSocket 遮罩会话保存。
- 用户配置来源为脚本/用户/直控：脚本归 `Default/ConfigFile`，用户归 `{userId}/ConfigFile`，直控直接读取脚本原有 `working/configs`。
- `Info.IfQuickConfig` 是独立覆盖层开关，控制快速配置面板是否覆盖 DailyTask 高频字段；关闭时使用来源配置中的完整任务设置。
- `Game.Enabled` 是当前 UI/运行时的游戏启停总开关；不要从兼容字段推断独立启动或关闭行为。
- ok-ww 根目录必须同时存在 `ok-ww.exe` 与 `data/apps/ok-ww/app.json`。
- Electron 一键导入与手动选择必须使用相同哨兵；鸣潮保存启动器路径，后端再解析实际客户端路径。
- 成功判定使用内置窗口关闭日志；进程在成功标记前退出视为异常。
- Okww 后续只使用官方资源与官方启动器，不使用 WeGame 侧资源。

完整实现与审查点见 [examples-okww.md](references/examples-okww.md)。

## 验证

按 `tests/AGENTS.md` 选择被改专项的最小测试入口；没有对应测试时不为了填目录新增脚本，在结果中说明测试缺口。仅在专项适配实际涉及前端时，再从 `frontend` 运行对应的前端最小测试；跨模块契约或用户明确要求时才扩大测试范围。文档修改至少用 `rg` 确认不存在相互冲突的旧规则。
