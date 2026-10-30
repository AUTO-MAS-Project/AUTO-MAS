---
name: mas-game-community
description: >-
  Add, refactor, or review AUTO-MAS game community (游戏社区) code: sign-in
  orchestration and the provider registry in app/tools/community_sign*.py,
  community daily-activity snapshots (日常便笺) in
  app/tools/community_activity*.py, platform adapters for
  Skland/Miyoushe/CloudGenshin/Kuro/Taygedo, credential parsing and one-time
  login routes, the community HTTP client, trigger paths and locks in
  app/core/timer.py and app/core/task_report.py, result and notification
  contracts in app/tools/community_notify.py, the GameSign account-group
  config, and the frontend gamesign views.
---

# 游戏社区（签到 + 日常便笺）

游戏社区由两件事共用一套凭据与账号组：**签到**（凭据驱动的批量外部请求）与**日常便笺**（按角色拉取活跃度）。两者都不是脚本适配，风险集中在三处：**用户凭据**、**上游风控**、**重复触发**。

## 代码归属（已收拢到 tools 一侧）

社区的业务实现全部位于 `app/tools/community*`；其余层只做时机、整形与展示。新增社区能力时不要往 `app/core`、`app/services`、`app/utils` 里散落社区逻辑。

| 层 | 位置 | 职责 |
| --- | --- | --- |
| 统一入口 | `app/tools/community.py` | 对外 facade；旧签到标识（`GameSignInProgressError`、`CommunityToolInProgressError`、`parse_community_activity_snapshot`）仅在此保留 |
| 签到编排 | `app/tools/community_sign.py` | 两把签到锁、账号遍历、并发执行、凭据回写、日期标记、系统时钟提示 |
| 平台注册表 | `app/tools/community_sign_provider.py` | `_COMMUNITY_SIGN_PROVIDERS`、runner、结果归一、`format_community_sign_results` / `merge_community_sign_results`、`check_community_system_time` |
| 凭据边界 | `app/tools/community_credentials.py` | 凭据外形解析（`empty`/`opaque`/`cookie`/`json`）与本地校验分派，不保存、不截断、不改写原始 Token |
| 结果契约 | `app/tools/community_contract.py` | `CommunitySignResult`、`CommunitySignDetail`、`CredentialStatus`、`CommunityActivitySnapshot`、`CommunitySignInProgressError` |
| 结果构建 | `app/tools/community_sign_result.py` | `build_skland_sign_results`、`merge_community_sign_result` |
| 通知 | `app/tools/community_notify.py` | 文本/Markdown/HTML/图片渲染、多渠道分发、渠道级失败系统提示 |
| 插件目录 | `app/tools/community_plugins.py` | 外部社区插件能力清单，纯静态，不联网 |
| 日常便笺消费层 | `app/tools/community_activity.py` | 账号组 → 快照、300s 缓存与 revision 失效 |
| 便笺四件套 | `app/tools/community_activity_roles.py`、`community_activity_provider.py`、`community_activity_transport.py`、`community_activity_parser.py` | 角色归一、上游请求与签名、请求构建与并发采集、响应解析（详见 [references/community-activity.md](references/community-activity.md)） |
| 触发策略 | `app/tools/community_scheduler.py` | `CommunityTriggerSource`、触发条件判定、便笺查询锁 |
| 账号命名 | `app/tools/community_accounts.py` | 默认账号组命名（`用户 1` 与 `用户1` 视为同一编号） |
| HTTP | `app/tools/community_http.py` | `create_community_client`：保留显式代理、忽略环境代理、连接失败时走 DoH 回退，默认超时 30s（`DEFAULT_REQUEST_TIMEOUT`，单请求可覆盖） |
| 平台适配器 | `app/tools/{skland,miyoushe,miyoushe_qr,kuro,taygedo,cloud_genshin}.py` | 单社区登录、角色发现、签到请求、风控退避 |
| 触发时机 | `app/core/timer.py` | 启动/任务前置触发、结果落盘、全局 `LastSignDate`、通知分流、电源动作前结清 |
| 任务报告 | `app/core/task_report.py` | 任务完成通知与社区结果合并、迟到补发、退出时取消补发 |
| 配置写入 | `app/core/config.py` | 账号组 CRUD、结果合并持久化与 WS 广播、便笺缓存订阅 |
| API | `app/api/tools.py`、`app/api/qr_login.py`、`app/api/skland_qr.py` | 手动签到、账号组 CRUD、塔吉多一次性登录、米游社/森空岛扫码、便笺查询 |
| 配置 | `app/models/config/tools.py` | `GameSignAccountGroup.GameSignAccountFields`（section 固定 `GameSignAccount`）与 `ToolsConfig.GameSignFields` |
| 前端 | `frontend/src/views/gamesign/**`、`frontend/src/stores/communityActivity.ts`、`frontend/src/views/home/**` | 页面容器、账号组、便笺卡片、主页签到统计 |

