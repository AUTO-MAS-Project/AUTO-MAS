# 游戏社区提交前审查清单

## 代码归属

- [ ] 协议与内部契约位于 `app/tools/common/community/`，宿主配置、锁与调度由 `core.Community` 持有，通知统一使用 `core.Notify`
- [ ] 单平台协议位于 `app/tools/common/community/providers/`，未泄漏进核心编排与 API
- [ ] 配置编排与进程级状态归 core，平台协议和工具内部契约留在本功能，utils 不承载社区业务策略
- [ ] 跨子包导入用绝对路径 `app.tools.common.*`；延迟导入的既有写法未被改成包顶层导出
- [ ] 移动/重命名后已同步 `app/`、`tests/`、`.agents/skills/mas-game-community/references/` 里的路径，并跑过 `ruff check --fix` 与 `python -m compileall -q app tests`

## 平台接入

- [ ] 新平台只改了适配模块 + 校验器一项 + 注册表一项，未在编排层加平台分支
- [ ] 凭据字段已加密，配置描述以 `GameSignAccount - ` 开头
- [ ] provider runner 返回 `_CommunityProviderRun(results, platforms, credential_updates)`，未直接写配置
- [ ] 新平台已加入 `_PLATFORM_ORDER`

## 凭据与日志

- [ ] 一次性登录密码用 `SecretStr`，异常分支未记录堆栈或上游响应
- [ ] 登录成功后校验了凭据完整性才落盘
- [ ] 读凭据走 `read_community_token()`，兼容缺字段的旧账号
- [ ] 凭据的即时写穿与收尾回写都先重读存量，不会覆盖用户刚登录保存的新凭据
- [ ] 日志与 API 错误消息里没有凭据值、Cookie、上游响应正文或异常栈

## 并发与语义

- [ ] 新增触发入口显式处理 `CommunitySignInProgressError`（409 或跳过），未静默等待锁
- [ ] 通知在流程锁**外**发送，后台通知任务持有强引用
- [ ] 成功判据只走 `is_community_sign_completed()`，没有新增手写状态元组
- [ ] 账号级与全局 `LastSignDate` 语义未混用；跨 0 点重取日期的行为保留
- [ ] 遍历账号组用 `list(keys())` 取快照再 `get()`，签到期间删除账号组不会中断整轮签到
- [ ] `_notification_only` 结果未进前端列表与通知
- [ ] 可预期失败走 `warning`，未因新异常类型扩大白名单

## 前端与契约

- [ ] 未手改 `frontend/src/api/**`；配置/schema 变更后已重新生成客户端
- [ ] 游戏清单仍只有 `frontend/src/views/gamesign/communityGames.ts` 一份，各处映射用 `Record<CommunityGame, …>` 绑定
- [ ] 新增 `ActivityState` 值已同步 `communityActivityPresentation.ts` 文案映射
- [ ] 未新增社区 e2e 用例；开发期验证脚本属一次性产物，不提交
