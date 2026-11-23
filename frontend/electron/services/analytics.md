# 匿名使用统计

Electron 主进程按 Aptabase 单事件协议向 `https://telemetry.auto-mas.top/api/v0/event` 上报匿名统计（App Key 为公开的客户端写入标识，不含管理或查询凭据）。Vue 渲染层通过受限 preload / IPC 交由主进程校验并发送，不直接初始化 Web SDK。

完整 84 项业务场景与复用台账见 [场景覆盖台账](./analyticsCoverage.md)；扩展或修改业务流程时遵循 [mas-telemetry Skill](../../../.agents/skills/mas-telemetry/SKILL.md)。所有固定字段枚举统一定义在 [analyticsFeaturePolicy.ts](./analyticsFeaturePolicy.ts)。

## 环境隔离、开关与传输策略

- **环境隔离**：由 Electron 打包状态和 `AUTO_MAS_BACKEND_REPO` 决定，并在页面执行前经 preload 传入 Vue。源码运行、纯浏览器、CI、单元测试、E2E、以及安装版启用开发源码后端时一律禁报；后端生产行为仅由 `AUTO_MAS_ENV=production` 控制。
- **用户开关**：复用 `Function.IfEnableTelemetry`（配置缺失或未确认时停采）。运行中关闭立即中止可取消请求并清空随机会话 ID；操作开始前获取的代次在关闭后失效，不补发关闭期间的数据。
- **隐私红线**：主进程仅接受白名单事件与有限枚举字段，拒绝自由文本、账号、凭据、路径、配置内容、日志或网络地址。事件携带 UTC 时间与内存随机会话 ID（空闲 1 小时或满 24 小时轮换），不使用设备或安装标识。
- **传输与限频**：固定 HTTPS 目的地、禁重定向、无 Cookie、5 秒超时；不排队、不重试、不落盘、不阻塞应用退出。主进程最多 4 并发，每分钟上限 120 条，单事件族每分钟最多 60 次。`config_write_finished` 的成功结果按 1/10 独立随机抽样（失败全量上报）。
- **分桶口径**：耗时桶为 `<1s`、`1-5s`、`5-30s`、`30-120s`、`>120s`；数量桶为 `0`、`1`、`2-5`、`6-20`、`20+`。
- **服务端留存**：自建 Aptabase（ClickHouse `default.events`）默认保留正式事件 1825 天（约 5 年），到期后后台清理。

## 事件目录

### 1. 启动、初始化、恢复与桌面生命周期

| 事件 | 含义 | 主要字段（未注明的均含 `outcome` / 耗时桶） |
| --- | --- | --- |
| `app_started` | 主进程进入 ready（每进程最多一次） | `launch_kind`（含 `scheduled_wakeup`）、`runtime_mode`、`release_channel` |
| `renderer_ready` | 主窗口完成 Vue 挂载（每进程最多一次） | `duration_bucket`、`visibility` |
| `backend_start_finished` | 串行后端启动作业的真实结果 | `runtime_mode` |
| `backend_restart_finished` | 主动更新或故障重启结果 | `reason_kind`（`update` / `recovery` 等） |
| `runtime_alignment_finished` | Runtime 升级、校验、回退结果 | `operation`、`release_channel` |
| `backend_update_finished` | 后端热更新结果与停止阶段 | `trigger_kind`、`phase` |
| `initialization_decided` | 直接进入、完整初始化或强制更新决策 | `decision`、`runtime_mode` |
| `initialization_stage_finished_v2` | Runtime 单次命令返回结果 | `stage`、`runtime_mode`、`known_code`、`failed_stage` |
| `initialization_recovery_selected` | 初始化失败后的用户恢复动作 | `action`、`stage`、`mirror_kind` |
| `initialization_finished_v2` | 初始化尝试的整体结局（含词表就绪） | `flow_kind`、`runtime_mode`、`failed_stage` |
| `renderer_recovery_decided` | 渲染进程异常退出后的重载决策 | `reason_kind`、`recovery_action`、`count_bucket` |
| `renderer_recovery_finished` | 每次实际重载的观察结果 | `reason_kind`、`result_kind`、`count_bucket` |
| `renderer_responsiveness_changed` | 页面卡死后是否恢复响应 | `state` |
| `connection_incident_finished` | 非计划断线的一次恢复事故 | `recovery_kind`、`reason_kind` |
| `system_resume_recovery_finished` | 系统休眠唤醒后的恢复结果 | `recovery_kind` |
| `app_close_finished` | 正常退出收尾、取消或强制退出（不含隐藏至托盘） | `close_kind` |
| `tray_action_requested` | 托盘菜单动作使用情况 | `action_kind` |
| `stop_all_requested` | 全局紧急停止请求 | `source` |
| `virtual_display_action_finished` | 虚拟显示器检查、拆除与用户选择 | `action` |
| `virtual_display_prompt_answered` | 显示器恢复提示的用户选择 | `choice` |
| `desktop_session_connection_finished` | 桌面分身连接结果 | `reason_kind` |
| `desktop_session_environment_repair_finished` | 桌面分身环境修复与复查结果 | `outcome` / 耗时桶 |

