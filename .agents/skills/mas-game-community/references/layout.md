# 游戏社区代码归属与入口

总体规则以 [mas-module-boundary](../../mas-module-boundary/SKILL.md) 为准。目录按功能聚合，宿主核心与独立协议实现分开。

- `app/core/community/__init__.py` 创建全局 Community；`sign.py` 管理账号编排、签到锁、日期与凭据回写，`activity.py` 管理活动查询缓存与失败快照，`scheduling.py` 管理触发策略。
- `app/tools/common/community/` 保存本功能内部契约 `contracts.py`、凭据校验 `credentials.py`、账号辅助 `accounts.py`、HTTP 客户端 `http.py`、插件能力 `plugins.py`、签到平台注册表 `sign.py` 和结果辅助 `results.py`。
- `providers/` 收纳单平台协议；`activity/` 收纳角色发现、请求构建、采集和解析，避免功能文件重新平铺到 common 根。
- `app/core/notify/` 负责通知，社区文案在 `community_content.py`，投递与等待在 `community.py`；不在 tools 中反向调用宿主通知。
- `app/api/community/` 只负责账号、签到及扫码登录的请求响应，调用核心入口；配置字段仍由 `app/models/config/tools.py` 声明。

业务使用 `from app.core import Community, Notify`；平台差异能力通过 utils/services 的统一入口取得，静态提示引用契约，不直接绑定开发机实现。专用类型留在工具内部，工具所需配置由调用方提供。

源码、动态导入、补丁和 Skills 的引用须同步迁移；不恢复旧扁平模块、独立全局锁或兼容转发。工具函数的临时状态不强制改成全局单例。
