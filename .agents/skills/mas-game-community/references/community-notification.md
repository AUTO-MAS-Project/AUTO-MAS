# 游戏社区通知与任务报告

社区通知有两条互斥的出口：**独立推送**（手动、启动）与**并入任务报告**（任务前置签到）。两者共用同一套渲染与分发代码，区别只在谁承担渠道重试与结清。

## 呈现模型

`community_notify._community_notification_rows()` 是文本 / Markdown / HTML / 图片四种渲染的**唯一**数据源，产出 `(kind, text)` 序列：

| kind | 内容 | 样式 |
| --- | --- | --- |
| `title` | `【社区签到通知】` | HTML `h2`，Markdown 加粗 |
| `heading` | `• {平台}({成功数}/{总数})：` | HTML `h3` |
| `item` | `✅/❌ [游戏] {身份} {详情}` | HTML `p` |
| `footer` | `AUTO-MAS 敬上` | HTML `p` |

规则：

- 平台顺序固定为 `_PLATFORM_ORDER`（森空岛、米游社、库街区、塔吉多、云异环），未知平台排在尾部而不是报错。新增平台必须同步该元组。
- 计数里的「成功」与每行的 ✅/❌ 都走 `community_contract.is_community_sign_completed()`（`status in ("成功","已签到") or _completed`），与签到处同一判据；不要再手写状态集合。
- `filter_community_notification_results()` 先剔除 `_notification_only` 占位项；**任何新出口都必须先过滤**，否则「未获取到可签到角色」会被当成失败发出去。
- `_result_status_text()` 负责状态短文案（已签 / 签到成功 / 签到失败-风控 / 签到失败-原因；`_completed` 但未成功的行渲染成「已完成-原因」）；`_result_detail()` 负责奖励，云异环的剩余时长属于状态而不是新领取奖励，不能加 `📥`。
- `_result_nickname()` 从 `昵称/角色名(UID)` 之类的展示格式里提取角色名，保留可能带斜线的昵称。
- HTML 分支对动态文本统一 `escape()`；Markdown 分支走 `_escape_markdown_text()`；两者都不允许把账号名当标记解释。

图片分支用 Pillow 渲染，字体候选见 `_FONT_CANDIDATES` / `_SYMBOL_FONT_CANDIDATES`：中文用系统字体，`✅❌📥` 优先用符号字体，缺失时回退到 `[OK]/[X]/[+]`。测量与绘制必须使用同一套 run 切分（`_notification_text_runs`），否则会出现方框或错位。

## 载荷与分发

`build_community_notification_payload()` 一次生成 `NotifyPayload` 的 `text` / `markdown` / `html` / `images`（`id="community-sign-summary"`，PNG），`append_signature=False`（签名由行模型自己给）。空结果但有 `completion_notice` 时改用纯文本载荷——这是「本次没有新结果」「结果无法确认」两种终态的唯一出口。

`dispatch_community_notification(results, targets=None, skip_channel_ids=(), completion_notice="")`：

- `targets` 为空时用 `[global_target(include_system=True)]`，即用户配置的全局渠道加系统提示。
- 恒定 `attempts=NOTIFICATION_SEND_ATTEMPTS (2)`、`retry_delay=NOTIFICATION_RETRY_DELAY_SECONDS (1)`。
- 返回 `DispatchResult`，其中 `succeeded_ids` / `failed` 供上层做**渠道级**记账与重试，不要只取布尔结果。

渠道级失败必须走 `report_community_notification_failure()` → `Config.push_system_notice(...)`，不能只写日志：用户看不到日志就等于没有通知。`results_saved=False` 时文案不得声称结果已保存。

## 两条出口

### 独立推送（手动 / 启动）

`push_community_notification(results)`：`dispatch_community_notification` + 渠道失败系统提示，返回失败渠道名列表。

