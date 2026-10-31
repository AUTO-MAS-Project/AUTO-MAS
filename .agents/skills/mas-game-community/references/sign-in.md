# 游戏社区签到链路

签到是「凭据驱动的批量外部请求」：遍历账号组、逐平台跑一次上游签到、归一结果、落盘日期、再交给通知。编排在 `app/core/community/sign.py`，平台知识集中在 `app/tools/common/community/sign.py`。

## 平台注册表是唯一入口

`_COMMUNITY_SIGN_PROVIDERS` 是不可变元组，每项 `_CommunitySignProvider(frozen=True)` 声明五件事：

| 字段 | 含义 |
| --- | --- |
| `token_field` | `GameSignAccountGroup` 上的凭据字段名，同时是「该平台是否已配置」的判据 |
| `log_name` | 日志与错误文案中的平台名 |
| `runner` | `async (token, account_name, account_uid, on_credential_update) -> _CommunityProviderRun` |
| `resolve_platforms` | 由凭据推导本次涉及的平台名元组 |
| `error_game` | 平台名 → 失败结果里的 `game` 字段 |

当前五项：

| token_field | log_name | 结果平台名 | 备注 |
| --- | --- | --- | --- |
| `SklandToken` | 森空岛 | 森空岛 | 与养成练度源共用 `skland_sign_lock` |
| `MiyousheToken` | 米游社 | 米游社 | DS 签名、风控退避、Cookie 轮换 |
| `CloudGenshinToken` | 云原神 | 米游社 | 米游社凭据已配置时改由米游社 Cookie 临时顶替；runner 不接收回写回调 |
| `KuroToken` | 库街区 | 库街区 | 无凭据轮换 |
| `TaygedoToken` | 塔吉多 | 塔吉多 / 云异环 | 唯一使用动态 `resolve_platforms`：一份 JSON 凭据可同时覆盖两个平台名 |

`COMMUNITY_TOKEN_FIELDS`、`has_community_credentials()` 全部由注册表派生。**不要另写一份平台或凭据字段清单**：调度台跳过账号、前端判空、通知分组都应回到注册表。

云原神有一条特殊装配：当 `MiyousheToken` 已配置时，编排层把米游社 Cookie 作为本轮临时 `CloudGenshinToken` 注入 `runtime_tokens`（不落盘、不回写），旧字段继续作为无米游社凭据时的兼容后备。改这段逻辑时两件事必须同时成立：只在运行时字典里注入、绝不写回配置。

## 新增一个社区平台

按此顺序，每步都能独立自查：

1. **写平台适配模块** `app/tools/<platform>.py`。对外只暴露「跑一次签到」入口、`validate_<platform>_credential()` 与必要的凭据序列化函数。参考了第三方项目接口知识时，按现有模块的文件头格式加致谢与许可声明。
2. **加凭据字段**：在 `app/models/config/tools.py` 的 `GameSignAccountFields` 增加 `<Name>Token`，类型用 `Annotated[str, encrypted()]`，描述以 `GameSignAccount - ` 开头并注明 DPAPI 加密。
3. **登记校验器**：在 `app/tools/common/community/credentials.py` 的 `_CREDENTIAL_VALIDATORS` 加一项，指向适配器的本地校验函数。
4. **写 provider runner**：在 `app/tools/common/community/sign.py` 加 `_run_<platform>_provider()`，返回 `_CommunityProviderRun(results=..., platforms=..., credential_updates=...)`。
5. **注册**：在 `_COMMUNITY_SIGN_PROVIDERS` 追加一项。凭据字段表、并发执行、凭据回写、日期标记全部自动生效。
6. **通知排序**：在 `app/core/notify/community_content.py` 的 `_PLATFORM_ORDER` 追加平台名。缺失时该平台落到排序尾部而不是报错，容易漏掉。
7. **重新生成 OpenAPI 客户端**，再在 `TabGameSign.vue` 加录入入口。禁止手改 `frontend/src/api/**`。

## 并发与重复触发

四把锁语义不同，不要合并：

