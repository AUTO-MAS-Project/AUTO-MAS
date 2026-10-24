---
name: mas-game-sign
description: >-
  Add, refactor, or review AUTO-MAS game community sign-in (game sign) code,
  including app/core/community_sign.py and its provider registry, platform adapters
  for Skland/Miyoushe/Kuro/Taygedo, credential encryption and one-time login
  routes, sign-in locks and trigger paths, result and notification contracts,
  the GameSign account-group config, and the frontend gamesign views.
---

# 游戏社区签到

## 代码与配置定位

当前签到编排位于 `app/core/community_sign.py`，provider 注册及凭据读取位于 `app/tools/community_sign_provider.py`，配置位于 `app/models/config/tools.py`。本技能中的业务约束按实际符号和调用者核对；配置声明、事务、锁、日期与序列化统一遵循[配置框架参考](../mas-data-model/references/config-framework.md)。

## 核心要义

签到是**凭据驱动的批量外部请求**，不是脚本适配。它的风险集中在三处：**用户凭据**、**上游风控**、**重复触发**。改动时先确认属于哪一层：

1. **平台适配层**（`app/tools/<platform>.py`）：单个社区的登录、角色发现、签到请求、风控退避。上游 API 知识来自被致谢的第三方项目，文件头的 AGPL/致谢声明必须保留。
2. **编排层**（`app/core/community_sign.py`）：账号遍历、并发、锁、日期标记和凭据回写；平台注册表及结果归一由 `app/tools/community_sign_provider.py` 提供。
3. **消费层**（`app/tools/community_notify.py`、`game_sign_result.py`、API、前端）：结果展示与通知。

新增或修改平台时，**只应动第 1 层加注册表一行**。若发现必须改编排层才能容纳新平台，先停下来确认是不是抽象放错了位置。

## 当前架构

### 平台注册表是唯一入口

`app/tools/community_sign_provider.py` 的 `_COMMUNITY_SIGN_PROVIDERS` 是不可变元组，每项 `_CommunitySignProvider(frozen=True)` 声明五件事：

| 字段 | 含义 |
| --- | --- |
| `token_field` | `GameSignAccountGroup` 上的凭据字段名，同时是「该平台是否已配置」的判据 |
| `log_name` | 日志与错误文案中的平台名 |
| `runner` | 按 `ProviderRunner` 签名执行平台请求，返回 `_CommunityProviderRun`，支持编排层提供的凭据刷新回调 |
| `resolve_platforms` | 由凭据推导本次涉及的平台名元组 |
| `error_game` | 平台名 → 失败结果里的 `game` 字段 |

平台及其凭据字段以当前注册表为准。`COMMUNITY_TOKEN_FIELDS` 由注册表派生，`has_community_credentials()` 又由它派生。**不要另写一份平台或字段清单**：调度台跳过账号、前端判空、通知分组都应回到注册表。

塔吉多通过动态 `resolve_platforms`（`_resolve_taygedo_platforms`）使一份凭据覆盖**塔吉多**与**云异环**等平台名；固定平台使用 `_fixed_platforms(...)`。新增「一份凭据对多平台」的社区时沿用注册表解析方式，不在编排层硬编码平台分支。

### 后端文件职责

| 文件 | 职责 |
| --- | --- |
| `app/core/community_sign.py` | 锁、账号遍历、签到编排及配置回写 |
| `app/tools/community_sign_provider.py` | 注册表、凭据读取、平台调度、结果格式化与合并 |
| `app/tools/skland.py` | 森空岛：凭据校验、角色发现、签到、账号密码登录；绑定列表与玩家整表数据（`player/info`）的公共拉取（`fetch_skland_bindings` / `fetch_skland_player_info`），供签到与养成练度源共用 |
| `app/tools/skland_response.py` | 森空岛响应形状判定（如 `is_skland_already_signed`），与请求逻辑分离 |
| `app/tools/miyoushe.py` | 米游社：DS 签名、多游戏签到 |
| `app/tools/miyoushe_qr.py` | 米游社扫码登录状态机 |
| `app/tools/kuro.py` | 库街区 |
| `app/tools/taygedo.py` | 塔吉多 + 云异环：账号密码登录、Token 刷新、凭据序列化 |
| `app/tools/game_sign_result.py` | 结果构建辅助（`SKLAND_GAME_MAPPING`、`build_skland_sign_results`） |
| `app/tools/community_notify.py` | 通知文案格式化、平台排序、任务摘要挂载、多渠道推送与重试 |
| `app/api/tools.py` | 手动签到、账号组 CRUD、塔吉多/森空岛一次性登录 |
| `app/api/qr_login.py` | 米游社扫码登录三步路由 |
| `app/core/timer.py` | 自动签到触发、任务前置签到、全局日期标记 |

