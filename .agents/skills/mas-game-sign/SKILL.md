---
name: mas-game-sign
description: >-
  Add, refactor, or review AUTO-MAS game community sign-in (game sign) code,
  including the provider registry in app/tools/game_sign.py, platform adapters
  for Skland/Miyoushe/Kuro/Taygedo, credential encryption and one-time login
  routes, sign-in locks and trigger paths, result and notification contracts,
  the GameSign account-group config, and the frontend gamesign views.
---

# 游戏社区签到

## 核心要义

签到是**凭据驱动的批量外部请求**，不是脚本适配。它的风险集中在三处：**用户凭据**、**上游风控**、**重复触发**。改动时先确认属于哪一层：

1. **平台适配层**（`app/tools/<platform>.py`）：单个社区的登录、角色发现、签到请求、风控退避。上游 API 知识来自被致谢的第三方项目，文件头的 AGPL/致谢声明必须保留。
2. **编排层**（`app/tools/game_sign.py`）：账号遍历、平台注册表、并发、锁、日期标记、凭据回写、结果归一。
3. **消费层**（`app/tools/game_sign_notify.py`、`game_sign_result.py`、API、前端）：结果展示与通知。

新增或修改平台时，**只应动第 1 层加注册表一行**。若发现必须改编排层才能容纳新平台，先停下来确认是不是抽象放错了位置。

## 当前架构

### 平台注册表是唯一入口

`app/tools/game_sign.py` 的 `_GAME_SIGN_PROVIDERS` 是不可变元组，每项 `_GameSignProvider(frozen=True)` 声明五件事：

| 字段 | 含义 |
| --- | --- |
| `token_field` | `GameSignAccountGroup` 上的凭据字段名，同时是「该平台是否已配置」的判据 |
| `log_name` | 日志与错误文案中的平台名 |
| `runner` | `async (token, account_name, account_uid) -> _ProviderRun` |
| `resolve_platforms` | 由凭据推导本次涉及的平台名元组 |
| `error_game` | 平台名 → 失败结果里的 `game` 字段 |

当前四项：`SklandToken`/森空岛、`MiyousheToken`/米游社、`KuroToken`/库街区、`TaygedoToken`/塔吉多。

`GAME_SIGN_TOKEN_FIELDS` 由注册表派生，`has_game_sign_credentials()` 又由它派生。**不要另写一份平台或字段清单**：调度台跳过账号、前端判空、通知分组都应回到注册表。

只有塔吉多使用动态 `resolve_platforms`（`_resolve_taygedo_platforms`）：一份凭据可能同时覆盖**塔吉多**与**云异环**两个平台名。其余三家用 `_fixed_platforms(...)` 返回单元素元组。新增「一份凭据对多平台」的社区时照塔吉多写，不要在 `runner` 里硬编码平台名。

### 后端文件职责

| 文件 | 职责 |
| --- | --- |
| `app/tools/game_sign.py` | 注册表、锁、编排、结果归一、`format_sign_results` / `merge_sign_results` |
| `app/tools/skland.py` | 森空岛：凭据校验、角色发现、签到、账号密码登录 |
| `app/tools/skland_response.py` | 森空岛响应形状判定（如 `is_skland_already_signed`），与请求逻辑分离 |
| `app/tools/miyoushe.py` | 米游社：DS 签名、多游戏签到 |
| `app/tools/miyoushe_qr.py` | 米游社扫码登录状态机 |
| `app/tools/kuro.py` | 库街区 |
| `app/tools/taygedo.py` | 塔吉多 + 云异环：账号密码登录、Token 刷新、凭据序列化 |
| `app/tools/game_sign_result.py` | 结果构建辅助（`SKLAND_GAME_MAPPING`、`build_skland_sign_results`） |
| `app/tools/game_sign_notify.py` | 通知文案格式化、平台排序、任务摘要挂载、多渠道推送与重试 |
| `app/api/tools.py` | 手动签到、账号组 CRUD、塔吉多/森空岛一次性登录 |
| `app/api/qr_login.py` | 米游社扫码登录三步路由 |
| `app/core/timer.py` | 自动签到触发、任务前置签到、全局日期标记 |