`app/tools/__init__.py` 的 `__all__` 只保留四个符号；其余符号按模块导入，多数调用点使用**函数内延迟导入**以避免启动期循环依赖——沿用这个写法，不要为了「统一出口」把社区模块提到包顶层。

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
2. **加凭据字段**：在 `app/models/config/tools.py` 的 `GameSignAccountFields` 增加 `<Name>Token`，类型用 `Annotated[str, encrypted()]`，描述必须以 `GameSignAccount - ` 开头并注明 DPAPI 加密。
3. **登记校验器**：在 `app/tools/community_credentials.py` 的 `_CREDENTIAL_VALIDATORS` 加一项，指向适配器的本地校验函数。
4. **写 provider runner**：在 `community_sign_provider.py` 加 `_run_<platform>_provider()`，返回 `_CommunityProviderRun(results=..., platforms=..., credential_updates=...)`。
5. **注册**：在 `_COMMUNITY_SIGN_PROVIDERS` 追加一项。凭据字段表、并发执行、凭据回写、日期标记全部自动生效。
6. **通知排序**：在 `community_notify.py` 的 `_PLATFORM_ORDER` 追加平台名。缺失时该平台会落到排序尾部而不是报错，容易漏掉。
7. **重新生成 OpenAPI 客户端**，再在 `TabGameSign.vue` 加录入入口。禁止手改 `frontend/src/api/**`。

## 凭据与安全

游戏社区是本仓少数直接持有**用户账号密码**的路径，规则从严：

1. 所有凭据字段（含米游社设备 ID/指纹）必须加密落盘，新增字段没有例外。
2. 一次性登录请求的密码字段用 `SecretStr`，用 `.get_secret_value()` 取值，**不落盘、不进日志**。
3. 登录路由的 `except Exception` 分支**禁止** `exc_info` / `logger.exception` / 回显上游响应，只返回固定文案（参见 `login_taygedo` 的注释）。
4. 只有 `ValueError` 允许把消息带给用户（凭据不完整、格式错误等可预期原因）；其他异常统一返回泛化文案。
5. 登录成功后必须**校验凭据完整性**再落盘（塔吉多校验 `accessToken`/`refreshToken`/`uid`，森空岛校验 `oauthToken`/`token`/`cred`），缺字段视为登录失败。
6. 凭据刷新走 `_ProviderRun.credential_updates`：runner 内**不要**直接写配置；即时回写通过 `on_credential_update` 回调，收尾由编排层统一比对并重试。
7. 读取凭据统一用 `read_community_token()`：容忍旧账号对象缺少新增字段（`AttributeError` / `KeyError` 返回空串）。直接 `account.get(...)` 会在旧配置上炸。
8. 日志只允许出现凭据**字段名**与状态，不允许出现凭据值、Cookie 或上游原始响应；异常栈同理。

## 并发与重复触发

四把锁语义不同，不要合并：