### 2. 脚本、任务、队列、计划与插件

| 事件 | 含义 | 主要字段（未注明的均含 `outcome` / 耗时桶） |
| --- | --- | --- |
| `screen_view` | 白名单业务页面导航（相邻去重） | `screen`、`script_type`、`entry_source` |
| `script_create_finished` | 新建托管、模板导入、复制与项目复用 | `create_kind`、`script_type` |
| `script_manage_finished` | 托管复制、删除与重排 | `action`、`script_type`、`count_bucket` |
| `user_create_finished` | 自动或手动建号结果 | `script_type` |
| `user_manage_finished` | 账号删除、启停与批量管理 | `action`、`script_type`、`count_bucket` |
| `config_write_finished` | 脚本、用户与设置的共享写入（成功 1/10 采样） | `owner_kind`、`section_kind`、`script_type`、`sample_rate` |
| `config_mode_changed` | 托管、原生、查看模式切换 | `script_type`、`mode` |
| `native_config_action_finished` | 原生配置打开、查看、保存/关闭与丢弃 | `script_type`、`operation` |
| `config_restore_finished` | MAS / 原生备份恢复与强制确认 | `script_type`、`target_kind`、`forced` |
| `task_start_result` | 任务启动请求受理结果 | `source`、`mode`、`target_kind` |
| `task_observed_finished` | 常驻订阅观察到的整任务完成结果 | `mode`、`script_type` |
| `task_stop_result` | 单任务停止请求的受理结果 | `source`、`mode`、`request_outcome` |
| `task_resume_requested` | 指定脚本起点或用户范围续跑请求 | `source`、`resume_kind`、`scope_kind`、`request_outcome` |
| `script_run_started` | 自动代理进入一次脚本执行 | `mode`、`script_type` |
| `script_run_finished` | 本窗口观察到的单次脚本执行结局 | `mode`、`script_type`、`partial_failure` |
| `queue_manage_finished` | 队列与队列项创建、删除、配置与排序 | `action`、`queue_kind`、`count_bucket` |
| `queue_schedule_changed` | 启动、定时、循环及星期调度配置 | `schedule_kind`、`action` |
| `queue_time_set_changed` | 时间集合管理 | `action`、`count_bucket` |
| `plan_manage_finished` | 计划创建、重命名、删除与排序 | `action`、`plan_type`、`count_bucket` |
| `plan_edit_finished` | 简单/复杂视图与轮换计划编辑 | `plan_type`、`view_kind`、`operation_kind` |
| `adapter_setup_finished` | 专项配置引导与独有操作（如保存、刷新、预览） | `script_type`、`operation_kind`、`engine_kind` |
| `plugin_action_finished` | 插件安装、启停、配置保存与市场手动刷新 | `action`、`outcome` / 耗时桶 |
| `mcp_retry_requested` | MCP 手动重新加载请求受理结果 | `outcome` / 耗时桶 |

