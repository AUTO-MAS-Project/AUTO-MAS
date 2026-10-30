# 游戏社区代码归属与命名

社区的**全部**实现收束在 `app/tools/common/`。这条规范取代了历史上散落在 `app/core`、`app/services`、`app/utils` 的社区模块，新增代码不得再分散回去。

## 目录归属

```text
app/tools/common/
├── community.py                      # facade：签到与便笺的统一出口
├── community_accounts.py             # 账号组命名、账号组标识比对（纯逻辑，不联网）
├── community_activity.py             # 便笺消费层：账号组 → 快照、缓存、失败兜底
├── community_activity_parser.py      # 上游响应 → 快照
├── community_activity_provider.py    # 认证注入、角色发现、设备指纹与节流
├── community_activity_roles.py       # 角色发现响应归一化
├── community_activity_transport.py   # 请求规格构建与并发采集
├── community_contract.py             # 结果与状态契约（唯一成功判据所在处）
├── community_credentials.py          # 凭据外形解析与本地校验分派
├── community_http.py                 # create_community_client：代理、DoH 回退、超时
├── community_plugins.py              # 外部社区插件能力清单（纯静态）
├── community_scheduler.py            # 触发来源判定与便笺查询锁
└── sign/
    ├── community_sign.py             # 签到编排、两把签到锁、账号遍历、凭据回写
    ├── community_sign_provider.py    # 平台注册表、runner、结果归一与格式化
    └── community_sign_result.py      # 结果构建与按账号合并
```

留在 `app/tools/` 顶层的是**单平台适配器**：`skland.py`、`miyoushe.py`、`miyoushe_qr.py`、`kuro.py`、`taygedo.py`、`cloud_genshin.py`。它们只负责某个社区自己的登录、角色发现、签到请求与风控退避，不含跨平台策略。

## 归属判据

| 要加的东西 | 放哪 | 理由 |
| --- | --- | --- |
| 签到专属流程、锁、平台注册表、签到结果 | `app/tools/common/sign/` | 只有签到链路使用 |
| 便笺链路任一环节 | `app/tools/common/` | 便笺专属或与签到共享 |
| 结果/状态契约、凭据解析、HTTP 客户端、账号组辅助、调度锁 | `app/tools/common/` | 两件事都依赖 |
| 某平台协议实现 | `app/tools/<platform>.py` | 单平台知识 |
| 触发时机、结果落盘、配置写入 | `app/core/` | 生命周期与配置归属 |
| 请求解析与响应整形 | `app/api/` | 传输层 |
| 通知编排与渲染 | `app/core/community_notification.py`、`app/services/community_notification.py` | 既有例外，dev 维护，不要搬进社区目录 |

判断口诀：**只有签到用 → `sign/`；社区内共用 → `common/` 根；单平台 → `app/tools/` 顶层；时机与整形 → `core`/`api`。**

## 导入规范

1. 新增导入一律写绝对路径 `from app.tools.common.community_contract import ...`，不要用相对导入跨子包（`sign/` 到 `common/` 根用 `..`）。
2. `app/tools/__init__.py` 只保留极少导出；其余按模块导入。
3. 多数调用点使用**函数内延迟导入**（`app/core/config.py`、`app/core/timer.py`、`app/api/tools.py` 都有先例），因为 `app/tools/common/sign/community_sign.py` 需要 `Config`，而 `Config` 初始化时又要读账号组辅助函数——把任一方向提到模块顶层就会形成启动期循环依赖。
4. 被移动或重命名模块时，同步检查：`app/`、`tests/`、`.agents/skills/mas-game-community/references/` 与本文件中的路径，以及模块 docstring 里提到的位置。
5. 移动模块后跑 `ruff check --fix`（isort 会因新路径重排）与 `python -m compileall -q app tests`。

## 命名

- 模块名用 `community_<领域>.py`；`sign/` 内的文件同样以 `community_sign` 开头，保留全仓前缀一致。
- facade `community.py` 只做再导出，不写业务逻辑。
- 平台适配器用平台名（`skland`、`miyoushe`、`kuro`、`taygedo`、`cloud_genshin`），与 `_COMMUNITY_SIGN_PROVIDERS` 的 `log_name` 对应。

## 迁移旧路径时的替换表

| 旧路径 | 新路径 |
| --- | --- |
| `app/core/community_sign.py` | `app/tools/common/sign/community_sign.py` |
| `app/core/community_scheduler.py` | `app/tools/common/community_scheduler.py` |
| `app/core/community_activity.py` | `app/tools/common/community_activity.py` |
| `app/services/community_http.py` | `app/tools/common/community_http.py` |
| `app/tools/community_sign_provider.py` | `app/tools/common/sign/community_sign_provider.py` |
| `app/tools/game_sign_result.py` | `app/tools/common/sign/community_sign_result.py` |
| `app/tools/community_contract.py` / `community_credentials.py` / `community_plugins.py` | `app/tools/common/` 同名文件 |
| `app/utils/community.py` | `app/tools/common/community_accounts.py` |
