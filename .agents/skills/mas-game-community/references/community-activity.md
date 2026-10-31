# 游戏社区日常便笺链路

日常便笺是**只读**的角色活跃度查询：按账号组凭据发现角色，再按角色拉取便笺快照。它不写回凭据、不调用签到入口、不占用签到锁。整条链路位于 `app/tools/common/community/activity/`，消费层是 `app/core/community/activity.py`。

## 入口与开关

| 位置 | 说明 |
| --- | --- |
| `POST /api/tools/community/activity/query` | `app/api/community/accounts.py::query_community_activity`，请求体 `CommunityActivityQueryIn(accountIds?)` |
| `GameSign.ActivityEnabled` | 总开关，关闭时 API 直接返回空列表，消费层也直接返回 `()` |
| `community_activity_flow()` | `app/core/community/scheduling.py` 的串行锁：后到者等锁，等完复用缓存 |
| 前端 | `views/gamesign/CommunityActivityView.vue`、`components/CommunityActivityCard.vue`、`communityActivityPresentation.ts`、`stores/communityActivity.ts` |

查询失败**不**影响签到，签到失败也**不**阻塞便笺；两条链路只共享账号组凭据与 `community_http` 客户端。

## 分层职责

| 模块 | 职责 | 关键符号 |
| --- | --- | --- |
| `activity/roles.py` | 角色发现响应归一化，不联网 | `ACTIVITY_COMMUNITY_DEFINITIONS`、`CommunityActivityRole`、`CommunityActivityRoleDiscovery`、`CommunityActivityCapability`、`normalize_skland_roles`、`normalize_miyoushe_roles` |
| `activity/provider.py` | 认证注入、角色发现请求、米游社设备指纹与节流 | `CommunityActivityProvider.discover_roles()` / `.request()`、`build_community_activity_requester()` |
| `activity/transport.py` | 请求规格构建与并发采集 | `CommunityActivityTarget`、`CommunityActivityRequest`、`build_community_activity_requests()`、`collect_community_activity()`、`CommunityActivityTransportError` |
| `activity/parser.py` | 上游响应 → 快照 | `parse_activity_snapshot()`、`ACTIVITY_GAME_DEFINITIONS`、`ActivityResponseLimitedError`、`ActivityResponseUnavailableError` |
| `app/core/community/activity.py` | 账号组 → 快照、缓存、失败兜底 | `query_configured_community_activity()`、`collect_configured_community_activity()`、`build_configured_community_activity_failures()`、`connect_community_activity_cache()` |

## 已登记的游戏范围

`ACTIVITY_COMMUNITY_DEFINITIONS` 是唯一登记表：

- 森空岛：明日方舟、终末地
- 米游社：原神、星穹铁道、绝区零

`ACTIVITY_GAME_DEFINITIONS`（parser 内）登记每款游戏的解析口径。新增游戏要**同时**补三处：`ACTIVITY_COMMUNITY_DEFINITIONS`（角色发现范围）、`build_community_activity_requests()`（请求规格）、`ACTIVITY_GAME_DEFINITIONS`（解析），缺一处就会出现「查到了但显示空白」或「直接报未登记」。

## 角色发现

- 森空岛走 `SKLAND_BINDING_URL`，用 `normalize_skland_roles()` 处理两种响应：按 `appCode` 分组的 `bindingList`，以及部分版本直接返回的无 `appCode` 绑定列表（只能用两款游戏互斥的字段区分，不能把一条记录同时解释为两个游戏）。
- 米游社走 `ROLES_URL`，`normalize_miyoushe_roles()` 同时兼容扁平列表与按游戏嵌套的 `list`，`game_biz` 映射到中文游戏名（`hk4e_cn`/`hkrpg_cn`/`nap_cn`）。
- 去重键固定为 `(game, role_uid, server)`，保持上游顺序。
- 角色对象**不携带**凭据与设备值；设备字段只在 `to_target()` 阶段按「米游社 + 绝区零」注入。

## 请求规格与签名

`build_community_activity_requests()` 只产出**脱敏规格**（URL、方法、查询串、头、签名 profile），认证值由 provider 在执行时注入，规格本身不含 Cookie / Token / Authorization / 请求体。

| 平台 + 游戏 | 规格顺序 | 签名 profile |
| --- | --- | --- |
| 森空岛 · 明日方舟 | `player/info` | `skland_widget` |
| 森空岛 · 终末地 | `endfield/card/detail` | `skland_endfield_web` |
| 米游社 · 原神 | `dailyNote` → `widget/v2` | `miyoushe_params` → `miyoushe_ios` |
| 米游社 · 星穹铁道 | `hkrpg/aapi/widget` → `hkrpg/api/note` | `miyoushe_data` → `miyoushe_params` |
| 米游社 · 绝区零 | `zzz/note` → `zzz/widget` | `miyoushe_params` |