签到公开入口从实际所属模块导入，配置编排使用 `app/core/community_sign.py`，provider 能力使用对应 tools 模块。现有函数内延迟导入承担启动期循环依赖隔离；普通配置适配不将这些模块提到包顶层统一加载。

### 前端表面

| 位置 | 内容 |
| --- | --- |
| `frontend/src/views/gamesign/index.vue` | 页面容器 |
| `frontend/src/views/gamesign/TabGameSign.vue` | 账号组列表、凭据录入、扫码弹窗、结果展示 |
| `frontend/src/views/gamesign/useGameSignApi.ts` | 仅包装生成的 `Service.*`，无业务判断 |

`useGameSignApi.ts` 是薄封装：每个方法一行转发到 `@/api` 的生成客户端。新增路由时在此加一行并从返回对象导出，**不要**在此写状态、缓存或错误吞掉逻辑。

## 新增一个签到平台

按此顺序，每步都能独立自查：

1. **写平台适配模块** `app/tools/<platform>.py`。对外只暴露一个「跑一次签到」的入口与必要的凭据解析/校验函数。若参考了第三方项目的接口知识，按现有模块的写法在文件头加致谢与许可声明。
2. **加凭据字段**：在 `app/models/config/tools.py` 的 `GameSignAccountGroup.GameSignAccountFields` 声明 `<Name>Token: Annotated[str, encrypted()]`，通过 `Field` 提供默认值和中文说明，保持 `GameSignAccount` 分组。模型与写入规则见[配置框架参考](../mas-data-model/references/config-framework.md)。
3. **派生接口契约**：账号配置的 `ConfigInput/ConfigPayload` 从该配置类自动取得新字段；只调整端点包裹层实际需要的类型，不在 `schema.py` 手写一份凭据字段。端点专用模型在所属 API 模块，跨层共享契约在单文件 `schema.py`。
4. **写 provider runner**：在 `community_sign_provider.py` 加 `_run_<platform>_provider()`，返回 `_CommunityProviderRun(results=..., platforms=..., credential_updates=...)`，保持当前凭据更新回调契约。
5. **注册**：在 `_COMMUNITY_SIGN_PROVIDERS` 追加一项。`COMMUNITY_TOKEN_FIELDS`、`has_community_credentials()`、并发执行、凭据回写、日期标记通过已有链路消费。
6. **通知排序**：在 `community_notify.py` 的 `_PLATFORM_ORDER` 追加平台名。缺失时该平台会落到排序尾部而不是报错，容易漏掉。
7. **重新生成 OpenAPI 客户端**，再在 `TabGameSign.vue` 加录入入口。禁止手改 `frontend/src/api/**`。

## 凭据与安全

签到是本仓少数直接持有**用户账号密码**的路径，规则从严：

1. 凭据字段使用 `Annotated[str, encrypted()]`，标记位于元数据末尾；按同设备多用户兼容算法加密落盘。业务属性读取为明文，迁移明文导出使用管理器的 export 受众，日志和错误摘要不包含凭据。
2. 一次性登录请求的密码字段用 `SecretStr`，用 `.get_secret_value()` 取值，**不落盘、不进日志**。
3. 登录路由的 `except Exception` 分支**禁止** `exc_info` / `logger.exception` / 回显上游响应，只返回固定文案。参见 `login_taygedo` / `login_skland` 的注释：避免密码、请求对象或上游响应进入日志。
4. `ValueError` 才允许把消息带给用户（凭据不完整、格式错误等可预期原因）；其他异常统一返回泛化文案。
5. 登录成功后必须**校验凭据完整性**再落盘（塔吉多校验 `accessToken`/`refreshToken`/`uid`，森空岛校验 `oauthToken`/`token`/`cred`），缺字段视为登录失败。
6. 凭据刷新通过回调及 provider 结果的 `credential_updates` 交给编排层处理。当前 `app/core/community_sign.py` 以同类冷态部分模型调用 `await account.update(...)`，内部按字段暂存并提交，保留轮换期间的新值保护和重试语义。runner 中的网络并发不等于配置事务并发，配置关联写入遵循同 Task 提交边界。
7. 凭据读取复用当前 `app/tools/community_sign_provider.py` 的 `read_community_token()`，它通过分组属性读取并兼容缺失字段；配置实例没有通用旧式 `get/set` 访问约定。

