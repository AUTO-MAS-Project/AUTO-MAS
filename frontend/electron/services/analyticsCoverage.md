# 匿名统计场景覆盖台账

本台账对应 [Issue #1605 的 84 项业务场景](https://github.com/AUTO-MAS-Project/AUTO-MAS/issues/1605#issuecomment-6354559213) 以及后续扩展场景，记录各场景对应的事件族与关键复用边界。事件定义、开关与限频策略见 [analytics.md](./analytics.md)。

> 84 项是业务场景而非 84 个独立事件名：多个场景会按固定分类复用同一事件族（如 `config_write_finished`、`adapter_setup_finished`）。

## 84 项基线场景（T001–T084）

| 编号 | 事件族与覆盖场景 | 覆盖说明 |
| --- | --- | --- |
| T001 | `app_started`：版本与启动方式分布 | 已接入（区分手动 / 开机自启 / 定时唤醒） |
| T002 | `initialization_decided`：初始化或直接进入决策 | 已接入 |
| T003 | `initialization_finished_v2`：初始化整体结局 | 已接入（含词表就绪与硬件档位摘要） |
| T004 | `initialization_stage_finished_v2`：Python、依赖、仓库等阶段结果 | 已接入（含硬件摘要） |
| T005 | `initialization_recovery_selected`：重试、重建、恢复与跳过 | 已接入 |
| T006 | `backend_start_finished`：后端启动成功率与耗时 | 已接入（含启动期插件兼容升级） |
| T007 | `backend_restart_finished`：主动更新与故障重启 | 已接入 |
| T008 | `runtime_alignment_finished`：Runtime 升级、校验与回退 | 已接入 |
| T009 | `backend_update_finished`：后端热更新完成或失败阶段 | 已接入（含手动同版本预检拒绝） |
| T010 | `renderer_recovery_decided` / `renderer_recovery_finished`：渲染进程恢复 | 已接入（主进程确认页面加载 + Vue 挂载） |
| T011 | `renderer_responsiveness_changed`：卡死后是否恢复响应 | 已接入 |
| T012 | `app_close_finished`：正常退出、取消与强制退出 | 已接入（不含隐藏至托盘） |
| T013 | `tray_action_requested`：托盘入口使用情况 | 已接入 |
| T014 | `stop_all_requested`：全局紧急停止入口 | 已接入 |
| T015 | `virtual_display_action_finished`：虚拟屏手动检查与拆除 | 已接入（自动探测不计数） |
| T016 | `virtual_display_prompt_answered`：显示器恢复提示选择 | 已接入（经限定窗口专用桥） |
| T017 | `renderer_ready`：首屏挂载耗时与可见性 | 已接入 |
| T018 | `screen_view`：白名单业务页面访问 | 已接入（相邻去重） |
| T019 | `connection_incident_finished`：断线后自动恢复结果 | 已接入 |
| T020 | `system_resume_recovery_finished`：系统唤醒后恢复结果 | 已接入 |
| T021 | `script_create_finished`：新增托管、模板导入与项目复用 | 已接入 |
| T022 | `script_manage_finished`：托管复制、删除与重排 | 已接入 |
| T023 | `user_create_finished`：自动/手动建号结果 | 已接入 |
| T024 | `user_manage_finished`：账号删除、启停与批量管理 | 已接入 |
| T025 | `config_write_finished`：配置保存失败率 | 已接入（成功 1/10 随机采样） |
| T026 | 账号配置草稿与联动保存 | 复用 `config_write_finished`（`owner_kind=user`） |
| T027 | `config_mode_changed`：托管、原生、查看模式切换 | 已接入 |
| T028 | `native_config_action_finished`：原生配置打开、查看与保存 | 已接入 |
| T029 | `config_restore_finished`：配置恢复完成率 | 已接入 |
| T030 | `task_start_result`：任务启动入口与受理结果 | 已接入（含桌面分身来源） |
| T031 | `task_observed_finished`：前端观察到的整任务结局 | 已接入（配合 `script_run_started/finished`） |
| T032 | `task_stop_result`：中止请求受理结果 | 已接入 |
| T033 | `task_resume_requested`：指定起点或范围续跑 | 已接入 |
| T034 | `queue_manage_finished`：队列增删改与排序 | 已接入 |
| T035 | `queue_schedule_changed`：启动、定时、循环与星期配置 | 已接入 |
| T036 | `queue_time_set_changed`：时间集合管理 | 已接入 |
| T037 | `plan_manage_finished`：各类计划创建、重命名、删除与排序 | 已接入（含 `UniversalPlanConfig`）；BAAH 使用原生轮换，不再提供 MAS 计划入口 |
| T038 | `plan_edit_finished`：简单/复杂视图与轮换计划编辑 | 已接入（整批汇总记录） |
| T039 | `update_check_finished`：手动/首次自动检查更新 | 已接入 |
| T040 | `update_download_started`：用户选择更新后的下载进入率 | 已接入 |
| T041 | `update_download_finished`：本体下载成功、失败与取消 | 已接入（换源不中断整次观察） |
| T042 | `update_source_changed`：换源结果 | 已接入 |
| T043 | `update_install_requested`：立即或稍后安装选择 | 已接入（仅记录请求受理） |
| T044 | `emulator_discovery_finished`：模拟器搜索与导入 | 已接入 |
| T045 | `emulator_operation_result`：模拟器启停/显示受理 | 已接入 |
| T046 | `emulator_operation_observed_finished`：模拟器操作终态 | 已接入（单窗口归因，128 键预算） |
| T047 | `emulator_instance_manage_finished`：实例增删与设置 | 已接入（含 AVD 分辨率档位） |
| T048 | `emulator_guard_changed`：稳定模式与配置守卫 | 已接入 |
| T049 | `avd_root_added`：自定义 AVD 根目录导入 | 已接入 |
| T050 | `game_sign_requested`：手动签到与被占用拒绝 | 已接入 |
| T051 | `community_account_manage_finished`：社区账号增删与启停 | 已接入 |
| T052 | `community_login_finished`：社区扫码登录终态 | 已接入 |
| T053 | `community_activity_requested`：社区活动工具调用 | 已接入 |
| T054 | `notification_test_finished`：通知总体测试 | 已接入 |
| T055 | `notification_channel_changed`：内置通知渠道启停 | 已接入 |
| T056 | `notification_binding_finished`：QQ 扫码、手动绑定与解绑 | 已接入 |
| T057 | `webhook_test_finished`：独立 Webhook 测试 | 已接入 |
| T058 | `settings_change_finished`：主要设置项修改与采用 | 已接入（含静默启动、关闭确认、目录显隐、更新接管开关等） |
| T059 | `appearance_preference_changed`：主题、语言、低性能与光标 | 已接入 |
| T060 | `appearance_package_finished`：本地外观包导入、启用与删除 | 已接入 |
| T061 | `appearance_store_install_finished`：主题商店安装 | 已接入（浏览详情与切换版本不计数） |
| T062 | `appearance_share_finished`：外观上传与分享 | 已接入 |
| T063 | `mascot_preference_changed`：桌宠采用率与 FPS 档位 | 已接入 |
| T064 | `home_activity_load_finished`：首页活动信息加载与来源 | 已接入（busy 跳过不重复计） |
| T065 | `home_layout_changed`：首页布局与快捷任务保存 | 已接入 |
| T066 | `history_query_finished`：历史记录检索 | 已接入 |
| T067 | `diagnostic_export_finished`：问题包与普通日志导出 | 已接入 |
| T068 | `data_backup_export_finished`：MAS 数据备份导出 | 已接入 |
| 整包升级备份 | 后端指标 `auto_mas.upgrade_backup.attempts`，仅记录创建尝试的成功或失败 | 由迁移前备份流程记录，复用 ZIP 和清理旧档不计 |
| 更新备份目录迁移 | 后端指标 `auto_mas.upgrade_backup.directory_moves`，仅记录迁移结果 | 由确认后的目录迁移入口记录，选择路径或取消不计 |
| T069 | `replay_tool_finished`：失败录屏连接、保存与回放 | 已接入 |
| T070 | `help_link_requested`：应用内帮助文档入口 | 已接入 |
| T071–T084 | `adapter_setup_finished`：14 类专项配置引导与独有操作 | 已接入：MAA、SRC、MaaEnd、HSR、General、BAAH（含推荐配置生成）、MaaFW、M9A、MSS、BetterGI、OK-WW、OK-NTE、ZZZ-OD、Whimbox 各自实际存在的独有引导与保存入口，其余通用读写复用 `config_write_finished` / 任务观察 |

## 扩展场景（T084 之外）

- **桌面分身**：`DesktopSessionService` 记录 `desktop_session_connection_finished` 与 `desktop_session_environment_repair_finished`；实际派发沿用 `task_start_result`（`source=desktop_session`）。
- **游戏管理**：`useGamesApi` 记录 `game_target_changed`；`useGameOperations` 分开记录 `game_operation_result` 与 `game_operation_observed_finished`；页面访问归入 `screen_view/games`。
- **插件管理**：`usePluginApi` 唯一记录 `plugin_action_finished`（覆盖安装、启停、配置保存与市场手动刷新）；需重启换版依赖时复用 `backend_restart_finished`。
- **MCP 工具页**：页面访问归入 `screen_view/tools`；手动重新加载由 `useMcpApi` 记录 `mcp_retry_requested`。
- **任务台**：`taskboard_marking_finished` 记录每周任务选择/打卡与版本主线标记保存（区分 `weekly_task` / `version` 与 `select` / `mark` / `unmark`）。
- **附属插件（SignFlow）**：`signflow_requested` 唯二记录抽卡记录的查询与读取、社区凭据的自动刷新（区分 `gacha_query` / `gacha_fetch` / `token_refresh`）；插件未启用记为 `unsupported`、切换帐号或翻页导致的旧响应记为 `cancelled`，都不计入失败率。库街区短信登录与塔吉多账密登录复用 `community_login_finished`（`provider=kuro|taygedo`，`stage=sms|password`）。

## 复用与归因边界

- **共享读写复用**：托管/账号常规配置保存（含专项更新方式、养成月卡、全部干员托管、协议空间与基质刷取、自定义启动参数等）统一复用 `config_write_finished`，不另建重复计数；专项运行期更新与预下载沿用 `task_observed_finished` / `script_run_finished`。
- **QQ 机器人命令**：私聊与群内触发任务沿用 `TaskManager.start` 与 `taskAnalytics.ts` 既有观察，不单独采集命令正文、白名单编辑或 QQ 标识。
- **模拟器终态归因**：仅关联本窗口发起的操作；缺少操作 ID 且同键并发重叠时放弃归因，超过 120 秒的终态不计耗时，单窗口最多保留 128 个未决/歧义键。
- **配置与权限隔离**：关闭动作与确认开关由 `useAppClosePreferences` 唯一确认；静默启动使用 `silent_start`；托盘菜单显式保存由主进程复用 `config_write_finished`。