| 锁 | 位置 | 覆盖范围 | 违反时 |
| --- | --- | --- | --- |
| `community_sign_flow()` | `app/core/community/sign.py` | 签到请求 **加** 结果落盘；通知在锁外 | 直接抛 `CommunitySignInProgressError`，不排队 |
| `_community_sign_lock` | `app/core/community/sign.py` | 全局签到执行，配合 `_community_sign_lock_owner` ContextVar 支持**同任务嵌套重入** | 同上，快速失败 |
| `skland_sign_lock` | `app/tools/common/community/providers/skland.py` | 森空岛签到全流程与养成练度源共用，互斥签名 token 的两个轮换写者 | 串行等待 |
| `community_activity_flow()` | `app/core/community/scheduling.py` | 日常便笺查询串行化；后到者等锁后复用缓存 | 串行等待（不抛错） |

签到锁是**快速失败**而非等待：`if lock.locked(): raise`。API 层把 `CommunitySignInProgressError` 映射为 `code=409`；timer 层降级为 `logger.info` 后跳过本次触发（任务来源则原样抛出，由任务完成回调交付异常终态）。新增触发入口时必须选一种处理，不要静默 `await` 到锁释放。

练度源的凭据回写走注入的 `save_credential` 回调（`app/core/config/manager.py`），不进 `credential_updates`——它不是注册表 runner；改这两条链路时必须保住 `skland_sign_lock`，否则会把对方刚回写的 token 作废。编排层收尾回写前会重读存量、发现已被别的链路轮换即跳过写入，也是防同一件事。

通知**必须在流程锁外**发送。慢渠道会阻塞后续操作，这是锁边界画在落盘之后的原因。

## 日期标记

两层语义，不要混用：

- 账号级 `GameSignAccount.LastSignDate`：由 `run_community_sign_in` 按账号写。自动模式（`force=False`）即使失败也标记当天，避免后续 MAS 任务反复请求上游；手动模式（`force=True`）仅在该账号所有已配置平台完成后才标记。
- 全局 `GameSign.LastSignDate`：由调用方（`timer` / `manual_game_sign`）在**所有**启用且有凭据的账号都完成后才写。

多账号串行签到可能跨越 0 点，写入时**重新取当前日期**而不是复用循环开始时的 `today`。改这段逻辑要保留这个行为。

遍历账号组用 `for uid in list(accounts.keys())` 取快照再逐个 `get()`：签到期间用户删除账号组不应中断整轮签到。

## 结果契约

`results` 是 `list[dict]`，键固定：

```text
account       账号名，失败结果为 "账号名/平台名"
account_uid   账号组 UUID 字符串，由编排层统一覆盖
game          游戏名
platform      平台名
status        "成功" / "已签到" / "失败"
reward        奖励文案
reason        失败原因
```

两个内部标记：

- `_notification_only`：占位结果（如「未获取到可签到角色」）。它只参与「本轮有没有结果」的判断，`format_community_sign_results` 与通知侧都会过滤它，前端和通知都看不到；某账号本轮全是占位时一条通知都不会发（既定口径，不是缺陷）。
- `_completed`：流程已跑完、但没拿到明确成功状态的旁路标记（如云异环没确认到新增时长）。

**成功判据只有一处实现**：`app/tools/common/community/contracts.py` 的 `is_community_sign_completed()`，即 `status in COMMUNITY_SIGN_SUCCESS_STATUSES or _completed`。编排层 `all_enabled_community_platforms_signed`、手动端点 `manual_game_sign`、通知模型据此语义投影既有结果，不反向参与日期与凭据落盘；不要再增加业务成功判据。前端标签云仍按 `status` 判定，`_completed` 行显示为失败，属于已知差异（该组合只在同一天二次确认云异环时出现）。

`_decorate_provider_run()` 负责归一：补 `account` 与 `account_uid`、为没有结果的平台补占位。runner 返回的结果**不必**自己填 `account_uid`。

`format_community_sign_results()` 输出 `{platform: [{account_alias, account_uid, games: [...]}]}`；`merge_community_sign_results()` 按 `account_uid` 替换受影响账号，避免旧成功状态遮蔽新失败结果。塔吉多的社区级结果（`幻塔社区`/`异环社区`/`塔吉多社区`）不进入游戏详情列表，但**只过滤已完成的**：平台整体失败时 `error_game` 也用社区名占位，一并过滤会让前端完全看不到塔吉多的失败。