## 并发与重复触发

两把锁，语义不同，不要合并：

| 锁 | 覆盖范围 | 违反时 |
| --- | --- | --- |
| `_community_sign_flow_lock`（`community_sign_flow()` 上下文管理器） | 签到请求 **加** 结果提交。通知在锁外发送。 | 直接抛 `CommunitySignInProgressError`，不排队等待 |
| `_community_sign_lock`（`run_community_sign_in` 内部） | 全局签到执行，配合 `_community_sign_lock_owner` ContextVar 支持**同任务嵌套重入** | 同上 |

两把业务流程锁都是**快速失败**而非等待：`if lock.locked(): raise`。API 层把 `CommunitySignInProgressError` 映射为冲突响应，自动触发层记录后跳过。它们区别于配置管理器的全局排队入口，新增触发保留既有快速失败契约；配置提交成功与防抖落盘完成分别判定。

森空岛另有模块级 `_skland_sign_lock`（公共别名 `skland_sign_lock`，`skland.py`）：签到全流程与**养成练度源**（`app/task/MAA/tools/cultivate/skland.py`）共用，互斥签名 token 的两个独立轮换写者。练度源的凭据回写走注入的 `save_credential` 回调（`core/config.py`），不进 `_ProviderRun.credential_updates`——它不是注册表 runner；改这两条链路时必须保住这把互斥锁，否则会把对方刚回写的 token 作废（`community_sign.py` 收尾回写前重读存量、发现已被轮换即跳过，也是防同一件事）。

通知**必须在流程锁外**发送。慢渠道会阻塞后续操作，这是锁边界画在落盘之后的原因。

**日期标记有两层**，不要混用：

- 账号级 `GameSignAccount.LastSignDate`：`run_community_sign_in` 内按账号写。字段为 UTC 存储、UTC+8 读取的完整 `datetime`，日级判断在读取后格式化；自动模式（`force=False`）即使失败也标记当天，手动模式（`force=True`）仅在该账号所有已配置平台完成后才标记。
- 全局 `GameSign.LastSignDate`：由调用方在**所有**启用且有凭据的账号都完成后才写。

多账号串行签到可能跨越 0 点，写入时**重新取当前日期**而不是复用循环开始时的 `today`。改这段逻辑要保留这个行为。

## 结果契约

编排层的 `results` 是 `list[dict]`，键固定：

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

- `_notification_only`：占位结果（如「未获取到可签到角色」），进通知但被 `format_sign_results` 过滤，不进前端列表。
- `_completed`：完成态旁路标记，参与「是否全部完成」判定。

**成功判据涉及编排、API 与通知**（`all_enabled_community_platforms_signed`、手动签到端点、`community_notify._SUCCESS_STATUSES`）：保持 `status in ("成功", "已签到") or _completed` 的既有业务含义，按实际调用链核对。

`_decorate_provider_run()` 负责归一：补 `account` 与 `account_uid`、为没有结果的平台补占位。runner 返回的结果**不必**自己填 `account_uid`。

`format_sign_results()` 输出 `{platform: [{account_alias, account_uid, games: [...]}]}`；`merge_sign_results()` 按 `account_uid` 替换受影响账号，避免旧成功状态遮蔽新失败结果（`replace` 参数已退化为兼容占位，两条路径行为相同）。

## 日志分级约定

`_is_expected_provider_exception()` 是**唯一**的分级依据，`_run_provider()` 据此选择 `logger.warning` 还是 `logger.exception`：

- 可预期（`warning` + 带消息给用户）：`ValueError`、`httpx.HTTPError`、`TimeoutError`、`ConnectionError`；以及消息中含 `token`/`cookie`/`凭据`/`登录`/`风控`/`请求`/`接口`/`网络`/`offline`/`timeout`/`timed out` 的 `RuntimeError`。
- 非预期（`exception` + 只给用户泛化文案）：其余全部。

凭据失效和上游风控是**正常运行状态**，不应刷栈。新增平台若抛自定义异常，让它继承 `ValueError` 或在消息里带上述关键词，不要扩大 `_is_expected_provider_exception` 的类型白名单来将就实现。

## 触发路径

