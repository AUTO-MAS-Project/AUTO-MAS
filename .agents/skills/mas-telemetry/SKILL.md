---
name: mas-telemetry
description: Implement and verify AUTO-MAS anonymous telemetry whenever adding or changing user-visible workflows, pages, script adapters, lifecycle operations or result contracts. Proactively reuse or extend events alongside the feature; also use for telemetry reviews and missing or incorrect statistics. Skip prose-only, styling-only and generated-only edits unless they change collection behavior.
---

# MAS Telemetry

新增或修改任何可观察用户流程（Vue/Electron/Python 公开结果、专项引导、任务队列、配置、模拟器、更新、通知、社区、外观、诊断）时，**主动同步完成遥测**，不等用户提醒。完成前明确给出结论与入口：**复用** / **补齐** / **不采集**（说明理由；“以后再补”或“类型里已有定义”不算接入）。

## 必读入口

- 现有事件与口径：`frontend/electron/services/analytics.md` & `analyticsCoverage.md`
- 类型与白名单：`frontend/src/types/analytics.d.ts`、`frontend/electron/services/analyticsFeaturePolicy.ts`、`analyticsPolicy.ts`
- 上报工具：Renderer 用 `observeFeature` / `beginAnalyticsOperation`；主进程用 `beginMainFeature`
- 按需深读：[integration.md](references/integration.md)（接入）· [scenarios.md](references/scenarios.md)（异步/批量/取消/专项）· [verification.md](references/verification.md)（验收）

## 红线边界

1. **一操作一所有者**：不重复埋点；严格区分「用户选择 / 请求受理 / 实际完成」，禁止把 HTTP 200、弹窗打开或任务入队冒充执行成功。
2. **操作前捕获代次**：在操作开始前捕获开关代次，结束时沿用原代次，关闭后再开启不补发旧操作。不把遥测放进业务或退出等待链。
3. **隐私绝对禁区**：只发白名单有限枚举、结果、数量桶与耗时桶。**严禁**发送任何 ID/UID/设备哈希、名称、路径、URL、凭据、二维码票据、配置、命令、正则、日志、正文、截图或原始错误文本；不可用类型断言绕过主进程白名单。
4. **共享开关与隔离**：复用 `Function.IfEnableTelemetry`（未知/损坏停采；开关本身不发事件）；保留开发/浏览器/CI/单测/E2E 禁报隔离与主窗口主 frame 限制；不另建客户端、拦截器、磁盘队列或退出 flush；不把堆栈/日志搬进 Aptabase（归 Sentry）。
5. **同步文档**：新增或变更事件口径时同步更新 `analytics.md` 与 `analyticsCoverage.md`，采集范围变化同步中英日说明，不悄悄篡改既有字段历史语义。