| 锁 | 位置 | 覆盖范围 | 违反时 |
| --- | --- | --- | --- |
| `community_sign_flow()` | `community_sign.py` | 签到请求 **加** 结果落盘；通知在锁外 | 直接抛 `CommunitySignInProgressError`，不排队 |
| `_community_sign_lock` | `community_sign.py` | 全局签到执行，配合 `_community_sign_lock_owner` ContextVar 支持**同任务嵌套重入** | 同上，快速失败 |
| `skland_sign_lock` | `skland.py` | 森空岛签到全流程与养成练度源共用，互斥签名 token 的两个轮换写者 | 串行等待 |
| `community_activity_flow()` | `community_scheduler.py` | 日常便笺查询串行化；后到者等锁后复用缓存 | 串行等待（不抛错） |

签到锁是**快速失败**而非等待：`if lock.locked(): raise`。API 层把 `CommunitySignInProgressError` 映射为 `code=409`；timer 层降级为 `logger.info` 后跳过本次触发（任务来源则原样抛出，由任务完成回调交付异常终态）。新增触发入口时必须选一种处理，不要静默 `await` 到锁释放。

练度源的凭据回写走注入的 `save_credential` 回调（`app/core/config.py`），不进 `credential_updates`——它不是注册表 runner；改这两条链路时必须保住 `skland_sign_lock`，否则会把对方刚回写的 token 作废。编排层收尾回写前会重读存量、发现已被别的链路轮换即跳过写入，也是防同一件事。

通知**必须在流程锁外**发送。慢渠道会阻塞后续操作，这是锁边界画在落盘之后的原因。

**日期标记有两层**，不要混用：

- 账号级 `GameSignAccount.LastSignDate`：由 `run_community_sign_in` 按账号写。自动模式（`force=False`）即使失败也标记当天，避免后续 MAS 任务反复请求上游；手动模式（`force=True`）仅在该账号所有已配置平台完成后才标记。
- 全局 `GameSign.LastSignDate`：由调用方（`timer` / `manual_game_sign`）在**所有**启用且有凭据的账号都完成后才写。

多账号串行签到可能跨越 0 点，写入时**重新取当前日期**而不是复用循环开始时的 `today`。改这段逻辑要保留这个行为。

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

- `_notification_only`：占位结果（如「未获取到可签到角色」）。它只参与「本轮有没有结果」的判断，`format_community_sign_results` 与 `filter_community_notification_results` 都会过滤它，前端和通知都看不到；某账号本轮全是占位时一条通知都不会发（这是既定口径，不是缺陷）。
- `_completed`：流程已跑完、但没拿到明确成功状态的旁路标记（如云异环没确认到新增时长）。

**成功判据只有一处实现**：`community_contract.is_community_sign_completed()`，即 `status in ("成功","已签到") or _completed`。编排层 `all_enabled_community_platforms_signed`、手动端点 `manual_game_sign`、通知的 ✅/❌ 与 (x/y) 计数全部走它，改成功语义只改这一处；不要再在别处手写状态元组。前端标签云仍按 `status` 判定，`_completed` 行显示为失败，属于已知差异（该组合只在同一天二次确认云异环时出现）。

`_decorate_provider_run()` 负责归一：补 `account` 与 `account_uid`、为没有结果的平台补占位。runner 返回的结果**不必**自己填 `account_uid`。

`format_community_sign_results()` 输出 `{platform: [{account_alias, account_uid, games: [...]}]}`；`merge_community_sign_results()` 按 `account_uid` 替换受影响账号，避免旧成功状态遮蔽新失败结果（`replace` 参数已退化为兼容占位，两条路径行为相同）。塔吉多的社区级结果（`幻塔社区`/`异环社区`/`塔吉多社区`）不进入游戏详情列表，但**只过滤已完成的**：平台整体失败时 `error_game` 也用社区名占位，一并过滤会让前端完全看不到塔吉多的失败。

## 日志分级

`_is_expected_provider_exception()` 是**唯一**的分级依据，`run_community_provider()` 据此选择 `logger.warning` 还是 `logger.exception`：