规格上的 `requires_device_id` / `requires_device_fingerprint` 决定是否带设备头：米游社设备头缺失会被上游判成通用失败，因此新增请求时必须显式声明。

## 执行、回退与并发

- `collect_community_activity(targets, requester, max_concurrency=4)` 用本地 semaphore 并发，**不复用签到锁**；单款游戏失败不会取消其他游戏。
- 每款游戏按规格顺序尝试，第一个 `success` 立即返回；全部失败时按 `_activity_failure_priority()` 保留**最具体**的原因（`limited` > `unavailable` > `failed` > `empty`），避免回退把「风控」降级成「泛失败」。
- 单个请求受 `request.timeout` 约束（provider 侧默认 12s）。
- 米游社请求之间由 `_wait_miyoushe_request()` 保持 `miyoushe_request_interval`（默认 1.2s）的最小间隔；`_miyoushe_rate_lock` 保证同一 provider 实例内串行打点。
- 米游社设备指纹经 `getFp` / `deviceLogin` / `saveDevice` 换取并缓存在 provider 实例内，绝不写回配置。

## 状态语义

`ActivityState`：`success` / `empty` / `limited` / `unavailable` / `failed`。

- `limited` 专指命中风控码（`1034`、`5003`、`10035`、`10041`），由 `ActivityResponseLimitedError` 与 provider 的 `_MIYOUSHE_RISK_CODES` 两处判定。
- `unavailable` 表示响应形状不可识别（如「非 JSON」「缺少绑定列表」），由 `ActivityResponseUnavailableError` 判定。
- `empty` 表示「账号没有绑定该游戏角色」，是正常态，不是错误。
- 前端文案映射在 `communityActivityPresentation.ts`；新增状态必须同步前端，否则会落到兜底文案。

角色发现阶段若拿到 `activity_capability.status == "limited"`，消费层**不再发便笺请求**，直接按已有角色生成 `limited` 快照；没有角色则生成 `empty` 快照。这条分支决定「风控时不要继续打接口」，改动时必须保留。

## 缓存与失效

- 缓存键 `(id(Config.ToolsConfig), account_uid)`，入口按账号维度复用。
- TTL：全部 `success`/`empty` 记 300s（`_ACTIVITY_CACHE_SECONDS`），包含任何失败记 30s（`_ACTIVITY_RETRY_SECONDS`），避免失败结果被长时间缓存。
- `connect_community_activity_cache()` 订阅 `GameSignAccount` 分组、`GameSign_Accounts` 集合、`GameSign.ActivityEnabled`、`Update.ProxyAddress`，命中即递增 `_activity_cache_revision` 并清空缓存。
- 等待上游期间 revision 变化时，旧响应**不得**写入新配置的缓存，循环重查（`while True` + revision 比较）。
- 取消/异常兜底：`build_configured_community_activity_failures()` 只按已配置凭据造分游戏失败快照、不发请求，供 API 在整体异常且无快照时回退。

## 安全边界

1. 便笺链路只读：不得写回凭据、不得触发签到、不得改动 `LastSignDate`。
2. 快照里不允许出现凭据、Cookie、设备值；允许出现的只有 `account`、`account_uid`、`game`、`platform`、`status`、进度、任务/资源条目、`role_name`、`role_uid`、`server`、`source`、`updated_at`。
3. 上游异常原文可能带 Cookie，日志只允许 `format_exception_reason(..., include_message=False)` 加上「调用位置」这类定位信息（见 `query_configured_community_activity` 的 `traceback.extract_tb` 用法），不要打印响应体。
4. 第三方接口知识的致谢声明保留在模块文件头。

## 审查清单

- [ ] 新游戏同时补齐角色发现范围、请求规格、解析口径三处
- [ ] 请求规格里没有凭据；认证只在 provider 内注入
- [ ] 规格显式声明 `requires_device_id` / `requires_device_fingerprint`
- [ ] 回退顺序没有把 `limited` 降级成 `failed`；成功即返回
- [ ] 风控时不继续发请求，直接产出 `limited` 快照
- [ ] 缓存 TTL 区分成功与失败，revision 变化时丢弃旧响应
- [ ] 新增 `ActivityState` 值已同步前端文案映射
- [ ] 快照与日志里没有凭据、设备值或上游原始响应
- [ ] 便笺链路没有获取签到锁、没有调用签到入口
