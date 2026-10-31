# 游戏社区通知与任务报告

社区通知有两条互斥出口：**独立推送**（手动、启动）与**并入任务报告**（任务前置签到）。两者共用同一套渲染与分发，区别只在谁承担渠道重试与结清。这条管线由 dev 维护，通知统一由 core.Notify 管理，社区工具只产出结果，宿主负责调用与配置回写。

## 三处所有权

| 位置 | 职责 | 关键符号 |
| --- | --- | --- |
| `app/models/notification/community.py` | 签到结果 → 通知结果模型 | `CommunityNotificationResult`、`community_notification_results(results)` |
| `app/core/notify/community_content.py` | 渲染与载荷 | `_community_notification_rows()`、`format_community_notification()`、`format_community_task_summary()`、`build_community_notification_payload()`、`append_community_summary_html()`、`_PLATFORM_ORDER` |
| `app/core/notify/community.py` | 编排：去重、快路径、后台任务、失败上报 | `CommunityNotificationCoordinator`、`CommunityNotificationDependencies`（`dispatch` / `prepare_targets` / `render` / `enabled` / `report_failure` / `spawn` / `fast_path_seconds`） |

消费方是 `app/api/community/accounts.py`（手动）、`app/core/timer.py`（启动）、`app/core/notify/task_report.py`（任务前置），三处都必须先转成 `community_notification_results(...)` 再交给管线。

## 不变量

1. 平台顺序固定为 `_PLATFORM_ORDER`（森空岛、米游社、库街区、塔吉多、云异环），未知平台排在尾部而不是报错。新增平台必须同步该元组。
2. 通知通过 `CommunityNotificationResult.succeeded` 读取已投影的结果；保持与签到完成语义一致，不通过渲染结果回写签到状态。
3. `_notification_only` 占位项在进入渲染前过滤；任何新出口都要先过滤，否则「未获取到可签到角色」会被当成失败发出去。
4. `GameSign.NotifyEnabled` 是总开关，三条路径都要检查。
5. 通知**必须在签到流程锁外**发送：慢渠道会拖住 `community_sign_flow()`，后续触发全部 409。
6. 后台通知任务必须持强引用并挂 `add_done_callback`，否则可能被事件循环回收，用户永远收不到。
7. 渠道级失败走 `report_failure` → `Notify.push_system_notice(...)`，只写日志等于没有通知。
8. 重试记账按渠道 id（`succeeded_ids` / `failed`）而不是布尔值，补发时跳过已送达渠道，避免同一渠道收到两遍。
9. 「结果无法确认」与「空结果」是两种终态，不能合并成「签到失败」。

## 渲染约定

- 行模型 `_community_notification_rows()` 是文本 / Markdown / HTML / 图片四种渲染的**唯一**数据源，不要新增平行格式化分支。
- HTML 分支对动态文本统一 `escape()`；Markdown 分支走 `_escape_markdown_text()`；账号名、奖励与失败原因都不得被当成标记解释。
- 云异环的剩余时长属于状态而不是新领取奖励，不能加 `📥` 之类的新增标记。
- 改重试次数或间隔时同步检查 `NOTIFICATION_FAST_PATH_WAIT_SECONDS`（`app/core/notify/coordinator.py`）：快路径的等待时间必须覆盖「一次重试仍失败」的最早返回时间。

## 常见错误

1. 在 `community_sign_flow()` 内推送通知 → 慢渠道拖住签到锁。
2. 后台任务不持强引用 → 补发永远不到。
3. 用布尔值判断「发过了」 → 重发时全量再发一遍。
4. 新出口忘记过滤 `_notification_only` → 占位项进入通知。
5. 只检查 `GameSign.NotifyEnabled` 的一处 → 关闭通知后仍有路径在推送。
6. 在 `app/core/notify/community_content.py` 里回读配置或发请求 → 渲染层必须保持纯函数。
