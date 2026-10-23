# 匿名统计场景覆盖台账

本表对应 [Issue #1605 的 84 项场景](https://github.com/AUTO-MAS-Project/AUTO-MAS/issues/1605#issuecomment-6354559213)。
场景可以共享事件族，事件契约存在不表示业务入口已经接入。每次提交前重新同步上游，并复核所有已接入项。
“已接入”描述代码边界，不表示已经完成真实游戏、扫码、升级或正式服务入库验收。

| 编号 | 场景 | 当前进度 |
| --- | --- | --- |
| T001 | app_started：版本与启动方式分布 | 已有事件，补细分维度中 |
| T002 | initialization_decided：多少启动需要初始化或直接进入 | 已接入，持续复核 |
| T003 | initialization_finished：初始化走完、失败、跳过分别多少 | 已接入，持续复核 |
| T004 | initialization_stage_finished：Python、依赖、仓库等阶段哪里卡住 | 已接入，持续复核 |
| T005 | initialization_recovery_selected：重试、重建、换镜像、跳过是否有效 | 已接入，持续复核 |
| T006 | backend_start_finished：后端启动成功率和等待时间 | 已接入，持续复核 |
| T007 | backend_restart_finished：主动更新和故障重启能否恢复 | 本批接入 |
| T008 | runtime_alignment_finished：Runtime 升级、校验、回退是否完成 | 本批接入 |
| T009 | backend_update_finished：后端热更新完成或停在什么阶段 | 本批接入 |
| T010 | renderer_recovery_decided：白屏、崩溃后自动恢复或放弃的比例 | 本批接入 |
| T011 | renderer_responsiveness_changed：卡死后能否恢复响应 | 本批接入 |
| T012 | app_close_finished：正常收尾、用户取消、强制关闭占比 | 本批接入 |
| T013 | tray_action_requested：托盘入口是否有实际使用 | 本批接入 |
| T014 | stop_all_requested：紧急停止入口的需求 | 本批接入 |
| T015 | virtual_display_action_finished：虚拟屏检查、拆除、用户选择的效果 | 待接入 |
| T016 | virtual_display_prompt_answered：显示器恢复后用户怎样处理提示 | 待接入 |
| T017 | renderer_ready：首屏挂载耗时与可见性 | 已接入，持续复核 |
| T018 | screen_view：用户实际访问哪些功能 | 已有事件，补细分维度中 |
| T019 | connection_incident_finished：断线后多少能自动恢复 | 已有事件，补细分维度中 |
| T020 | system_resume_recovery_finished：电脑唤醒后能否继续使用 | 本批接入 |
| T021 | script_create_finished：新增脚本漏斗和导入失败率 | 已接入，持续复核 |
| T022 | script_manage_finished：复制、删除、重排入口的使用 | 待接入 |
| T023 | user_create_finished：第一次建托管账号是否顺利 | 已接入，持续复核 |
| T024 | user_manage_finished：删除、启停和批量账号管理 | 待接入 |
| T025 | config_write_finished：配置保存失败是否普遍 | 已接入，持续复核 |
| T026 | user_config_write_finished：用户配置草稿与联动保存是否可靠 | 已接入，持续复核 |
| T027 | config_mode_changed：托管、原生、查看模式的使用 | 待接入 |
| T028 | native_config_session_finished：原生配置窗口能否打开与保存 | 已接入，持续复核 |
| T029 | config_restore_finished：配置恢复实际完成率 | 已接入，持续复核 |
| T030 | task_start_result：从哪个入口开始任务、请求是否受理 | 已接入，持续复核 |
| T031 | task_observed_finished：前端观察到的任务结局 | 已接入，持续复核 |
| T032 | task_stop_result：中止请求是否被接受 | 已接入，持续复核 |
| T033 | task_resume_requested：从指定脚本继续、失败范围重试的需求 | 已接入，持续复核 |
| T034 | queue_manage_finished：队列新增、删除、配置是否顺利 | 已接入，持续复核 |
| T035 | queue_schedule_changed：定时、间隔、日期集合的使用 | 已接入，持续复核 |
| T036 | queue_time_set_changed：时间集合管理使用情况 | 待接入 |
| T037 | plan_manage_finished：各类计划创建、删除、排序 | 已接入，持续复核 |
| T038 | plan_edit_finished：简单/复杂视图与轮换计划是否好用 | 待接入 |
| T039 | update_check_finished：手动检查更新能否得到结果 | 已接入，持续复核 |
| T040 | update_download_started：用户选择更新后的进入率 | 已接入，持续复核 |
| T041 | update_download_finished：本体下载成功、失败和取消 | 已接入，持续复核 |
| T042 | update_source_changed：低速后换源能否改善 | 已接入，持续复核 |
| T043 | update_install_requested：下载后启动安装器还是稍后安装 | 已接入，持续复核 |
| T044 | emulator_discovery_finished：搜索、导入模拟器是否顺利 | 搜索与路径管理已接入，旧版整段导入待补 |
| T045 | emulator_operation_result：启停、显示等操作是否被接受 | 本批接入 |
| T046 | emulator_operation_observed_finished：前端观察到的模拟器操作结局 | 本批接入 |
| T047 | emulator_instance_manage_finished：实例创建、删除与批量设置 | 本批接入 |
| T048 | emulator_guard_changed：稳定模式和配置守卫是否解决使用障碍 | 本批接入 |
| T049 | avd_root_added：自定义 AVD 安装导入完成率 | 本批接入 |
| T050 | game_sign_requested：手动签到的使用与被占用拒绝 | 待接入 |
| T051 | community_account_manage_finished：签到账号创建、启停、删除 | 待接入 |
| T052 | community_login_finished：扫码登录在生成、确认、保存何处失败 | 已接入，持续复核 |
| T053 | community_activity_requested：社区活动工具是否有需求 | 待接入 |
| T054 | notification_test_finished：配置通知后测试是否顺利 | 已接入，持续复核 |
| T055 | notification_channel_changed：各内置通知渠道的启用情况 | 已接入，持续复核 |
| T056 | notification_binding_finished：二维码绑定、取消和解绑是否完成 | 已接入，持续复核 |
| T057 | webhook_test_finished：自定义通知配置是否容易出错 | 已接入，持续复核 |
| T058 | settings_change_finished：设置修改成功率及主要功能采用情况 | 待接入 |
| T059 | appearance_preference_changed：主题、语言、低性能模式需求 | 待接入 |
| T060 | appearance_package_finished：本地外观导入、启用、删除是否顺利 | 待接入 |
| T061 | appearance_store_install_finished：主题商店发现到安装的转化 | 待接入 |
| T062 | appearance_share_finished：外观上传与分享是否顺利 | 待接入 |
| T063 | mascot_preference_changed：桌宠采用率和性能档位选择 | 待接入 |
| T064 | home_activity_load_finished：首页活动信息在哪类来源不可用 | 待接入 |
| T065 | home_layout_changed：首页布局与快速任务入口的使用 | 待接入 |
| T066 | history_query_finished：历史检索能否帮助定位运行结果 | 待接入 |
| T067 | diagnostic_export_finished：问题包和普通日志能否导出 | 待接入 |
| T068 | data_backup_export_finished：用户能否成功备份 MAS 数据 | 待接入 |
| T069 | replay_tool_finished：失败录屏连接、手动保存、回放的使用 | 待接入 |
| T070 | help_link_requested：哪些功能需要文档帮助 | 待接入 |
| T071 | adapter_setup_finished：MAA 配置与原生会话是否顺利 | 公共创建/保存/会话已有，专项引导待补 |
| T072 | adapter_setup_finished：SRC 配置与会话是否顺利 | 公共创建/保存/会话已有，专项引导待补 |
| T073 | adapter_setup_finished：MaaEnd 启动器、配置与更新是否完成 | 公共创建/保存/会话已有，专项引导待补 |
| T074 | adapter_setup_finished：HSR 的不同执行方式配置是否顺利 | 公共创建/保存/会话已有，专项引导待补 |
| T075 | adapter_setup_finished：通用脚本模板导入与配置是否顺利 | 公共创建/保存/会话已有，专项引导待补 |
| T076 | adapter_setup_finished：BAAH 配置是否顺利 | 公共创建/保存/会话已有，专项引导待补 |
| T077 | adapter_setup_finished：通用 MaaFW 首次引导、导入与环境准备 | 公共创建/保存/会话已有，专项引导待补 |
| T078 | adapter_setup_finished：M9A flavor 配置入口使用 | 公共创建/保存/会话已有，专项引导待补 |
| T079 | adapter_setup_finished：MSS flavor 配置与计划入口使用 | 公共创建/保存/会话已有，专项引导待补 |
| T080 | adapter_setup_finished：BetterGI 原生配置、更新与托管模式 | 公共创建/保存/会话已有，专项引导待补 |
| T081 | adapter_setup_finished：OK-WW 自动发现路径、更新与配置 | 公共创建/保存/会话已有，专项引导待补 |
| T082 | adapter_setup_finished：OK-NTE 配置编辑与原生窗口 | 公共创建/保存/会话已有，专项引导待补 |
| T083 | adapter_setup_finished：ZZZ-OD 原生实例与配置会话 | 公共创建/保存/会话已有，专项引导待补 |
| T084 | adapter_setup_finished：奇想盒配置与原生会话 | 公共创建/保存/会话已有，专项引导待补 |

## 当前批次边界

- 恢复：后端重启在共享执行位置记录，热更新首轮与重试分别记录真实返回；取消后重启旧后端仍归取消。唤醒以主连接状态为观察结果，不把启动受理算连接恢复。
- 模拟器：显式业务 API 记录搜索、路径管理、实例管理、单台及批量设置、守卫与 AVD 根目录添加。操作受理和完成消息分开；应用常驻订阅只关联本窗口发起的操作。重复帧、未发起的帧、被拒绝请求不制造完成。同设备同动作并发在缺少操作 ID 时放弃归因；两分钟后仍未观察到结果的样本丢弃。
- 退出：只记录观察到的协调结束、取消或强制清理失败，不等待遥测网络，也不保证退出末刻事件送达。
- 新增类别的类型与主进程白名单共用 analyticsFeaturePolicy.ts；仅定义的后续类别仍在台账标为待接入。关闭后原代次失效，不发送原始配置、对象标识、路径或错误内容。

## 验证记录

以 PR 评论中的提交编号、实际命令与结果为准。本台账不把源码复核当作真实集成测试。
