---
name: mas-game-community
description: >-
  Add, refactor, or review AUTO-MAS game community (游戏社区) code: sign-in
  orchestration, provider registry and result contract under
  app/tools/common/sign/, daily-activity snapshots (日常便笺) and the shared
  community base (contract, credentials, http, plugins, accounts, scheduler)
  under app/tools/common/, Skland/Miyoushe/CloudGenshin/Kuro/Taygedo adapters
  in app/tools/*.py, credential parsing and one-time login routes, trigger
  paths and locks in app/core/timer.py and app/core/task_report.py, the
  GameSign account-group config, and the frontend gamesign views.
---

# 游戏社区（签到 + 日常便笺）

游戏社区由两件事共用一套凭据与账号组：**签到**（凭据驱动的批量外部请求）与**日常便笺**（按角色拉取活跃度）。两者都不是脚本适配，风险集中在三处：**用户凭据**、**上游风控**、**重复触发**。

## 代码归属（硬规则）

社区的**全部**实现收束在 `app/tools/common/`：

| 位置 | 内容 |
| --- | --- |
| `app/tools/common/sign/` | 签到专属：`community_sign.py`（编排与两把锁）、`community_sign_provider.py`（平台注册表与结果归一）、`community_sign_result.py`（结果构建与合并） |
| `app/tools/common/` | 共享底座：`community.py`（facade）、`community_activity*.py`（便笺四件套 + 消费层）、`community_contract.py`、`community_credentials.py`、`community_http.py`、`community_plugins.py`、`community_accounts.py`、`community_scheduler.py`（触发来源判定与便笺锁） |
| `app/tools/{skland,miyoushe,miyoushe_qr,kuro,taygedo,cloud_genshin}.py` | 单平台适配器，留在 `app/tools/` 顶层 |
| `app/core/`、`app/api/` | 只放触发时机、结果落盘与请求响应整形 |

- 新增社区模块一律进 `app/tools/common/`；签到专属进 `app/tools/common/sign/`，便笺与跨两者的共享件留 `app/tools/common/` 根。
- **不要**再把社区业务逻辑放进 `app/core`、`app/services`、`app/utils`。既有例外只有通知管线（`app/core/community_notification.py` + `app/services/community_notification.py`），由 dev 维护，社区侧只负责产出结果与渲染数据。
- 导入一律写绝对路径 `app.tools.common.*`；`app/tools/__init__.py` 与调用点的**函数内延迟导入**是防启动期循环依赖的既有写法（`app/core/config.py` ↔ `sign/community_sign.py` 尤其敏感），不要为了「统一出口」把社区模块提到包顶层。
- 细节与命名规范见 [references/layout.md](references/layout.md)。

## 三条不能违反的语义

1. **平台注册表是唯一入口**：`_COMMUNITY_SIGN_PROVIDERS` 派生凭据字段表与「该平台是否已配置」判据；不要另写平台清单或凭据字段清单。见 [references/sign-in.md](references/sign-in.md)。
2. **成功判据只有一处**：`community_contract.is_community_sign_completed()`，即 `status in COMMUNITY_SIGN_SUCCESS_STATUSES or _completed`。编排、手动端点、通知计数全部走它。
3. **锁不合并、通知在锁外**：`community_sign_flow`、`_community_sign_lock`、`skland_sign_lock`、`community_activity_flow` 语义各不相同；签到锁**快速失败**（API 映射 409），便笺锁串行等待。

## 凭据与安全

社区是本仓少数直接持有**用户账号密码**的路径：凭据加密落盘、一次性登录用 `SecretStr`、异常分支不回显上游正文与堆栈、凭据刷新只经 `credential_updates` / `on_credential_update` 回写。细则见 [references/credentials.md](references/credentials.md)。

## 最小验证

- 后端：`python -m pytest tests/tools tests/core/test_notify.py tests/api -q`
- 前端：只跑受影响的 `*.test.ts`；配置/schema 变更后重新生成 OpenAPI 客户端，禁止手改 `frontend/src/api/**`
- 开发期的签到/便笺验证脚本属于一次性产物，默认不提交，也不新增社区 e2e 用例。

## 参考

- 签到编排、注册表、锁、日期标记、触发路径、已知不一致：[references/sign-in.md](references/sign-in.md)
- 日常便笺链路（角色发现、请求签名、缓存与状态语义）：[references/community-activity.md](references/community-activity.md)
- 通知与任务报告：[references/community-notification.md](references/community-notification.md)
- 代码归属、命名与导入规范：[references/layout.md](references/layout.md)
- 凭据、日志与错误消息边界：[references/credentials.md](references/credentials.md)
- 提交前审查清单：[references/review-checklist.md](references/review-checklist.md)
- 配置声明、事务与锁：[配置框架参考](../mas-data-model/references/config-framework.md)

## 避免

1. 不要为社区引入通用「平台配置引擎」或字段元数据表：五个平台的差异在请求协议，不在字段形状。
2. 不要新增第二份平台清单、凭据字段清单或通知平台顺序。前端五款游戏清单只有一份 `frontend/src/views/gamesign/communityGames.ts`，各处映射用 `Record<CommunityGame, …>` 绑定它。
3. 不要在编排层按平台名写 `if`；平台差异体现在 provider 字段上。
4. 不要把 `check_community_system_time()` 变成阻断条件，也不要让它占用签到锁。
5. 不要把凭据、密码、上游响应正文（HTML/JSON 全文）或异常栈写进日志与 API 错误消息。
