# 内置通知渠道与投递架构

本目录存放随应用源码交付的内置通知渠道（可信进程内模块，不提供外部插件安装或热加载）。

## 新增内置通知渠道

每个渠道位于独立子目录 `<id>/`，包含 `manifest.json`、`__init__.py` 与传输实现：

```json
{
  "interface_version": 1,
  "id": "example",
  "entrypoint": "app.core.notify.channels.example:register",
  "requires": []
}
```

实现约束：

- **延迟依赖与纯净导入**：`requires` 声明必需的第三方顶层模块名。发现阶段只读清单；注册时调用 `register() -> NotifyChannel`。入口包仅依赖标准库、通知契约和本包代码，外部传输库由宿主通过 `ChannelDependencies` 注入，禁止在导入、注册或构造期间联网、发消息或修改全局注册表。
- **完整声明**：`NotifyChannel` 提供稳定 `id`、本地化键、排序权重 `(order, key)`、目标构造器、单次发送适配器、发送器工厂，以及有连接状态时的可选启停入口。
- **错误与缺依赖隔离**：重复 ID 不覆盖；缺依赖的有效声明保持可见但不绑定发送器（已启用目标会明确报失败）；清单或入口损坏的包被隔离并记入 `NotifyTarget.unresolved`，避免宿主把未知渠道误判为全部送达。
- **目标构造与发送返回值**：目标构造器只读宿主的 `ChannelConfig` 视图，依据显式启用开关（`enable_field` 或逐目标开关）构造不可变目标快照（固定地址、密钥、模板与请求头，重试不重新枚举）。发送器每次执行单次发送：`None` / `True` 表示成功，`False` 表示失败，协议层通过 `NotificationDeliveryError` 声明是否可重试。

## 无会话快照 vs 有状态会话渠道

| 类型 | 声明方式 | 适用渠道 | 行为说明 |
| --- | --- | --- | --- |
| 无会话渠道 | 声明 `transport_fields`（空元组表示仅固定代理） | 邮件、系统提示、Server 酱、Webhook、移动消息 | 准备目标时生成不可变 `NotificationTransportSnapshot` 注入工厂，重试沿用同一快照，凭据不进入 `repr` |
| 有状态会话渠道 | `transport_fields=None`，提供启停入口 | QQ、Koishi | 全局共用已装配实例，由主定时器启动后按 `lifecycle_order` 启动（QQ 先于 Koishi），退出时先回收通知任务再逆序停止 |

> 业务系统提示统一走 `Notify.send_notice()`，Webhook 草稿测试走 `Notify.test_webhook()`（禁用草稿也可测试），两者均直接调用已装配渠道能力。

## 单次通知投递链路

```text
业务 / 协调器
  -> core.Notify (NotificationManager)      读取全局或用户配置，逐渠道准备目标快照
  -> models.notification_channel            NotifyTarget / DeliveryChannel / ChannelTarget
  -> notify.dispatch                        渲染、并发与重试调度、汇总 DispatchResult
  -> notify.transport                       选择已装配会话或无会话发送器
  -> 渠道传输
```

关键边界：

- **解耦与按需渲染**：投递服务不导入 `core` 或全局配置，发送器与渲染器显式注入。`NotifyPayload` 的 HTML / Markdown / 图片支持 `DeferredContent`，仅在目标需要该格式时生成并缓存；可选格式生成失败时按目标格式顺序自动降级，图片失败保留正文。
- **并发与事务安全**：单次分发不同渠道最多 4 路并发，同渠道内按原顺序投递；若调用位于配置事务内，由 `core` 门面自动切换为同 Task 串行执行，避免与父事务锁冲突。
- **取消与退出**：取消时同步取消并等待全部渠道子任务完成 `finally` 清理；应用退出时先停止业务与 `BackgroundTaskManager` 托管的通知任务，再关闭渲染器与渠道。
- **失败可诊断**：`DispatchResult.failures` 记录每项失败的目标 ID、阶段、类别、可重试性、尝试次数与异常类型（不记录可能含凭据的原文）；`NotifyTarget.unresolved` 汇总目录错误与准备失败，防止上游在未确认送达时结清提醒或消费摘要。

## 任务报告、社区签到与日历编排

```text
manager -> TaskResultReport -> Notify.push_proxy_result
  -> notify.task_report          读取策略快照、装配依赖
  -> notify.coordinator          等待签到、摘要去重与迟到补发
       -> ReportRenderer + NotificationDispatcher

AutoProxy / runner -> NotifyPayload -> Notify.push_statistics_report
MAA 喜报 / HSR 云登录 -> NotifyPayload -> dispatch_task_notification
```

- **任务报告协调器（`TaskReportCoordinator`）**：只持有 `TaskNotificationState`，外部能力经 `TaskReportDependencies` 注入。入口固定不可变 `TaskReportPolicy` 与目标快照，等待期间修改配置不影响已准备报告；迟到补发作为新一次通知重新读取策略。报告与补发共享同一把锁，已收到签到摘要的渠道不重复追加。
- **专项内容隔离**：简单统计共用 `notify.task_content`，复杂统计由各专项纯内容适配生成正文、模板与图片声明，不接触渠道选择与发送逻辑。
- **社区签到通知**：消费不可变 `CommunityNotificationResult`（`success` / `already_signed` / `risk_control` / `failed`）。手动签到与非任务定时签到走 `Notify.community`；超时或 HTTP 取消后由 `BackgroundTaskManager` 接管投递。
- **日历提醒**：直接调用 `Notify` 准备目标并按成功 ID 更新进度，存在未解析目标时不结清提醒。