### 3. 模拟器、游戏、社区、通知、更新、设置与工具

| 事件 | 含义 | 主要字段（未注明的均含 `outcome` / 耗时桶） |
| --- | --- | --- |
| `emulator_discovery_finished` | 模拟器搜索与导入 | `emulator_family`、`action`、`count_bucket` |
| `emulator_operation_result` | 模拟器启停/显示请求受理结果 | `emulator_family`、`operation` |
| `emulator_operation_observed_finished` | 前端观察到的模拟器操作结局 | `emulator_family`、`operation` |
| `emulator_instance_manage_finished` | 实例增删与批量设置 | `emulator_family`、`action`、`scope`、`count_bucket` |
| `emulator_guard_changed` | 稳定模式与配置守卫变更 | `guard_kind`、`action` |
| `game_target_changed` | 游戏目标管理、发现与批量操作 | `adapter`、`action` |
| `game_operation_result` | 插件设备命令受理结果 | `adapter`、`operation` |
| `game_operation_observed_finished` | 按唯一操作 ID 确认的设备操作终态 | `adapter`、`operation` |
| `avd_root_added` | 自定义 AVD 安装导入 | `reason_kind` |
| `game_sign_requested` | 手动签到触发与被占用拒绝 | `trigger_kind` |
| `community_account_manage_finished` | 社区签到账号增删与启停 | `action` |
| `community_login_finished` | 社区扫码登录终态（生成/扫码/保存） | `provider`、`stage` |
| `community_activity_requested` | 社区活动工具调用 | `operation_kind` |
| `notification_test_finished` | 总体通知测试响应 | `test_kind`、`request_outcome` |
| `notification_channel_changed` | 内置通知渠道启停保存 | `channel_kind`、`action` |
| `notification_binding_finished` | QQ 扫码绑定、手动配置与解绑 | `channel_kind`、`action` |
| `webhook_test_finished` | 独立 Webhook 测试结果 | `scope_kind` |
| `update_check_finished` | 手动检查与首次自动检查结果 | `trigger_kind`、`update_available` |
| `update_download_started` | 本次本地下载首次获得进度或响应 | `source_kind`、`release_channel` |
| `update_download_finished` | 本地下载最终结局（完成/取消/失败） | `source` |
| `update_source_changed` | 用户确认换源的结果 | `from_kind`、`to_kind`、`trigger_kind` |
| `update_install_requested` | 立即安装或稍后安装选择 | `choice`、`request_outcome` |
| `settings_change_finished` | 主要功能开关与设置保存 | `setting_key`、`value_kind`、`setting_kind` |
| `appearance_preference_changed` | 主题、语言、低性能模式与自定义光标 | `preference_kind`、`preset_value` |
| `appearance_package_finished` | 本地主题/桌宠导入、启用与删除 | `package_kind`、`action` |
| `appearance_store_install_finished` | 主题商店安装结果 | `category_kind` |
| `appearance_share_finished` | 外观上传与分享 | `category_kind` |
| `mascot_preference_changed` | 桌宠开关与 FPS 档位选择 | `action`、`fps_preset` |
| `home_activity_load_finished` | 首页活动信息加载结果与来源 | `trigger_kind`、`source_kind`、`cache_kind` |
| `home_layout_changed` | 首页布局与快捷任务保存 | `action`、`layout_preset` |
| `taskboard_marking_finished` | 每周任务打卡与版本主线标记保存 | `target_kind`、`action`、`count_bucket` |
| `history_query_finished` | 历史记录检索 | `filter_kind`、`count_bucket` |
| `diagnostic_export_finished` | 问题包与普通日志导出 | `bundle_kind`、`script_type`、`incomplete` |
| `data_backup_export_finished` | MAS 数据备份导出 | `outcome` / 耗时桶 |
| `replay_tool_finished` | 失败录屏连接、手动保存与回放 | `action` |
| `help_link_requested` | 应用内帮助文档入口点击 | `link_kind`、`entry_source` |

