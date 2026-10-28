# 匿名统计场景覆盖台账

本表对应 [Issue #1605 的 84 项场景](https://github.com/AUTO-MAS-Project/AUTO-MAS/issues/1605#issuecomment-6354559213)。
场景可以共享事件族，事件契约存在不表示业务入口已经接入。每次提交前重新同步上游，并复核所有已接入项。
“已接入”描述代码边界，不表示已经完成真实游戏、扫码、升级或正式服务入库验收。

运行环境隔离统一使用 Electron 打包状态和 preload 下发值；Runtime 启动模式不改变采集环境。
此次复用既有事件族与结果所有者，业务覆盖范围不变，受控探针不作为正式服务入库证据。

| 编号 | 场景 | 当前进度 |
| --- | --- | --- |
| T001 | app_started：版本与启动方式分布 | 已接入，持续复核 |
| T002 | initialization_decided：多少启动需要初始化或直接进入 | 已接入，持续复核 |
| T003 | initialization_finished：初始化走完、失败、跳过分别多少 | 已接入，持续复核 |
| T004 | initialization_stage_finished：Python、依赖、仓库等阶段哪里卡住 | 已接入，持续复核 |
| T005 | initialization_recovery_selected：重试、重建、换镜像、跳过是否有效 | 已接入，持续复核 |
| T006 | backend_start_finished：后端启动成功率和等待时间 | 已接入，持续复核 |
| T007 | backend_restart_finished：主动更新和故障重启能否恢复 | 已接入，持续复核 |
| T008 | runtime_alignment_finished：Runtime 升级、校验、回退是否完成 | 已接入，持续复核 |
| T009 | backend_update_finished：后端热更新完成或停在什么阶段 | 已接入，持续复核 |
| T010 | renderer_recovery_decided：白屏、崩溃后自动恢复或放弃的比例 | 已接入，持续复核 |
| T011 | renderer_responsiveness_changed：卡死后能否恢复响应 | 已接入，持续复核 |
| T012 | app_close_finished：正常收尾、用户取消、强制关闭占比 | 已接入，持续复核 |
| T013 | tray_action_requested：托盘入口是否有实际使用 | 已接入，持续复核 |
| T014 | stop_all_requested：紧急停止入口的需求 | 已接入，持续复核 |
| T015 | virtual_display_action_finished：虚拟屏检查、拆除、用户选择的效果 | 已接入，持续复核 |
| T016 | virtual_display_prompt_answered：显示器恢复后用户怎样处理提示 | 已接入，持续复核 |
| T017 | renderer_ready：首屏挂载耗时与可见性 | 已接入，持续复核 |
| T018 | screen_view：用户实际访问哪些功能 | 已接入，持续复核 |
| T019 | connection_incident_finished：断线后多少能自动恢复 | 已接入，持续复核 |
| T020 | system_resume_recovery_finished：电脑唤醒后能否继续使用 | 已接入，持续复核 |
| T021 | script_create_finished：新增脚本漏斗和导入失败率 | 已接入，持续复核 |
| T022 | script_manage_finished：复制、删除、重排入口的使用 | 已接入，持续复核 |
| T023 | user_create_finished：第一次建托管账号是否顺利 | 已接入，持续复核 |
| T024 | user_manage_finished：删除、启停和批量账号管理 | 已接入，持续复核 |
| T025 | config_write_finished：配置保存失败是否普遍 | 已接入，持续复核 |
| T026 | user_config_write_finished：用户配置草稿与联动保存是否可靠 | 已接入，持续复核 |
| T027 | config_mode_changed：托管、原生、查看模式的使用 | 已接入，持续复核 |
| T028 | native_config_session_finished：原生配置窗口能否打开与保存 | 已接入，持续复核 |
| T029 | config_restore_finished：配置恢复实际完成率 | 已接入，持续复核 |
| T030 | task_start_result：从哪个入口开始任务、请求是否受理 | 已接入，持续复核 |
| T031 | task_observed_finished：前端观察到的任务结局 | 已接入，持续复核 |
| T032 | task_stop_result：中止请求是否被接受 | 已接入，持续复核 |
| T033 | task_resume_requested：从指定脚本继续、失败范围重试的需求 | 已接入，持续复核 |
| T034 | queue_manage_finished：队列新增、删除、配置是否顺利 | 已接入，持续复核 |
| T035 | queue_schedule_changed：定时、间隔、日期集合的使用 | 已接入，持续复核 |
| T036 | queue_time_set_changed：时间集合管理使用情况 | 已接入，持续复核 |
| T037 | plan_manage_finished：各类计划创建、删除、排序 | 已接入，持续复核 |
| T038 | plan_edit_finished：简单/复杂视图与轮换计划是否好用 | 已接入，持续复核 |
| T039 | update_check_finished：手动检查更新能否得到结果 | 已接入，持续复核 |
| T040 | update_download_started：用户选择更新后的进入率 | 已接入，持续复核 |
| T041 | update_download_finished：本体下载成功、失败和取消 | 已接入，持续复核 |
| T042 | update_source_changed：低速后换源能否改善 | 已接入，持续复核 |
| T043 | update_install_requested：下载后启动安装器还是稍后安装 | 已接入，持续复核 |
| T044 | emulator_discovery_finished：搜索、导入模拟器是否顺利 | 已接入，持续复核 |
| T045 | emulator_operation_result：启停、显示等操作是否被接受 | 已接入，持续复核 |
| T046 | emulator_operation_observed_finished：前端观察到的模拟器操作结局 | 已接入，持续复核 |
| T047 | emulator_instance_manage_finished：实例创建、删除与批量设置 | 已接入，持续复核 |
| T048 | emulator_guard_changed：稳定模式和配置守卫是否解决使用障碍 | 已接入，持续复核 |
| T049 | avd_root_added：自定义 AVD 安装导入完成率 | 已接入，持续复核 |
| T050 | game_sign_requested：手动签到的使用与被占用拒绝 | 已接入，持续复核 |
| T051 | community_account_manage_finished：签到账号创建、启停、删除 | 已接入，持续复核 |
| T052 | community_login_finished：扫码登录在生成、确认、保存何处失败 | 已接入，持续复核 |
| T053 | community_activity_requested：社区活动工具是否有需求 | 已接入，持续复核 |
| T054 | notification_test_finished：配置通知后测试是否顺利 | 已接入，持续复核 |
| T055 | notification_channel_changed：各内置通知渠道的启用情况 | 已接入，持续复核 |
| T056 | notification_binding_finished：二维码绑定、取消和解绑是否完成 | 已接入，持续复核 |
| T057 | webhook_test_finished：自定义通知配置是否容易出错 | 已接入，持续复核 |
| T058 | settings_change_finished：设置修改成功率及主要功能采用情况 | 已接入，持续复核 |
| T059 | appearance_preference_changed：主题、语言、低性能模式需求 | 已接入，持续复核 |
| T060 | appearance_package_finished：本地外观导入、启用、删除是否顺利 | 已接入，持续复核 |
| T061 | appearance_store_install_finished：主题商店发现到安装的转化 | 已接入，持续复核 |
| T062 | appearance_share_finished：外观上传与分享是否顺利 | 已接入，持续复核 |
| T063 | mascot_preference_changed：桌宠采用率和性能档位选择 | 已接入，持续复核 |
| T064 | home_activity_load_finished：首页活动信息在哪类来源不可用 | 已接入，持续复核 |
| T065 | home_layout_changed：首页布局与快速任务入口的使用 | 已接入，持续复核 |
| T066 | history_query_finished：历史检索能否帮助定位运行结果 | 已接入，持续复核 |
| T067 | diagnostic_export_finished：问题包和普通日志能否导出 | 已接入，持续复核 |
| T068 | data_backup_export_finished：用户能否成功备份 MAS 数据 | 已接入，持续复核 |
| T069 | replay_tool_finished：失败录屏连接、手动保存、回放的使用 | 已接入，持续复核 |
| T070 | help_link_requested：哪些功能需要文档帮助 | 已接入，持续复核 |
| T071 | adapter_setup_finished：MAA 配置与原生会话是否顺利 | 已接入现有引导入口，详见下文 |
| T072 | adapter_setup_finished：SRC 配置与会话是否顺利 | 已接入现有引导入口，详见下文 |
| T073 | adapter_setup_finished：MaaEnd 启动器、配置与更新是否完成 | 已接入现有引导入口，详见下文 |
| T074 | adapter_setup_finished：HSR 的不同执行方式配置是否顺利 | 已接入现有引导入口，详见下文 |
| T075 | adapter_setup_finished：通用脚本模板导入与配置是否顺利 | 已接入现有引导入口，详见下文 |
| T076 | adapter_setup_finished：BAAH 配置是否顺利 | 已接入现有引导入口，详见下文 |
| T077 | adapter_setup_finished：通用 MaaFW 首次引导、导入与环境准备 | 已接入现有引导入口，详见下文 |
| T078 | adapter_setup_finished：M9A flavor 配置入口使用 | 已接入现有引导入口，详见下文 |
| T079 | adapter_setup_finished：MSS flavor 配置与计划入口使用 | 已接入现有引导入口，详见下文 |
| T080 | adapter_setup_finished：BetterGI 原生配置、更新与托管模式 | 已接入现有引导入口，详见下文 |
| T081 | adapter_setup_finished：OK-WW 自动发现路径、更新与配置 | 已接入现有引导入口，详见下文 |
| T082 | adapter_setup_finished：OK-NTE 配置编辑与原生窗口 | 已接入现有引导入口，详见下文 |
| T083 | adapter_setup_finished：ZZZ-OD 原生实例与配置会话 | 已接入现有引导入口，详见下文 |
| T084 | adapter_setup_finished：奇想盒配置与原生会话 | 已接入现有引导入口，详见下文 |

## 当前批次边界

- 恢复：后端重启在共享执行位置记录，热更新首轮与重试分别记录真实返回；取消后重启旧后端仍归取消。唤醒以主连接状态为观察结果，不把启动受理算连接恢复。
- 模拟器：显式业务 API 记录搜索、路径管理、实例管理、单台及批量设置、守卫与 AVD 根目录添加。操作受理和完成消息分开；应用常驻订阅只关联本窗口发起的操作。重复帧、未发起的帧、被拒绝请求不制造完成。同设备同动作并发在缺少操作 ID 时放弃归因；两分钟后的终态不作为耗时样本；未决键不按时间过期或被逐出。同键重叠或响应不明后，该键本窗口内持续放弃完成归因；128 个未决/歧义键耗尽预算后本窗口停止新关联。请求统计仍继续。
- 退出：只记录观察到的协调结束、取消或强制清理失败，不等待遥测网络，也不保证退出末刻事件送达。
- 新增类别的类型与主进程白名单共用 analyticsFeaturePolicy.ts；84 项均有业务入口映射；共享事件与受理/完成边界在本表注明。关闭后原代次失效，不发送原始配置、对象标识、路径或错误内容。

## 验证记录

以 PR 评论中的提交编号、实际命令与结果为准。本台账不把源码复核当作真实集成测试。

## 管理与诊断批次补充

- T022/T024/T027：脚本与账号的删除、排序、账号启停、MAS 配置来源保存，以真实接口结果为准；整表重复保存不制造状态切换。T026 沿用 config_write_finished 的 user 口径，不再复制一份保存计数。
- T036/T038：时间集合按实际写入记录；计划表格按保存批次记录，MAA 整行操作与自定义项改名仍逐日串行保存，但汇总为一条 success/partial/failure。只保留计划类型与简化/复杂视图，不发送单元格内容。
- T044：旧版模拟器的创建记录与后续写配置合为一个导入结果；配置失败但记录已创建为 partial。保留原有界面刷新和缓存失效顺序。
- T050/T051/T053：手动签到区分 busy、部分完成和总体完成；社区账号普通保存不假装启停。空模板账号创建不表示已经登录，社区查询只记录类别和结果。
- T067/T068：主进程在导出实际返回后记录。MaaEnd 手动入口共用后端保存逻辑；已有自动归档时以文件夹实际打开结果为准，旧包完整性为 unknown，选目录取消仍为 cancelled。各问题包透传已存在收集清单的遗漏/截断数量；缺少完整性证据为 unknown，保存对话框取消为 cancelled。只发送完整性标记，不发送数量明细、附件或路径。
- T066/T069/T070：历史检索仅发送固定筛选类别和数量桶；统一附件中的视频从 play 到 playing 确认一次播放，缓冲恢复不重复记录，播放前媒体错误为 failure。手动保存录屏按 capture_path 是否存在确认结果，不发送路径。旧系统回放列表已随历史重构移除；内置文档/支持入口显式统计，通用外链函数不采集。

## 专项与细分维度批次补充

- T001/T017/T018/T019：启动固定区分手动/开机自启、Runtime 模式与稳定/公测；首屏增加可见性；页面仅记录白名单上一页面类别；断线原因只按公开关闭码归为固定类别，不发送 reason 文本。
- T015/T016：设置页只记录手动检查/拆除，自动状态探测不计数。询问窗的用户选择走限定窗口和主 frame 的专用桥，通用遥测桥仍只允许主窗；拆除请求由主进程持有，后端提前关窗不会丢掉实际 HTTP 结果。后端自动收窗不冒充用户取消。开发窗口可操作，但依旧停采。
- T071–T084：14 类专项的创建、MAS 配置保存、原生/查看会话和任务更新共用已有边界；源码中实际存在的其他引导分别接入：MAA 基建导入/选择与养成预览、MaaEnd 启动器发现、General 模板导入、MaaFW/M9A/MSS 项目预览/副本导入/同步/克隆/外壳实例导入/环境/更新、HSR M7A/SRA 更新与云登录、OK-WW 安装与游戏启动器发现、BetterGI 配置组保存、OK-NTE 独有配置保存、ZZZ-OD 原生/任务保存、导入、实例增删及回收操作。SRC、BAAH、奇想盒沿用其实际提供的公共保存/导入/原生会话，不虚构不存在的独有引导。
- 专项检查更新与应用更新分开；检查发现新版不能当作安装完成。已有任务式更新只记录 accepted/rejected，实际运行终态仍由任务观察事件报告；原生保存/安装没有可靠完成信号时同样不猜测成功。
- T081：OK-WW 更新以用户 UID 发起原业务请求，入口显式传入 Okww 分类；不拿用户 UID 查询脚本 UID 缓存，也不上报任何 UID。
- PR 复审 P3（6369303497/6369397213）：旧模拟器请求超过 120 秒仍可能返回，不能覆盖为新请求；已按未决/歧义键保留并在本地验证 A=0s、B=200s、A终态=300s 的顺序，禁止把 A 终态记到 B。

## 设置、外观和首页批次补充

- T058/T059：固定设置键只保留内置分类与 enabled/disabled/default/custom，不读取凭据或发送地址、日期等原值，遥测开关本身不发事件。主题、语言和性能只在显式修改时记录，初始化回填不记采用。语言选择在所需词表就绪、Electron 偏好保存后完成；后台词表刷新不新增事件。
- T003：后端已启动但业务词表不可用时，本次初始化结果为 failure、failed_stage 为 unknown；仅词表就绪并进入应用才记录完成。初始化页主动重试词表是新的进入尝试，断线自动恢复不补发已结束尝试的成功结果。
- T060–T063：本地主题/桌宠导入把文件选择、覆盖确认与最终原生返回合为一次；取消覆盖为 cancelled，桌宠已导入但选择写入未完成为 partial。删除以原生资源服务返回为准；主题启用以真实配置写入为准。商店桌宠已安装但选择保存失败同样为 partial，上传只记录最终接口结果。桌宠只记录开关、选择与 FPS 档位，不采动作、坐标、逐帧行为。
- T064：每游戏卡首个加载批次和实际开始新批次的手动刷新各一条；busy 跳过的刷新不复用旧结果。碧蓝档案三服与终末地两源保留稳定组合批次，汇总后判断 success/partial/failure/unknown。cache/mixed 描述前端已有快照/内容的使用，不推断代理或服务端缓存命中。自动退避、定时刷新、图片不增加统计。
- T065：首页排序、显示与快速任务选择只在显式用户保存后记录。迁移旧配置、后端托管列表、清理失效任务选择不制造采用事件；不传布局内容或任务标识。

84 项是业务场景，不等于 84 个独立事件名；T026 等复用已有配置写入，14 个专项复用固定 script_type 和实际存在的入口。本台账的代码覆盖不替代真实游戏、扫码、升级、虚拟屏硬件及正式服务入库验收。

- PR 复审 P3（6369823771）：导航来源与目标共用四种专项后缀映射，SetupWizard→UserAdd 为 script_setup，UserAdd→Scripts 为 user_add，首次进入与真正未知来源分别为 initial/other。

## 2026-10-24 验收

四批代码和商店桌宠 partial 复审修复：107 项针对性验证、96 项既有前端测试通过；四批代码的
11 项隔离浏览器流程通过。
隔离打包端专用入口复用未经修改的统计服务，本地收齐 72 类契约样本，生产只发一条独立验收版本的
测试进程启动；正式 Release 看板筛选 `0.0.0-telemetry-validation` 后可查询 1 个会话和 1 条
`app_started`。关闭前后、旧代次和额外字段未增加生产请求。原始 ASAR/配置已恢复。
仅证明该传输与开关边界，未把契约样本当成真实游戏、扫码、升级、硬件或真实混合/循环队列验收。
