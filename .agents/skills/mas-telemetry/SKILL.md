---
name: mas-telemetry
description: Implement and verify AUTO-MAS anonymous telemetry whenever adding or changing user-visible workflows, pages, script adapters, lifecycle operations or result contracts. Proactively reuse or extend events alongside the feature; also use for telemetry reviews and missing or incorrect statistics. Skip prose-only, styling-only and generated-only edits unless they change collection behavior.
---

# MAS Telemetry

## 默认行为

新增或修改 AUTO-MAS 的可观察业务流程时，主动把遥测作为该功能的一部分完成，不等用户再说“加埋点”。先检查现有观察入口：已经覆盖就复用，缺失才补，口径变化则同步修正。不要为每个点击、请求或辅助函数增加一个事件。

这条规则适用于 Vue/Electron、Python 对外可观察结果、专项引导、任务与队列、配置管理、模拟器、更新、通知、社区、外观和诊断工具。纯文案、样式、内部重构、生成文件更新通常复用现有覆盖；只读分析不顺手改代码。明确的用户限制优先。

对每项功能在完成前给出以下结论之一，并说明实际入口：

1. **复用**：已有事件族、维度和唯一观察者已经覆盖，不再加第二层。
2. **补齐**：新增/修正业务观察边界、有限字段、主进程校验及验证证据。
3. **不采集**：没有可解释的产品问题、属于高频内部活动、涉及敏感信息，或没有可靠结果。说明理由；只有受理信号时可记录受理，不编造完成。

“以后再补遥测”和“类型里已经有事件”不能代替入口接入。没有接入的子流程要明确列为未覆盖。

## 先读什么

代码和文档的位置均相对仓库根目录：

| 任务 | 必读来源 |
| --- | --- |
| 每次业务接入 | `frontend/electron/services/analytics.md`，当前入口及其调用者，相邻同类事件 |
| 新事件或字段 | `frontend/src/types/analytics.d.ts`、`frontend/electron/services/analyticsFeaturePolicy.ts`、`frontend/electron/services/analyticsPolicy.ts` |
| Renderer 操作 | `frontend/src/utils/featureAnalytics.ts`、`frontend/src/utils/analytics.ts` |
| 主进程操作 | `frontend/electron/services/featureAnalytics.ts`、`analyticsService.ts`、`analytics.ts` |
| 覆盖核对 | `frontend/electron/services/analyticsCoverage.md`，对应 Issue/PR；台账不是执行证据 |

- 编写或修改埋点时读 [接入与结果语义](references/integration.md)。
- 涉及异步、批量、缓存、重连、取消、部分完成或专项时，再读 [场景决策与反例](references/scenarios.md) 的相关条目。
- 提交验证和审查结论前读 [验证与交付](references/verification.md)。

不复制一份完整事件目录到 Skill；现有事件数量、字段和限频参数以代码及上述文档为准。

## 必须保持的边界

### 一个业务操作，一个结果所有者

- 先明确要回答的问题、实际入口、操作何时开始、由谁确认结果、有哪些合法终态。
- 用户选择、请求受理、实际完成分别处理，不能把 HTTP 成功、打开窗口或排入任务当成工作已完成。
- 在实际操作开始前捕获采集代次；完成时只用原代次。关闭后再开启不能补发旧操作。
- Renderer 使用 `observeFeature`、`beginAnalyticsOperation`；主进程使用 `beginMainFeature`。只有已有语义适用时才选通用 outcome 映射。
- 不把统计发送加入保存、任务、更新、退出的网络等待链。保留原请求、取消能力、响应对象、异常语义和清理顺序。
- 一次终态保护属于逻辑操作，不属于每条响应、每次轮询或每个 Vue 实例。快照恢复、相同批次、跳过的刷新不制造新结果。
- ID 只在有界本机关联中使用；用户 UID、脚本 UID、队列 UID、任务 UID 不可互换。能从实际入口传固定类型时不要用错误 ID 查询缓存，也不要为分类新增查询。

### 默认不允许的数据

只发送显式允许的类别、布尔状态的有限分类、结果、数量桶和耗时桶。禁止对象/账号/设备标识及其稳定哈希、名称、路径、URL、凭据、二维码票据、配置、命令、正则、日志、通知正文、截图和视频。异常只映射为有限类别，不把原错误写入属性。

新增值必须有有限白名单和未知值归类。不能只用类型断言绕过主进程校验；不能把自由文本包装为“类别”。协议已有的系统属性和临时随机会话遵循现有实现，不新增稳定安装标识。

### 共享开关与隔离

- 复用 `Function.IfEnableTelemetry` 和现有持久化确认机制；配置未知或损坏时停采。
- 开关自身不产生事件；不单独上报用户启用或关闭遥测。
- 不另建 Aptabase 客户端、通用 IPC/HTTP 拦截器、后台队列、重试、落盘缓存或退出 flush。
- 保留开发、浏览器、CI、单元测试、E2E 的生产上报隔离，以及主窗口、主 frame、固定文件入口和字段校验。
- 辅助窗口不能获得通用事件桥权限；确需记录时沿已有业务 IPC 由明确所有者记录结果。
- Sentry 继续负责异常和性能诊断；不把堆栈、逐日志、逐帧进度重复搬进 Aptabase。

## 新功能的完成条件

功能实现同时核对：真实入口已有观察、同类旁路没有遗漏、类型和运行时白名单一致、错误/取消/未知/部分完成语义正确、ID 分类正确、异步不会错配、开关与隐私仍生效。新增页面还需检查路由白名单及来源映射。

更新当前事件文档与覆盖台账；采集范围或处理方式变化时同步中英日的遥测说明。不要把现有字段历史含义悄悄改成另一种含义。更新日志按仓库规则处理，一条 PR 不重复加多个碎片。

功能专属探针按项目规则保留在本地忽略目录，不默认提交。交付说明写清复用/新增的事件、结果所有者、跳过的范围和实际验证层级。接入 Skill 不增加会话授权：真实账号、游戏、硬件、生产写入、服务器改动、提交和推送仍遵循用户已有授权，不因“验证遥测”自行扩展。