## 关键统计口径

- **初始化 v2**：从 `v2` 起将取消独立记为 `cancelled`，Runtime 对齐失败记为 `runtime_binary`；确认主连接可用且业务词表就绪才计为成功。自动恢复最多两轮，不计为用户恢复动作；缺失 Runtime 触发的补装按 `flow_kind=update` 记录。
- **渲染进程恢复**：由主进程 `rendererRecoveryService.ts` 唯一观察，页面加载完成且收到 Vue 挂载就绪 IPC 才记 `success`（30 秒未确认记 `unknown`，退出/关机打断记 `cancelled`）。
- **任务与逐脚本观察**：整任务 `success` 仅表示执行器正常收尾，不代表每个账号成功；逐脚本 `script_run_finished` 另带 `partial_failure`（`yes` / `no` / `unknown`）。恢复快照不补报样本，仅按成对收到的开始/完成事件计数。
- **请求受理 vs 执行完成**：安装启动、停止任务、原生配置保存、MCP 重载等无可靠终态信号的接口只记录请求受理（`accepted` / `rejected` / `unknown`），不伪造执行成功。
- **更新检查与换源**：自动检查每进程最多记一次，不按定时轮询累计；下载中途换源属于同一次下载尝试，不提前结束 `update_download_finished`。
- **启动硬件统计**：桌面启动时启用每秒一次的只读采样器（最长 10 分钟），并在 `initialization_finished_v2` / `initialization_stage_finished_v2` 附加有限硬件档位字段；关闭遥测后仍仅写入本地 `debug/startup-hardware.log` 供日志包排查。

### 启动硬件 ClickHouse 参考查询

```sql
SELECT app_version,
       JSONExtractString(string_props, 'flow_kind') AS flow,
       if(empty(JSONExtractString(string_props, 'install_media')), 'unknown', JSONExtractString(string_props, 'install_media')) AS disk,
       count() AS attempts,
       countIf(JSONExtractString(string_props, 'coverage') != 'sampled') AS missing,
       countIf(JSONExtractString(string_props, 'outcome') = 'failure') AS failures,
       countIf(JSONExtractString(string_props, 'outcome') = 'success') AS successes,
       countIf(JSONExtractString(string_props, 'outcome') = 'cancelled') AS cancelled,
       countIf(JSONExtractString(string_props, 'outcome') = 'skipped') AS skipped,
       countIf(JSONExtractString(string_props, 'outcome') = 'unconfirmed') AS unconfirmed,
       round(100 * failures / nullIf(successes + failures, 0), 2) AS confirmed_failure_percent
FROM events
WHERE app_id = {app:String} AND timestamp >= now() - INTERVAL 30 DAY
  AND event_name = 'initialization_finished_v2'
GROUP BY app_version, flow, disk
ORDER BY attempts DESC
```

整包升级首次启动的自动备份由后端记录 Sentry 计数 `auto_mas.upgrade_backup.attempts`。唯一字段 `outcome` 取 `success` 或 `failure`，归档落盘后才计成功。沿用后端匿名遥测开关。

## 扩展约束

1. 新增事件须同步更新 TypeScript 类型契约与主进程白名单（`analyticsFeaturePolicy.ts`），并明确限频与去重边界。
2. 异步流程在操作开始前获取 context 代次，结束时携带原代次上报，不在结束后重新取新代次补报。
3. 不将请求受理等同于执行成功，不把恢复快照当成新事件，不引入通用 HTTP/日志拦截器。

协议参考：[Aptabase 单事件实现](https://github.com/aptabase/aptabase-electron/blob/main/src/main.ts) · [自建 SDK 指南](https://github.com/aptabase/aptabase/wiki/How-to-build-your-own-SDK)