- 可预期（`warning` + 带消息给用户）：`ValueError`、`httpx.HTTPError`、`TimeoutError`、`ConnectionError`；以及消息中含 `token`/`cookie`/`凭据`/`登录`/`风控`/`请求`/`接口`/`网络`/`offline`/`timeout`/`timed out` 的 `RuntimeError`。
- 非预期（`exception` + 只给用户泛化文案）：其余全部。

凭据失效和上游风控是**正常运行状态**，不应刷栈。新增平台若抛自定义异常，让它继承 `ValueError` 或在消息里带上述关键词，不要扩大类型白名单来将就实现。

## 触发路径

| 入口 | 特点 |
| --- | --- |
| `POST /api/tools/sign`（`manual_game_sign`） | `force=True`；通知走快路径 `asyncio.shield` + 1.1s（`NOTIFICATION_FAST_PATH_WAIT_SECONDS`）超时后转后台，不阻塞响应；渠道级失败另有系统提示兜底 |
| `timer.schedule_community_for_startup` | 仅 `GameSign.Enabled` 且 `RunOnStartup`；后台任务持强引用并挂 `add_done_callback` |
| `timer.schedule_community_for_task` | 任务前置签到（`task_scheduled`/`task_manual`/`task_startup`），结果交由**任务完成通知**消费 |
| `timer.drain_community_tasks` | 电源动作前结清后台签到与补发，超时只停止等待、不取消工作 |

`GameSign.NotifyEnabled` 是通知总开关，每条路径都要检查（`timer`、`manual_game_sign`、`task_report`）。后台通知任务必须持有强引用（`_PENDING_TASK_COMMUNITY_NOTIFICATIONS`）并挂 `add_done_callback`，否则任务可能被 GC；渠道级失败由 `push_community_notification` 另发一条系统提示（`Config.push_system_notice`），不只写日志。退出时由 `shutdown_community_notifications()` 取消并等待。

`check_community_system_time()` 只告警不阻断，且**不占签到锁**（以独立 task 起、finally 里取消）。时间源不可用时静默 `debug`；被取消的那一次不写检查缓存，否则接下来一个检查周期都会命中缓存、偏差提示不再出现。不要把它改成阻断条件。

## 已知不一致（改动时留意，不要照抄）

1. `app/api/qr_login.py`、`app/api/skland_qr.py` 把 `QrCreateOut` / `QrCheckIn` / `QrCheckOut` / `QrSaveIn` 一类 schema **定义在路由文件内**。新增社区 schema 优先放所属 `api` 模块顶部或 `app/models/schema.py`，不要照搬。
2. 路由 tag 不统一：账号组路由用 `tags=["GameSign"]`，手动签到用 `tags=["Action"]`，便笺查询用 `tags=["Community"]`，扫码用中文 `tags=["扫码登录"]`。沿用所在文件的既有 tag，不要顺手改动已生成客户端的方法名。
3. `qr_login.py` 的 `QrSaveIn` 用 snake_case（`account_uid`），`tools.py` 的账号组请求用 camelCase（`accountId`）。这是既有契约，改名会破坏生成客户端。
4. `ToolsConfig.GameSign.AutoStart` **已移除**：它只有字段声明、没有运行时消费者，也没有页面入口。不要在旧配置看到它就复活：`Result` / `Status` 是虚拟字段，剩余的历史键由配置框架 `extra="ignore"` 忽略。
5. `CommunityTriggerSource` 里的 `"scheduled"` **已移除**：没有任何入口会触发它。`timer._execute_community_sign(source=...)` 现在必须显式传来源；新增定时签到要同时补触发点和 `should_run_community_for_source` 判定，否则只是改了一个字面量。
6. 扫码 `/check`（`qr_login.py`、`skland_qr.py`）把上游 Passport 的**单行状态文案**（未扫描/已扫描待确认/已取消）当 `message` 回传，前端扫码弹窗直接显示它作为进度引导；真正的凭据是同一响应里的 `cookies_str` / `scan_code`，已单独处理。改成白名单等于枚举上游状态机，漏一个用户就看不到进度，所以保持现状。边界：只允许短状态文案，**不得**回传响应正文、HTML、堆栈或 Cookie；新增扫码接口仍按白名单写本地文案。
7. 「角色列表非空、但解析出 0 个可签到的角色」现在会产出**可见**的失败行（米游社、库街区都带「角色列表返回 N 条」），因为这条几乎只出现在新游戏未支持或上游结构变化时。只有角色记录数本身为 0（用户没绑游戏）才退回静默占位。排查时先看这条失败行的 reason。