`app/tools/__init__.py` 的 `__all__` 只有四项：`run_all_sign_in`、`format_sign_results`、`login_skland_with_password`、`skland_sign_in`。其余符号按需从具体模块导入，且多数调用点使用**函数内延迟导入**以避免启动期循环依赖；沿用这个写法，不要为了「统一出口」把签到模块提到包顶层导入。

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
2. **加凭据字段**：在 `app/models/config.py` 的 `GameSignAccountGroup` 增加 `<Name>Token`，section 固定为 `"GameSignAccount"`，validator 必须是 `EncryptValidator()`，并在字段上方写 `## GameSignAccount - <说明> (DPAPI 加密)` 注释。
3. **加 schema 字段**：`app/models/schema.py` 的 `GameSignAccountGroupConfig` 增加同名可选字段。这是 API 出入口，字段名与配置项保持一致。
4. **写 provider runner**：在 `game_sign.py` 加 `_run_<platform>_provider()`，返回 `_ProviderRun(results=..., platforms=..., credential_updates=...)`。
5. **注册**：在 `_GAME_SIGN_PROVIDERS` 追加一项。`GAME_SIGN_TOKEN_FIELDS`、`has_game_sign_credentials()`、并发执行、凭据回写、日期标记全部自动生效。
6. **通知排序**：在 `game_sign_notify.py` 的 `_PLATFORM_ORDER` 追加平台名。缺失时该平台会落到排序尾部而不是报错，容易漏掉。
7. **重新生成 OpenAPI 客户端**，再在 `TabGameSign.vue` 加录入入口。禁止手改 `frontend/src/api/**`。

## 凭据与安全

签到是本仓少数直接持有**用户账号密码**的路径，规则从严：

1. 所有凭据字段用 `EncryptValidator()`（DPAPI 加密落盘）。新增凭据字段没有例外。
2. 一次性登录请求的密码字段用 `SecretStr`，用 `.get_secret_value()` 取值，**不落盘、不进日志**。
3. 登录路由的 `except Exception` 分支**禁止** `exc_info` / `logger.exception` / 回显上游响应，只返回固定文案。参见 `login_taygedo` / `login_skland` 的注释：避免密码、请求对象或上游响应进入日志。
4. `ValueError` 才允许把消息带给用户（凭据不完整、格式错误等可预期原因）；其他异常统一返回泛化文案。
5. 登录成功后必须**校验凭据完整性**再落盘（塔吉多校验 `accessToken`/`refreshToken`/`uid`，森空岛校验 `oauthToken`/`token`/`cred`），缺字段视为登录失败。
6. 凭据刷新走 `_ProviderRun.credential_updates`：编排层在并发完成后统一比对新旧值并写回，值未变则跳过。**不要**在 runner 内部直接写 `account.set()`。
7. 读取凭据统一用 `_read_game_sign_token()`：它容忍旧账号对象缺少新增字段（`AttributeError` / `KeyError` 均返回空串）。直接 `account.get(...)` 会在旧配置上炸。

## 并发与重复触发

两把锁，语义不同，不要合并：

| 锁 | 覆盖范围 | 违反时 |
| --- | --- | --- |
| `_game_sign_flow_lock`（`game_sign_flow()` 上下文管理器） | 签到请求 **加** 结果落盘。通知在锁外发送。 | 直接抛 `GameSignInProgressError`，不排队等待 |
| `_game_sign_lock`（`run_all_sign_in` 内部） | 全局签到执行，配合 `_game_sign_lock_owner` ContextVar 支持**同任务嵌套重入** | 同上 |

两把锁都是**快速失败**而非等待：`if lock.locked(): raise`。API 层把 `GameSignInProgressError` 映射为 `code=409`；`timer` 层降级为 `logger.info` 后跳过本次触发。新增触发入口时必须选一种处理，不要静默 `await` 到锁释放。

通知**必须在流程锁外**发送。慢渠道会阻塞后续操作，这是锁边界画在落盘之后的原因。

**日期标记有两层**，不要混用：

- 账号级 `GameSignAccount.LastSignDate`：`_run_all_sign_in` 内按账号写。自动模式（`force=False`）即使失败也标记当天，避免后续 MAS 任务反复请求上游；手动模式（`force=True`）仅在该账号所有已配置平台完成后才标记。
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

**成功判据在三处重复出现**（`_all_enabled_platforms_signed`、`manual_game_sign`、`game_sign_notify._SUCCESS_STATUSES`）：`status in ("成功", "已签到") or _completed`。改成功语义时必须同步这三处。

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
| `POST /api/tools/sign`（`manual_game_sign`） | `force=True`；通知走 `_dispatch_game_sign_notification`，`asyncio.shield` + 0.1s 超时后转后台，不阻塞响应 |
| `timer._execute_game_sign(source=...)` | `force=False`；`source` 在 `_TASK_GAME_SIGN_SOURCES` 内时结果交由**任务完成通知**消费，其余自动来源单独推送 |
| `timer.try_game_sign_for_task` | MAS 任务前置签到 |