| 入口 | 特点 |
| --- | --- |
| `POST /api/tools/sign`（`manual_game_sign`） | `force=True`；通知走 `_dispatch_community_notification`，`asyncio.shield` + 1.1s（`NOTIFICATION_FAST_PATH_WAIT_SECONDS`）超时后转后台，不阻塞响应；渠道级失败另有系统提示兜底 |
| `timer._execute_game_sign(source=...)` | `force=False`；`source` 在 `_TASK_GAME_SIGN_SOURCES` 内时结果交由**任务完成通知**消费，其余自动来源单独推送 |
| `timer.try_game_sign_for_task` | MAS 任务前置签到 |

`GameSign.NotifyEnabled` 是通知总开关，两条路径都要检查。后台通知任务必须持有强引用（`_PENDING_COMMUNITY_NOTIFICATIONS`）并挂 `add_done_callback`，否则任务可能被 GC；渠道级失败由 `push_community_notification` 另发一条系统提示（`Config.push_system_notice`），不只写日志。

`check_community_system_time()` 只告警不阻断，且**不占签到锁**（在 `run_community_sign_in` 里以独立 task 起、finally 里取消）。时间源不可用时静默 `debug`。被取消的那一次不写检查缓存（只在跑完后打点），否则接下来一个检查周期都会命中缓存、偏差提示不再出现。不要把它改成阻断条件。

## 已知不一致（改动时留意，不要照抄）

1. 端点专用请求、响应和子模型定义在对应 API 模块顶层；API 与业务层共同使用的消息和载荷留在 `app/models/schema.py`，配置字段由配置类派生。
2. 路由 tag 不统一：`tools.py` 的账号组路由用 `tags=["GameSign"]`，手动签到用 `tags=["Action"]`，`qr_login.py` 用中文 `tags=["扫码登录"]`。沿用所在文件的既有 tag，不要顺手改动已生成客户端的方法名。
3. `qr_login.py` 的 `QrSaveIn` 用 snake_case（`account_uid`），`tools.py` 的账号组请求用 camelCase（`accountId`）。这是既有契约，改名会破坏生成客户端。
4. `GameSign_WindowStart` / `WindowEnd` / `ScheduledRun` / `ScheduledTime` 是**保留读取历史配置**的旧字段，不参与调度。不要据此推断当前调度行为。

## 审查清单

- [ ] 新平台只改了适配模块 + 注册表一项，未在编排层加平台分支
- [ ] 凭据字段使用 `encrypted()` 并带默认值、说明，派生输入输出及页面已适配，无重复字段声明
- [ ] 一次性登录密码用 `SecretStr`，异常分支未记录堆栈或上游响应
- [ ] 登录成功后校验了凭据完整性才落盘
- [ ] 凭据刷新经 `credential_updates` 回写，runner 内未直接写配置
- [ ] 读凭据复用 `read_community_token()`，字段写入经分组属性赋值与 commit，省略/null/掩码语义保持一致
- [ ] 新增触发入口显式处理 `CommunitySignInProgressError`（冲突响应或跳过），未静默等待业务锁
- [ ] 通知在流程锁**外**发送，后台通知任务持有强引用
- [ ] 编排、手动签到端点和通知 `_SUCCESS_STATUSES` 的成功判据一致
- [ ] 账号级与全局 `LastSignDate` 语义未混用；跨 0 点重取日期的行为保留
- [ ] 新平台已加入 `_PLATFORM_ORDER`
- [ ] 可预期失败走 `warning`，未因新异常类型扩大白名单
- [ ] `_notification_only` 结果未进前端列表
- [ ] 未手改 `frontend/src/api/**`；后端契约变更后通过生成器更新

## 最小验证

按 `tests/AGENTS.md`，开发时在 `tests/tools/` 下编写签到测试用于本地验证（`test_game_sign.py`、`test_game_sign_notification.py`、`test_miyoushe_qr.py`、`test_miyoushe_retry.py`、`test_contracts.py` 等）。

提交或提 PR 时，测试文件的取舍见根目录 `AGENTS.md`「分支与 PR」。

前端改动只运行实际受影响的 `*.test.ts`。有缺口就在结果里说明，不编造验证结果。

## 避免

1. 不要为签到引入通用「平台配置引擎」或字段元数据表。四个平台的差异在**请求协议**，不在字段形状。
2. 不要在 `useGameSignApi.ts` 里写业务判断或错误吞掉逻辑。
3. 不要把 `_check_system_time()` 变成阻断条件，也不要让它占用签到锁。
4. 不要在编排层按平台名写 `if`。需要平台差异时加 provider 字段。
5. 不要新增第二份平台清单或凭据字段清单。
6. 不要把凭据、密码或上游原始响应写进日志或 API 错误消息。