- 手动签到 `POST /api/tools/sign` 用 `asyncio.shield` 包住推送，最多等 `NOTIFICATION_FAST_PATH_WAIT_SECONDS (1.1s)`；超时转后台任务，接口立刻返回。1.1s 恰好覆盖「一次重试仍失败」的最早返回时间，改重试参数时必须同步这个常量。
- 启动签到（`timer.schedule_community_for_startup`）在 `_execute_community_sign` 里直接 `await push_community_notification`，因为后台任务已经有强引用。

### 并入任务报告（任务前置签到）

`community_sign_notification`（`app/core/task_report.py::TaskCommunitySignNotification`）挂在 `task_info` 上，负责把签到结果并进脚本的完成报告：

1. `receive(results)`：先存 `task_info.community_results`（已过滤占位），再置 `completed` 事件，最后尝试补发。`results is None` 表示「无法确认结果」，与「空结果」是两种终态。
2. `dispatch_task_report()` 在已置锁内等 `completed`，最多 `NOTIFICATION_FAST_PATH_WAIT_SECONDS`；超时则给报告补一句「社区签到结果待确认，完成后另行通知。」并照常投递。
3. `schedule_supplement()` 在「任务结束」或「报告已发且已超时」时补发，任务由 `RuntimeTasks.spawn` 创建并登记进 `_PENDING_TASK_COMMUNITY_NOTIFICATIONS`（强引用，防 GC）。
4. 渠道记账落在 `task_info.game_sign_summary_delivered`（已送达摘要的渠道）与 `game_sign_summary_pending`；补发时以 `skip_channel_ids=delivered` 只发给没收到摘要的渠道，避免同一渠道收到两遍。
5. `community_summary_consumed` 表示摘要已被完整消费，之后的脚本报告不再重复附加。

报告正文合成走 `append_task_community_summary()`（文本/Markdown）与 `append_community_summary_html()`（在模板 `signature` 或 `body` 末尾插入转义后的 `result-box`），`append_task_community_summary` 会先检查 `GameSign.NotifyEnabled`。

## 结清与退出

- `drain_task_community_notifications(timeout)`（`task_report.py`）：幂等等待所有补发任务，超时只停止等待、**不取消**投递。
- `timer.drain_community_tasks()`：电源动作前先等后台签到任务、再等补发；补发期间若又启动了新一轮签到（跨零点），共用同一个截止时间。
- `shutdown_community_notifications()`：退出时取消并 `gather` 全部补发任务，之后才能释放共享 HTTP 连接。

## 常见错误

1. 在 `community_sign_flow()` 内推送通知 → 慢渠道拖住签到锁，后续触发全部 409。
2. 后台任务不持强引用 → 事件循环回收任务，用户永远收不到补发。
3. 忽略 `DispatchResult.succeeded_ids`，用布尔值判断「发过了」 → 重发时全量再发一遍。
4. 新增渠道/新出口时忘记 `filter_community_notification_results()` → 占位失败项进入通知。
5. 把「结果无法确认」写成「签到失败」→ 用户被误导；该终态只能由 `COMMUNITY_SIGN_RESULT_UNAVAILABLE_TEXT` 表达。
6. 只检查 `GameSign.NotifyEnabled` 的一处 → 关闭通知后仍有路径在推送。

## 审查清单

- [ ] 行模型仍是四种渲染的唯一数据源，未新增平行格式化分支
- [ ] 新平台进了 `_PLATFORM_ORDER`，新状态进了 `_SUCCESS_STATUSES` 或 `_result_status_text`
- [ ] 占位项在进入通知前被过滤
- [ ] 渠道失败走系统提示，且文案与实际保存状态一致
- [ ] 手动/启动/任务三条路径都检查了 `GameSign.NotifyEnabled`
- [ ] 通知在流程锁外发送；后台任务有强引用、有 `done_callback`
- [ ] 补发按 `succeeded_ids` 记账，不重复打扰已送达渠道
- [ ] 改重试次数或间隔时同步了 `NOTIFICATION_FAST_PATH_WAIT_SECONDS`