## 审查清单

- [ ] 新平台只改了适配模块 + 校验器一项 + 注册表一项，未在编排层加平台分支
- [ ] 凭据字段已加密，配置描述以 `GameSignAccount - ` 开头
- [ ] 一次性登录密码用 `SecretStr`，异常分支未记录堆栈或上游响应
- [ ] 登录成功后校验了凭据完整性才落盘
- [ ] 凭据刷新经 `credential_updates` / `on_credential_update` 回写，runner 内未直接写配置
- [ ] 读凭据走 `read_community_token()`，兼容缺字段的旧账号
- [ ] 新增触发入口显式处理 `CommunitySignInProgressError`（409 或跳过），未静默等待锁
- [ ] 通知在流程锁**外**发送，后台通知任务持有强引用
- [ ] 成功判据只走 `is_community_sign_completed()`，没有新增手写状态元组
- [ ] 账号级与全局 `LastSignDate` 语义未混用；跨 0 点重取日期的行为保留
- [ ] 凭据的即时写穿与收尾回写都先重读存量，不会覆盖用户刚登录保存的新凭据
- [ ] 遍历账号组用 `list(keys())` 取快照再 `get()`，签到期间删除账号组不会中断整轮签到
- [ ] 新平台已加入 `_PLATFORM_ORDER`
- [ ] 可预期失败走 `warning`，未因新异常类型扩大白名单
- [ ] `_notification_only` 结果未进前端列表
- [ ] 未手改 `frontend/src/api/**`；配置/schema 变更后已提示重新生成
- [ ] 社区业务逻辑没有新落在 `app/core`、`app/services`、`app/utils`

## 最小验证

- 后端：`python -m pytest tests/tools tests/core/test_notify.py -q`（签到、便笺解析、通知与任务报告口径）。
- 前端：只运行实际受影响的 `*.test.ts`。
- 按 `tests/AGENTS.md`，开发期的签到/便笺验证脚本属于一次性产物，默认不提交；有缺口就在结果里说明，不编造验证结果。

## 参考

- 日常便笺链路（角色发现、请求签名、缓存与状态语义）：[references/community-activity.md](references/community-activity.md)
- 通知与任务报告（渲染、多渠道、迟到补发、结清）：[references/community-notification.md](references/community-notification.md)
- 配置声明、事务、锁与序列化：[配置框架参考](../mas-data-model/references/config-framework.md)

## 避免

1. 不要为社区引入通用「平台配置引擎」或字段元数据表。五个平台的差异在**请求协议**，不在字段形状。
2. 不要在 `useGameSignApi.ts` / `useCommunityActivityApi.ts` 里写业务判断或错误吞掉逻辑。
3. 不要把 `check_community_system_time()` 变成阻断条件，也不要让它占用签到锁。
4. 不要在编排层按平台名写 `if`。需要平台差异时加 provider 字段。
5. 不要新增第二份平台清单、凭据字段清单或通知平台顺序。前端的五款游戏清单只有一份：`frontend/src/views/gamesign/communityGames.ts`；各处的游戏映射表用 `Record<CommunityGame, …>` 绑定它，新增游戏漏映射会直接变成类型错误。
6. 不要把凭据、密码、上游响应正文（HTML/JSON 全文）或异常栈写进日志与 API 错误消息；扫码 `/check` 需要的单行状态文案按「已知不一致 6」的边界处理。
7. 不要把社区业务逻辑重新放进 `app/core`、`app/services`、`app/utils`；这几层只保留时机、整形与展示。