`GameSign.NotifyEnabled` 是通知总开关，两条路径都要检查。后台通知任务必须持有强引用（`_PENDING_GAME_SIGN_NOTIFICATIONS`）并挂 `add_done_callback` 记录失败，否则任务可能被 GC。

`_check_system_time()` 只告警不阻断，且**不占签到锁**（在 `run_all_sign_in` 里以独立 task 起、finally 里取消）。时间源不可用时静默 `debug`。不要把它改成阻断条件。

## 已知不一致（改动时留意，不要照抄）

1. `app/api/qr_login.py` 把 `QrCreateOut` / `QrCheckIn` / `QrCheckOut` / `QrSaveIn` **定义在路由文件内**，其余签到 schema 都在 `app/models/schema.py`。新增签到 schema 放 `schema.py`。
2. 路由 tag 不统一：`tools.py` 的账号组路由用 `tags=["GameSign"]`，手动签到用 `tags=["Action"]`，`qr_login.py` 用中文 `tags=["扫码登录"]`。沿用所在文件的既有 tag，不要顺手改动已生成客户端的方法名。
3. `qr_login.py` 的 `QrSaveIn` 用 snake_case（`account_uid`），`tools.py` 的账号组请求用 camelCase（`accountId`）。这是既有契约，改名会破坏生成客户端。
4. `GameSign_WindowStart` / `WindowEnd` / `ScheduledRun` / `ScheduledTime` 是**保留读取历史配置**的旧字段，不参与调度。不要据此推断当前调度行为。

## 审查清单

- [ ] 新平台只改了适配模块 + 注册表一项，未在编排层加平台分支
- [ ] 凭据字段使用 `EncryptValidator()`，schema 侧同名字段已加
- [ ] 一次性登录密码用 `SecretStr`，异常分支未记录堆栈或上游响应
- [ ] 登录成功后校验了凭据完整性才落盘
- [ ] 凭据刷新经 `credential_updates` 回写，runner 内未直接写配置
- [ ] 读凭据走 `_read_game_sign_token()`，兼容缺字段的旧账号
- [ ] 新增触发入口显式处理 `GameSignInProgressError`（409 或跳过），未静默等待锁
- [ ] 通知在流程锁**外**发送，后台通知任务持有强引用
- [ ] 成功判据三处（`_all_enabled_platforms_signed`、`manual_game_sign`、`_SUCCESS_STATUSES`）保持一致
- [ ] 账号级与全局 `LastSignDate` 语义未混用；跨 0 点重取日期的行为保留
- [ ] 新平台已加入 `_PLATFORM_ORDER`
- [ ] 可预期失败走 `warning`，未因新异常类型扩大白名单
- [ ] `_notification_only` 结果未进前端列表
- [ ] 未手改 `frontend/src/api/**`；后端 schema 变更后已提示重新生成

## 最小验证

按 `tests/AGENTS.md`，签到测试归 `tests/tools/`（通用工具与外部平台交互）。现有入口：

```bash
python -m pytest tests/tools/test_game_sign.py tests/tools/test_game_sign_notification.py -q
```

其余相关入口按改动范围选择：`test_skland_response.py`、`test_skland_proxy.py`、`test_miyoushe_qr.py`、`test_miyoushe_retry.py`、`test_contracts.py`。

改通知文案或分组走 `test_game_sign_notification.py`；改编排、锁或结果归一走 `test_game_sign.py`。前端改动只运行实际受影响的 `*.test.ts`。非必要不新增测试；有缺口就在结果里说明，不编造验证结果。

## 避免

1. 不要为签到引入通用「平台配置引擎」或字段元数据表。四个平台的差异在**请求协议**，不在字段形状。
2. 不要在 `useGameSignApi.ts` 里写业务判断或错误吞掉逻辑。
3. 不要把 `_check_system_time()` 变成阻断条件，也不要让它占用签到锁。
4. 不要在编排层按平台名写 `if`。需要平台差异时加 provider 字段。
5. 不要新增第二份平台清单或凭据字段清单。
6. 不要把凭据、密码或上游原始响应写进日志或 API 错误消息。


