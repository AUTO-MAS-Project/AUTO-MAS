---
name: mas-game-community
description: >-
  Add, refactor, or review AUTO-MAS game community sign-in and daily-activity
  flows: core.Community orchestration, locks and caching; provider protocols,
  credentials and result contracts under app/tools/common/community/;
  core.Notify community notifications; account-group config and gamesign UI.
---

# 游戏社区（签到 + 日常便笺）

游戏社区由两件事共用一套凭据与账号组：**签到**（凭据驱动的批量外部请求）与**日常便笺**（按角色拉取活跃度）。两者都不是脚本适配，风险集中在三处：**用户凭据**、**上游风控**、**重复触发**。

## 代码归属（硬规则）

按 [后端源码组织规范](../mas-module-boundary/SKILL.md) 分配职责：

- `app/core/community/`：全局 `Community` 实例的配置读取、签到编排、锁、活动缓存与调度策略。
- `app/tools/common/community/`：本功能的契约、凭据、账号辅助、平台协议与活动解析；平台适配在 `providers/`，活动实现细分在 `activity/`。
- `app/core/notify/`：社区通知、任务报告、渠道与后台投递。业务通过 `from app.core import Notify` 使用。
- `app/api/community/`：账号、签到和扫码登录薄入口，既有 `/api/tools/*` 路径保持不变。
- 配置模型仍在 `app/models/config/tools.py`，工具内部契约不得迁入共享 models。

调用方通过 `from app.core import Community` 使用核心实例；工具公共模块由 `app.tools` 入口提供，内部模块使用实际功能包路径。导入与缓存机制不构成绕过依赖边界的理由。当前源码和历史排布不自动成为组织规范例外。
详见 [references/layout.md](references/layout.md)。

## 三条不能违反的语义

1. **平台注册表是唯一入口**：`_COMMUNITY_SIGN_PROVIDERS` 派生凭据字段表与「该平台是否已配置」判据；不要另写平台清单或凭据字段清单。见 [references/sign-in.md](references/sign-in.md)。
2. **成功判据只有一处**：`contracts.is_community_sign_completed()`，即 `status in COMMUNITY_SIGN_SUCCESS_STATUSES or _completed`。编排与手动端点复用它；通知结果模型只投影既有结果，不反向决定签到完成或落盘。
3. **锁不合并、通知在锁外**：`community_sign_flow`、`_community_sign_lock`、`skland_sign_lock`、`community_activity_flow` 语义各不相同；签到锁**快速失败**（API 映射 409），便笺锁串行等待。

## 凭据与安全

社区是本仓少数直接持有**用户账号密码**的路径：凭据加密落盘、一次性登录用 `SecretStr`、异常分支不回显上游正文与堆栈、凭据刷新只经 `credential_updates` / `on_credential_update` 回写。细则见 [references/credentials.md](references/credentials.md)。

## 最小验证

- 后端：`uv run --no-sync python -m pytest tests/tools tests/core/test_components.py tests/core/test_notify.py tests/api -q`
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