「角色列表非空、但解析出 0 个可签到的角色」会产出**可见**的失败行（米游社、库街区都带「角色列表返回 N 条」）：这条几乎只出现在新游戏未支持或上游结构变化时。只有角色记录数本身为 0（用户没绑游戏）才退回静默占位。排查时先看这条失败行的 `reason`。

## 日志分级

`_is_expected_provider_exception()` 是**唯一**的分级依据，`run_community_provider()` 据此选择 `logger.warning` 还是 `logger.exception`：

- 可预期（`warning` + 带消息给用户）：`ValueError`、`httpx.HTTPError`、`TimeoutError`、`ConnectionError`；以及消息中含 `token`/`cookie`/`凭据`/`登录`/`风控`/`请求`/`接口`/`网络`/`offline`/`timeout`/`timed out` 的 `RuntimeError`。
- 非预期（`exception` + 只给用户泛化文案）：其余全部。

凭据失效和上游风控是**正常运行状态**，不应刷栈。新增平台若抛自定义异常，让它继承 `ValueError` 或在消息里带上述关键词，不要扩大类型白名单来将就实现。

## 触发路径

| 入口 | 特点 |
| --- | --- |
| `POST /api/tools/sign`（`manual_game_sign`） | `force=True`；通知走快路径，超时后转后台，不阻塞响应 |
| `timer.schedule_community_for_startup` | 仅 `GameSign.Enabled` 且 `RunOnStartup`；后台任务持强引用并挂 `add_done_callback` |
| `timer.schedule_community_for_task` | 任务前置签到（`task_scheduled`/`task_manual`/`task_startup`），结果交由**任务完成通知**消费 |
| `timer.drain_community_tasks` | 电源动作前结清后台签到与补发，超时只停止等待、不取消工作 |

`GameSign.NotifyEnabled` 是通知总开关，每条路径都要检查。`check_community_system_time()` 只告警不阻断，且**不占签到锁**（以独立 task 起、finally 里取消）。时间源不可用时静默 `debug`；被取消的那一次不写检查缓存，否则接下来一个检查周期都会命中缓存、偏差提示不再出现。不要把它改成阻断条件。

## 已知不一致（改动时留意，不要照抄）

1. 端点专用输入输出模型放在所属 API 文件顶部；跨模块共享契约才放入 `app/models/schema.py`。配置字段由配置类派生，不重复声明凭据字段。
2. 路由 tag 不统一：账号组路由用 `tags=["GameSign"]`，手动签到用 `tags=["Action"]`，便笺查询用 `tags=["Community"]`，扫码用中文 `tags=["扫码登录"]`。沿用所在文件的既有 tag，不要顺手改动已生成客户端的方法名。
3. `miyoushe.py` 的 `QrSaveIn` 用 snake_case（`account_uid`），`accounts.py` 的账号组请求用 camelCase（`accountId`）。这是既有契约，改名会破坏生成客户端。账号组标识是 UUID，比较时走 `accounts.is_known_community_account()`，不要直接比字符串。
4. `ToolsConfig.GameSign.AutoStart` 只有字段声明、没有运行时消费者、也没有页面入口。它当前仍留在模型里（dev 现状）：删除它必须同时重新生成前端客户端，否则生成模型与后端不一致。
5. `CommunityTriggerSource` 里的 `"scheduled"` 目前没有任何入口会触发；新增定时签到要同时补触发点和 `should_run_community_for_source` 判定，只改字面量没有意义。
6. 扫码 `/check`（`miyoushe.py`、`skland_qr.py`）把上游 Passport 的**单行状态文案**当 `message` 回传，前端扫码弹窗直接显示它作为进度引导；真正的凭据是同一响应里的 `cookies_str` / `scan_code`，已单独处理。改成白名单等于枚举上游状态机，漏一个用户就看不到进度，所以保持现状。边界：只允许短状态文案，**不得**回传响应正文、HTML、堆栈或 Cookie。
