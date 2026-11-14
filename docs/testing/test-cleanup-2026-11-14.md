# 存量单测清理（2026-11-14）

按实际故障、责任边界和长期维护收益重新筛查249个文件，删除116个定义，将38个重合来源定义归并进已有测试，并裁剪混合用例中的低价值断言。生产代码未改；人工确认保留的14个定义和受保护的 MaaFW 核心文件均核对未变。

## 范围与实际结果

| 范围 | 原定义 | 删除 | 归并移除来源 | 剩余定义 |
| --- | ---: | ---: | ---: | ---: |
| 前端与 Electron | 291 | 39 | 6 | 246 |
| 后端 API、核心、模型、服务、平台、发布工具 | 524 | 40 | 12 | 472 |
| 专项、工具与通用基础设施 | 744 | 37 | 20 | 687 |
| 合计 | 1559 | 116 | 38 | 1405 |

定义数不展开参数化；已有用例归并保留的输入仍可能展开为多项。原索引漏掉了开发启动器中callback后带options参数的一条Node测试，现用TypeScript AST补记，属于原有测试而非本轮新增。测试文件由249减至232。

本轮逐定义筛查断言与调用，对删除、合并及存疑候选补读完整测试、相关责任函数和消费者；不声称把全部保留项的所有依赖和历史逐行深读完。38条归并来源已实际迁移输入或有效断言；应用时确认是不同故障、不同入口或不同边界的候选，保留独立场景，没有硬塞成复杂多分支测试。

逐项删除依据、归并目标和后端失败节点见下文附表。完整原始审阅索引与执行日志保留在作者本地工作树，本报告记录可供仓库审查的结果；未新增长期测试框架。

## 已执行的清理

- 删除仅固定SSR文字、光标像素、选项清单、路由总数、对象身份、私有字段初值和内部转发的断言；混合用例保留实际入口、保存失败、恢复重试和安全边界。
- 写盘定位在真实责任边界判断，删除修改周一后检查周二、任意相邻账号不变等间接表象，保留真正迁移落盘后重新读取的数据结果。
- 合并同一解析、迁移、日志、来源选择和协议边界的重合覆盖；保留输入与独有失败结果。没有为测试构造跨专项私有方法分发表，也没有为保留数量创造生产公共类。
- 十专项重复枚举超时字段的检查缩为GeneralConfig一次真实wire输入、写盘、重载至公共运行消费；实际超时取消回归仍保留。各专项字段当前独立声明，不能声称本轮建立了共享字段拥有者或继续逐一守护九份声明。
- 删除仍在演进的Sentry字段名单、i18n缺失时回落原文、未知/旧事件文本退化等门禁；没有修改生产脱敏或兜底行为。诊断测试只保留明确敏感内容不入日志的检查。
- 删除活动迁移与养成目标commit-hook的耦合；删除手工MAS_STEP/Dispatcher日志拼出的BetterGI成败判定测试。保留不执行外部插件代码的安全保证和不解释私有记录的原始字节备份/恢复；删除测试不表示既有生产判定逻辑已被修复或完成上游契约核验。
- 发布工具删除重复生成物相等、当前公告内容快照、15000字符余量探针和PR正文逐字编排门禁；保留真实版本推进、Git历史归属、发布检查与客户端JSON/预算边界，并归并同一解析/渲染输入。

## 已确认的取舍及保留边界

| 范围 | 人工审阅结论 | 已执行 |
| --- | --- | --- |
| 诊断日志 | 删除诊断事件清单，只保留敏感内容不入日志 | 裁剪Runtime诊断及同类连接诊断的固定分类/清单断言 |
| 活动迁移 | 删除耦合断言，迁移只验证自身结果 | 删除仅验证养成目标commit-hook的用例，保留迁移落盘重载 |
| 不完整计划 | 不保留人工缺字段计划用例 | 删除该用例，保留真实日期分组规则 |
| 上游成败判定 | 不保留这类自造判定测试 | 删除BetterGI手工日志成败判定的4个定义 |

其余保留不等于所有上游假设都已获得新认证：插件私有清单、真实游戏能力与历史实现的黑箱边界并非本轮生产重构范围。没有因“只有这一条覆盖”默认保留低价值测试，也没有按预定百分比删除。

## 验证

| 检查 | 清理前 | 清理后 |
| --- | --- | --- |
| 前端 `cd frontend; yarn test` | 64文件、358项通过 | 54文件、301项通过 |
| 后端 `uv run --locked --group dev python -m pytest tests -q --disable-warnings --basetemp <工作树临时目录>` | 2051通过、34失败、2跳过 | 1907通过、35失败、2跳过 |
| Python受改文件 `ruff check` / `ruff format --check` | 未作为基线全仓检查 | 49个现存受改Python文件通过 |
| 前端 `yarn lint`、`yarn typecheck`、Electron `tsc --noEmit`、受改文件格式检查 | 单测基线通过 | 均通过；lint有未改文件QueueDeleteButton.vue的一条既有warning |

后端34个原失败节点在清理后全部仍在，没有通过删除或弱化这些测试让失败消失。本轮全量额外出现一个未改的MaaFW预取用例，在目录换入时发生Windows WinError5；该节点单独重跑1项通过，所在文件单独重跑23项全部通过。全量结果仍为35失败，不将复跑通过写成全量通过；执行顺序与Windows文件系统波动的因果尚未证明。

裁剪后的插件原始记录恢复用例在一次独立运行中也遇到目录rename拒绝访问；同环境临时还原HEAD原函数后复现相同错误，未加sleep/mock或改生产绕过。相关对照日志保留在临时审查目录。

默认Windows pytest临时根曾产生PermissionError，正式前后对照均改用已校验位于工作树内的独立 `--basetemp`。环境脚本分配应用端口37742；本轮没有启动应用，因此没有使用该应用端口。未做真实Electron页面、Runtime可执行文件、游戏、模拟器或上游网络E2E。

本轮未提交、推送或创建PR。纯测试/规范清理不新增用户更新日志碎片。

## 删除明细

以下名称取自核验基线 `7af5238026204f0e827749e8b6c44a4557dc3d82`；删除只发生在列出的用例，混合文件其余有效覆盖保留。

| 原测试 | 删除依据 |
| --- | --- |
| `frontend/electron/ipc/initializationProgress.test.ts::preserves download metadata through %s` | 大段IPC→SSR用例最终固化下载来源/顺序/原文/KB与翻译展示；Runtime初始化实际恢复入口由U0003、U0270、U0272、U0273验证。 |
| `frontend/electron/ipc/initializationProgress.test.ts::keeps dependency source attempts and official fallback visible through %s` | 大段IPC→SSR用例最终固化下载来源/顺序/原文/KB与翻译展示；Runtime初始化实际恢复入口由U0003、U0270、U0272、U0273验证。 |
| `frontend/electron/services/backendService.test.ts::环境变更进行中拒绝第二次操作，完成后允许显式恢复` | 仅传入悬挂的匿名operation验证通用互斥状态，未从两个安装/修复IPC请求触发具体文件或后端冲突；这是“锁正常工作”演示。 |
| `frontend/electron/services/runtime/launchConfig.test.ts::存量 %s 设置不再覆盖构建默认值` | 生产resolveRuntimeLaunchModeDetail已经完全不读取旧Runtime.LaunchMode；测试仅向无人读取的旧文件写三个值再重复构建默认断言。 |
| `frontend/electron/services/scheduledWakeup.test.ts::allows a fresh automatic quit after a manual attempt was cancelled` | 人工审阅：用户：S不保留；“取消手动退出”的流程前提不合理，中断流程再嵌套中断流程，不应作为保留依据。 |
| `frontend/electron/services/sentryPrivacy.test.ts::保留恢复诊断数值，移除自由文本、用户与未知字段` | 人工审阅：用户认为组织内Sentry脱敏规则需在使用中持续权衡敏感信息与排查信息，尚无稳定名单，不应固化为每次必须通过的门禁。 |
| `frontend/electron/services/sentryPrivacy.test.ts::普通事件与非法数值不获得恢复诊断豁免` | G明确拒绝把仍需使用中权衡的组织Sentry诊断白名单固化为持续门禁；U0135仍在固定同一数值/字段例外策略，按同因清理。 |
| `frontend/src/components/appearanceCursor.test.ts::sets the longest edge to %i and scales the hotspot` | 只固定光标缩放尺寸/热点/边界和缺角色映射；未执行真实图像decode/canvas应用或用户设置保存，不值得随像素参数调整维护。 |
| `frontend/src/components/appearanceCursor.test.ts::keeps the rounded hotspot inside a thin, downscaled image` | 只固定光标缩放尺寸/热点/边界和缺角色映射；未执行真实图像decode/canvas应用或用户设置保存，不值得随像素参数调整维护。 |
| `frontend/src/components/appearanceCursor.test.ts::uses the original size for %s` | 只固定光标缩放尺寸/热点/边界和缺角色映射；未执行真实图像decode/canvas应用或用户设置保存，不值得随像素参数调整维护。 |
| `frontend/src/components/appearanceCursor.test.ts::accepts the supported limit %i` | 只固定光标缩放尺寸/热点/边界和缺角色映射；未执行真实图像decode/canvas应用或用户设置保存，不值得随像素参数调整维护。 |
| `frontend/src/components/appearanceCursor.test.ts::keeps native fallback for missing cursor roles` | 只固定光标缩放尺寸/热点/边界和缺角色映射；未执行真实图像decode/canvas应用或用户设置保存，不值得随像素参数调整维护。 |
| `frontend/src/composables/useNativeGuiSession.test.ts::uses the requirement-tree entry for a native session` | 当前只mock requestScriptConfigStart并比较转发参数；不执行要求树构造/实际会话结果，不能证明迁移后打开正确会话。 |
| `frontend/src/composables/useNativeGuiSession.test.ts::does not query a deferred plan result when saving a normal session` | Service状态查询在当前生产useNativeGuiSession根本没有导入；断言一个不被查找的旧mock未调用只锁定迁移残影。 |
| `frontend/src/composables/useSatelliteStatus.test.ts::查询失败保留最近一次有效配置结果` | 复核按用户标准清理第三方缓存机制自证或只有数字映射、未证明实际平台故障的用例。 |
| `frontend/src/services/systemNotices.test.ts::preserves plain messages from older backends` | 人工审阅：用户确认 X 不保留：i18n 缺失应补齐 i18n，不应退化为原始标题；这种证明出现 bug 时会退化的测试对开发者和用户都没有意义。 |
| `frontend/src/utils/fieldPatch.test.ts::preserves a nested field value without mutating or copying it` | 嵌套对象保持===原引用不是公开保存契约，拷贝一个等值补丁也应通过；本例只固定投影实现与未变原值。 |
| `frontend/src/views/EditView/Script/components/OkwwAccountSwitchField.test.ts::offers separate per-account and batch native switching choices` | 仅SSR复制四个选项值和十条提示/翻译字符串，未选择切号方式或触发保存/脚本。 |
| `frontend/src/views/EditView/Script/components/WhimboxUpdateSettings.test.ts::starts disabled and saves enabling and disabling` | 测试只调用stub捕获的change，断言两个model初值/事件值；保存落盘和执行更新均不在场。 |
| `frontend/src/views/EditView/Script/components/WhimboxUpdateSettings.test.ts::prevents saving while the script is loading` | ASwitch替身自己用if(!props.disabled)阻止emit；生产组件只有disabled属性并转发change，本例“不能保存”主要由替身保证。 |
| `frontend/src/views/EditView/User/BAAHUserEdit.test.ts::keeps real configuration controls without offering ineffective source or override modes` | 人工审阅：用户确认 W 不保留，未另述理由。 |
| `frontend/src/views/EditView/User/components/OkwwArgumentsConfig.test.ts::keeps default arguments readonly while custom mode is off` | SSR不执行onMounted中的参数请求，也没有编辑/提交事件；初始resolvedArguments为空便能满足默认参数缺席，custom模式只断言value属性，无法守护“编辑不改写参数”。 |
| `frontend/src/views/EditView/User/components/OkwwArgumentsConfig.test.ts::allows editing without rewriting the entered arguments` | SSR不执行onMounted中的参数请求，也没有编辑/提交事件；初始resolvedArguments为空便能满足默认参数缺席，custom模式只断言value属性，无法守护“编辑不改写参数”。 |
| `frontend/src/views/EditView/User/components/OkwwArgumentsConfig.test.ts::inherits the account configuration lock from its form` | Form disabled传播给Input/Button由Antd useProviderDisabled/useInjectDisabled实现，已核对依赖源码；本用例只SSR该第三方行为，没有触发MAS配置锁或被拒的保存。 |
| `frontend/src/views/Emulator/emulatorTabTitle.test.ts::omits the repeated installation path without changing custom names` | 仅从标签移除重复路径及保留自定义标题，用户可观察后果是局部文字，未涉及选错模拟器/改变路径/启动。 |
| `frontend/src/views/Emulator/settingsTiers.test.ts::sends the default 1080p and an explicit 720p through creation options` | createOptions只是把表单三个字段原样投影，本例仅确认默认1080/显式720参数；没有保存/创建结果，按用户Y同类参数标准不保留。 |
| `frontend/src/views/Emulator/settingsTiers.test.ts::recognizes portrait presets and changes dimensions and DPI together` | 人工审阅：用户确认 Y 不保留：生成参数本就是实现应做的事，用例未说明不生成参数会造成什么用户损失或功能错误，仅确认生成了参数没有保留意义。 |
| `frontend/src/views/Emulator/settingsTiers.test.ts::keeps family-specific DPI in batch settings` | 复核按用户标准清理第三方缓存机制自证或只有数字映射、未证明实际平台故障的用例。 |
| `frontend/src/views/Initialization/useInitializationFlow.test.ts::re-renders the same received repository event in Chinese, English and Japanese` | 仅保留/翻译进度文字、来源顺序与旧事件原文，并逐一枚举协议stage和三种语言；不影响进程恢复/按钮可达性。 |
| `frontend/src/views/Initialization/useInitializationFlow.test.ts::keeps the reported source order and transfer state while switching languages` | 仅保留/翻译进度文字、来源顺序与旧事件原文，并逐一枚举协议stage和三种语言；不影响进程恢复/按钮可达性。 |
| `frontend/src/views/Initialization/useInitializationFlow.test.ts::updates recovery download text reactively and preserves legacy update events` | 仅保留/翻译进度文字、来源顺序与旧事件原文，并逐一枚举协议stage和三种语言；不影响进程恢复/按钮可达性。 |
| `frontend/src/views/Initialization/useInitializationFlow.test.ts::localizes the reachable top-level states and keeps unrelated protocol stages raw` | 仅保留/翻译进度文字、来源顺序与旧事件原文，并逐一枚举协议stage和三种语言；不影响进程恢复/按钮可达性。 |
| `frontend/src/views/Initialization/useInitializationFlow.test.ts::localizes known normal statuses while leaving failures and unknown events untouched` | 仅保留/翻译进度文字、来源顺序与旧事件原文，并逐一枚举协议stage和三种语言；不影响进程恢复/按钮可达性。 |
| `frontend/src/views/MAAUserEdit/maaPlanCurrent.test.ts::does not use fixed values when the selected plan group is incomplete` | 人为传入缺MedicineNumb/SeriesNumb等字段的计划；代码确实返回null，但尚未证实真实getPlans响应可省略这些已由后端配置模型补默认的字段。 |
| `frontend/src/views/WhimboxUserEdit/BasicInfoSection.test.ts::does not promise a shared base for %s` | Whimbox测试只检查SSR说明文字、aria-label有无和词句变化，不执行base配置物化、切换保存或任务。 |
| `frontend/src/views/WhimboxUserEdit/BasicInfoSection.test.ts::shows the native override effect when enabled=%s` | Whimbox测试只检查SSR说明文字、aria-label有无和词句变化，不执行base配置物化、切换保存或任务。 |
| `frontend/src/views/scripts/components/scriptCreateFlow.test.ts::keeps the existing order and the two general choices` | SCRIPT_TYPE_OPTIONS来自已有SCRIPT_METADATA与MAAFW_FLAVORS；逐项复制14个类型/顺序是登记清单镜像。 |
| `frontend/src/views/taskboard/VersionStoryPanel.test.ts::uses the provided clock to show the gap before the next version starts` | 只锁定中文SSR倒计时句子和日期显示；不验证目录获取、完成标记写入或版本归属。 |
| `frontend/src/views/taskboard/VersionStoryPanel.test.ts::stops treating the new version start as the next update after it begins` | 只锁定中文SSR倒计时句子和日期显示；不验证目录获取、完成标记写入或版本归属。 |
| `tests/core/test_background_tasks.py::test_invalid_policy_is_rejected` | 生产register_group参数均为代码内常量；这里只枚举自造无效配额并证明ValueError，未覆盖通知或退出中的可达故障。 |
| `tests/core/test_components.py::test_community_flow_excludes_concurrent_callers_and_releases_after_use` | 用户：Q意义不明，错误场景不清晰，不保留。 |
| `tests/core/test_maintenance_cycle_review.py::test_rejected_creation_does_not_advance_any_clock` | 受理全部拒绝后时钟不变与timed_fired为空；真实L1事务失败由U0413覆盖，拒绝同分钟重试由U0417覆盖，不再保留完全stub调度入口的同义检查。 |
| `tests/core/test_maintenance_cycle_review.py::test_startup_async_task_runs_once_per_timer_instance` | start/stop同一个timer实例两次但mock掉所有定时循环，只断言内部startup协程仅被调用一次；未建立用户实际重启/重复派发场景，真实DailyFirst去重由U0350覆盖。 |
| `tests/core/test_notify.py::test_dispatch_continues_after_system_failure` | 用户：T不保留，意义不明。 |
| `tests/core/test_notify_entry.py::test_core_notify_is_shared_instance_without_channel_initialization` | 重复共享组件导入测试；U0320已跨多导入顺序核对Notify/core的同一实例与惰性初始化，windows依赖闭包由平台/启动边界保留。 |
| `tests/core/test_notify_entry.py::test_notification_transport_can_initialize_without_api_routes` | 用自造MetaPathFinder禁止app.api，再读取同一个_transport两次并数bind调用；只固定内部分层/缓存，未执行真实投递或说明独立用户故障。 |
| `tests/core/test_notify_entry.py::test_api_consumers_share_singleton_and_manifests_keep_canonical_paths` | 单例身份重复U0320；entrypoint以app.core.notify.channels开头仅钉内部包名，正确渠道能否加载由启动/投递行为守护。 |
| `tests/core/test_notify_entry.py::test_global_manager_prepares_channels_once_and_close_does_not_recreate` | 替换真实registry和channels后只数bind/stop调用并查私有属性；没有真实渠道资源泄漏、二次发信或退出结果，属于内部缓存/正常调用。 |
| `tests/core/test_power.py::test_failed_native_action_does_not_request_exit` | SLEEP成功也不请求退出，power_task未创建便恒为None，不能区别声称的原生失败故障。 |
| `tests/core/test_scheduler_ownership.py::test_deferred_prefetch_does_not_run_during_queue_dispatch` | 此测试仅创建一个队列项，没有可预取的下一托管；即使预取已接入也会通过，无法证明所谓延期。 |
| `tests/core/test_scheduler_ownership.py::test_deferred_plan_session_does_not_restore_flat_creation_arguments` | 固定已移除的扁平planId/planDay请求不得出现，未保护现行计划会话的独立用户流程；内部升级同步调用者，不长期守护旧参数不存在的形状。 |
| `tests/core/test_scheduler_ownership.py::test_timer_does_not_write_clocks_when_creation_is_only_stubbed` | 将L1完全stub成成功后只证timer没写时钟，不能验证真实受理记账。 |
| `tests/core/test_script_observation.py::test_observation_capacity_drops_only_messages_and_keeps_business_metrics` | 以17次空运行上下文和固定32项配额只数本地消息/metric调用；未建立值得固化的产品容量保证或实际丢报/业务阻塞。 |
| `tests/core/test_script_registration.py::test_explicit_unsupported_is_distinct_from_missing` | 全None的虚构AdapterConfig只测内部不支持哨兵、重复绑定和MappingProxyType不可写；不是实际脚本的用户可达配置/执行/恢复流程，初始化装配错误由真实启动暴露。 |
| `tests/core/test_script_registration.py::test_test_adapter_three_lines_and_two_hosts_share_no_dependencies` | 测试专造两个AppConfig.__new__宿主、虚构AdapterConfig并测试相互隔离；main只创建一个全局Config并一次装配，无受支持的双宿主用户流程。 |
| `tests/core/test_script_registration.py::test_public_task_creation_passes_current_host_factories` | 当前宿主factories正常传入的路径已由真实scheduler fixture→manager.start→Builtin完成的U0520覆盖；此项重复造自定义registry，只额外数构造器参数和内部字典身份。 |
| `tests/core/test_script_registration.py::test_unbound_task_manager_fails_before_mutating_task_state` | 绕过main实际装配构造未绑定_TaskManager再传空树，只证明初始化前内部保护会报错；main在进入调度前必绑定，不是可达用户故障。 |
| `tests/core/test_script_update_download.py::test_actual_downloader_changes_on_http_fallback_without_extra_user_callbacks` | fake transport自己决定调用progress与http_download，断言下载器文字序列和回调次数；没有下载正确性或停写保证，属于内部展示观察。 |
| `tests/core/test_script_update_download.py::test_download_observers_are_isolated_between_concurrent_tasks` | 只为ContextVar观察回调造两个并发任务并数参数归属，未验证实际下载文件、候选交接或用户可见串进度；候选/日志实际隔离保留U0470/U0471。 |
| `tests/core/test_script_update_entry.py::test_update_waits_for_installation_before_returning` | 未设置TaskProcessScope，run_script_update实际只有日志和return await operation；五种script_type仅改变日志。 |
| `tests/core/test_script_update_entry.py::test_cancellation_waits_for_operation_cleanup` | 该入口无scope时仅return await operation，测试实际验证自造协程finally的Python取消；U0472执行真实会话并证明清理前配置锁不释放。 |
| `tests/core/test_script_update_queue.py::test_unhealthy_user_does_not_start_download` | 所谓不健康用户检查由测试传入的completed_at lambda自行实现，生产ScriptUpdateSession传入自身_completed_at；测试可证明测试lambda，不能证明生产用户故障。 |
| `tests/core/test_script_update_queue.py::test_first_success_clock_survives_account_switch_before_sixty` | 切号只修改替身user_list/current_index，队列本身不读这些字段；completed_at lambda固定script.first_task_completed_at，断言await Event仅证明其未变，未执行真实切号契约。 |
| `tests/core/test_script_update_queue.py::test_unconfirmed_fluxdown_stop_blocks_handoff` | 同一未停writer阻断交接在U0447由真实FluxDown service→queue链保留；此项直接让operation抛约定异常，新增收益仅异常透传。 |
| `tests/core/test_script_update_queue.py::test_unconfirmed_fluxdown_cancel_remains_visible` | 只直接测私有_cancel_and_wait透传自造finally错误；U0519经真实账号TaskBase吞异常后仍阻断下一托管，更强覆盖。 |
| `tests/core/test_script_update_queue.py::test_unconfirmed_retry_stop_remains_blocking_at_outer_handoff` | 外层handoff再次报未停writer的保证已由U0519实际账号生命周期与双托管执行覆盖；此项只在queue手动重复finish/watch。 |
| `tests/models/test_account_status_tags.py::test_last_result_color` | 仅断言getTags输出red/green；状态值为输入，没执行任务成败、保存或列表行为。 |
| `tests/models/test_account_status_tags.py::test_ordinary_account_details_use_neutral_color` | 仅断言标签数组最后两项颜色default，耦合展示顺序和局部样式，无独立数据/功能故障。 |
| `tests/models/test_config_signal_rejection.py::test_signal_rejection_closes_created_coroutines` | 直接调用私有_dispatch，替换receivers_for顺序并inspect协程CLOSED；只验证内部资源状态/不再发RuntimeWarning，没有保存、事务失败或用户结果。 |
| `tests/models/test_schema_legacy_base_compat.py::LegacyInfoModeCompatTest.test_explicit_base_wins_and_unknown_mode_rejected` | 此项固化旧Info.Mode在线请求长期兼容；用户要求内部更新只迁移，现行请求用Base。 |
| `tests/models/test_schema_legacy_base_compat.py::LegacyInfoModeCompatTest.test_update_user_request_keeps_legacy_source` | 旧Info.Mode在线更新请求不是历史文件迁移；内部新旧业务双契约不作长期门禁，保留实际迁移入口U0558。 |
| `tests/scripts/test_changelog_script.py::test_changelog_round_trips_to_itself` | 当前仓库CHANGELOG逐字归一化与全生成目标检查重合。 |
| `tests/scripts/test_changelog_script.py::test_version_json_matches_changelog` | version.json当前仓库结果逐字相等已由全生成目标覆盖。 |
| `tests/scripts/test_changelog_script.py::test_pr_body_keeps_only_a_count_of_unconfirmed_commits` | 仅固定发布PR/运行摘要的编排与逐字措辞；真正未入账提交识别由真实git测试U0672守护，客户端首行JSON由U0650/U0652/U0653守护。 |
| `tests/scripts/test_changelog_script.py::test_repository_release_note_fits_the_budget` | 当前公告内容快照的预算检查与真实预算算法边界及发布检查重复，正常内容增长不应新增长期门禁。 |
| `tests/scripts/test_changelog_script.py::test_repository_stable_rollup_leaves_room_for_more_betas` | 15000是一次公告整理成果的余量探针，真实发布契约预算18000且已有裁剪/熔断场景。 |
| `tests/services/test_update_fluxdown_proxy.py::test_direct_proxy_and_history_redaction` | None代理转换与record.to_dict的局部脱敏示例无须独立门禁；真正的现有/新历史记录保存边界脱敏由U0751保留。 |
| `tests/services/test_wuthering_waves_install.py::test_legacy_launcher_without_platform_selection_returns_none` | 不存在platform_ui_state时只断言helper返回None，未执行当前客户端定位；仅锁定第三方旧格式探测缺省，U0792保留旧启动器实际客户端解析。 |
| `tests/services/test_wuthering_waves_install.py::test_platform_selection_preserves_unbound_legacy_resources` | 用户确认M不保留。 |
| `tests/task/test_bettergi_execution_report.py::test_dispatcher_failure_overrides_done_and_keeps_next_step` | 按用户AH清理未核实上游契约的手工MAS_STEP成败判定。 |
| `tests/task/test_bettergi_execution_report.py::test_recoverable_error_is_not_a_terminal_failure` | 按用户AH清理未核实上游契约的手工MAS_STEP成败判定。 |
| `tests/task/test_bettergi_execution_report.py::test_terminal_failure_takes_priority_over_recoverable_error` | 按用户AH清理未核实上游契约的手工MAS_STEP成败判定。 |
| `tests/task/test_bettergi_execution_report.py::test_execution_failure_logs_name_builtin_and_custom_tasks` | 按用户AH清理未核实上游契约的手工MAS_STEP成败判定。 |
| `tests/task/test_bettergi_program_update.py::test_batch_download_failure_continues_without_rechecking` | 用户确认F不保留。 |
| `tests/task/test_builtin_registration.py::test_all_builtin_capabilities_and_lazy_factory_selection` | 复制 EXPECTED 注册清单并用 mock 构造器证明索引指向自己提供的对象，维护第二份实现清单；未执行专项实际可用行为。 |
| `tests/task/test_builtin_registration.py::test_builtin_config_and_restore_keep_different_priorities` | 人工构造 ZzzOdConfig、MaaEndConfig 多继承 Overlap；真实配置工厂不产生这种对象，不能把内部匹配优先级固化为合理用户流程。 |
| `tests/task/test_general_report_policy.py::test_typed_and_legacy_entries_render_identically` | 把同一渲染实现对 typed/legacy 两种内部表示的结果互相比，二者一起渲染为空也能通过；内部表示迁移不长期双轨兼容。 |
| `tests/task/test_legacy_callbacks.py::test_mode_mapping_lives_only_in_legacy_execution` | 仅检查 execution_mode 属性放在哪层和内部枚举映射、再直接改任务状态；没有执行设置会话或更新任务，不替代实际流程校对。 |
| `tests/task/test_log_capture_lifecycle.py::test_offset_concurrent_close_and_user_ownership` | 用户指出 AA 的“重复关闭”对用户意义不明，沿用不保留判断。 |
| `tests/task/test_log_capture_lifecycle.py::test_disabled_caller_does_not_read_or_compile` | 关闭采集后检查空结果和 _log_source/_log_pipeline 初值；没有外部读取探针，既不能证明不读取也不能证明不编译。 |
| `tests/task/test_m9a_login_mode.py::test_supports_account_switch_reads_login_mode` | 重复支持切号判据的布尔表；实际队列装饰 U0960/U0961 与整理 U0964 已观察任务是否下发。 |
| `tests/task/test_m9a_login_mode.py::test_only_account_switch_aborts_round` | 只确认 FLAVOR.abort_round_entries 容器中两个常量的成员关系，没有让切号失败并观察本轮是否中止；属于声明清单镜像。 |
| `tests/task/test_m9a_login_mode.py::test_login_hook_skips_in_project_mode` | Project 模式直接调用钩子返回空字符串；只固化空消息，不执行原生切号，未增加对 U0961 原生任务下发的功能证据。 |
| `tests/task/test_maa_activity_migration.py::test_unrelated_save_neither_fetches_stages_nor_changes_old_plans` | 改账号名后检查旧活动计划没变及没有请求；与用户 AC/B 的邻项表象相同，不在配置写入定位边界验证。 |
| `tests/task/test_maa_activity_migration.py::test_migration_keeps_the_existing_owned_cultivation_commit_guard` | 调用活动迁移却验证owned培养提交guard，是否稳定业务契约还是内部hook组合；需明确活动保存与培养目标自动补齐的用户操作绑定，避免两种功能偶然耦合。 |
| `tests/task/test_maa_fluxdown_update.py::test_package_mode_defaults_to_full_and_survives_config_projection` | 逐专项扫 PackageMode 默认值和 ConfigInput 字段投影；没有验证全量/增量选择结果。 |
| `tests/task/test_maa_version_download_budget.py::test_resource_same_version_or_backoff_never_requests_url` | 用户确认 O 不保留，未另述理由。 |
| `tests/task/test_maaend_hdr_restore.py::test_hdr_restore_without_resolution` | HDR恢复Task optionValues为上游特有字段，需核对版本支持与被上游实际执行的结果；仅参数生成未观察屏幕恢复，不能凭容器值自动保留。 |
| `tests/task/test_maaend_log_details.py::test_collection_failure_reaches_user_report` | 用户确认 U 不保留，未另述理由。 |
| `tests/task/test_maaend_program_update.py::test_missing_installation_path_survives_reload_for_crash_recovery` | 名字称 reload，但只 model_validate 一次并比较 Path，没有落盘重载或实际恢复。 |
| `tests/task/test_maafw_prefetch.py::test_prefetch_discovery_forwards_precheck_gate_before_url` | mock 掉整个详细发现逻辑，只检查返回对象身份和 precheck_gate 参数转发；不观察是否真的避免收费URL请求，不能守护所称故障。 |
| `tests/task/test_oknte_missing_paths.py::test_run_book_initialized_before_prepare` | 仅构造 OkNte 对象检查 run_book=False，与用户 AD 同义；没有执行 prepare 失败后的真实收尾。 |
| `tests/task/test_oknte_missing_paths.py::test_close_policy_is_independent_of_game_launch` | 关闭/重试策略本身有明确游戏进程损失，但当前测试只调两个私有bool函数；是否已有真实finalizer/retry关闭目标覆盖需进一步交叉核对，不因函数唯一就保留。 |
| `tests/task/test_okww_arguments_preview.py::test_preview_respects_native_switch_mode` | 预览实际输出以 build_custom_arguments 当前实现计算预期；只确认生成参数和内部 native 标记，未观察预览/启动功能差异。 |
| `tests/task/test_okww_batch_lifecycle.py::test_batch_timeout_preserves_per_account_budget` | 批量账号总预算倍乘有合理用户契约，但当前只检查property数值；若预算未用于真实timeout仍通过。 |
| `tests/task/test_okww_plan.py::test_plan_api_saves_only_selected_day` | 用户认为修改周一再检查周二只验证表象；若周二变化，应核查写盘定位和前后端对应关系，而不是为相邻业务对象增加检查。 |
| `tests/task/test_okww_plan.py::test_numeric_inheritance_is_not_coerced_to_default` | 只模型验证 None 后仍为 None；真实继承/False/空列表处理已由 U1287 运行 task_config 验证。 |
| `tests/task/test_okww_plan.py::test_custom_start_arguments_are_not_daily_plan_fields` | 前半重复固定配置取值，后半复制模型字段排除清单；未执行启动与日常计划的不同入口，不再固化字段表。 |
| `tests/task/test_okww_push_log_rules.py::test_traceback_source_line_no_longer_infers_skip` | 给孤立 traceback 源码行并期待“成功”来证明不推断跳过，缺少上游完成信号仍锁定成功，属于把缺失判据固化为正确的风险。 |
| `tests/task/test_okww_run_book_init.py::test_run_book_initialized_before_prepare` | 用户确认 AD 不保留：应抽象为各专项的公共测试。 |
| `tests/task/test_universal_plan.py::test_saved_days_and_user_base_are_isolated` | 用户确认 AC 不保留：写盘漂移应在负责写入定位的边界验证，不做修改一项再检查邻项的表象测试；重合覆盖应合并或抽象精简。 |
| `tests/task/test_universal_plan.py::test_universal_plan_general_only` | 只复制 PLAN_BOOK 类型与账号 PlanMode 默认值；计划能否被选择与保存应由真实计划入口验证，字段/索引初值本身收益不足。 |
| `tests/task/test_whimbox_update.py::test_access_lock_excludes_same_installation` | 手工嵌套同一安装锁验证互斥，没有构造两个真实更新/运行会话；U1406 仍执行真实 manager 主任务并观察锁释放，公共安装互斥不在专项重复演示。 |
| `tests/task/test_zzzod_log_box_session.py::test_mapping_is_copied_before_worker_reads` | 用户确认 V 不保留，未另述理由。 |
| `tests/utils/test_asyncio_compat.py::test_tls_client_diagnostic_classifies_inner_protocol` | 构造 SSLProtocol 调私有诊断函数并固定整句分类文案，不观察连接是否释放或故障是否可诊断；U1511/U1512 已执行连接清理。 |
| `tests/utils/test_asyncio_compat.py::test_non_windows_keeps_original_cleanup` | 只 monkeypatch sys.platform 后比较方法身份；Windows 专用安装分支的源码形状断言，无真实非Windows连接行为或资源损失。 |

## 归并明细

保留目标中的原有有效场景，并迁入来源用例的独有输入或断言；未用重复函数改名来替代覆盖。

| 原来源测试 | 保留目标 |
| --- | --- |
| `frontend/electron/services/runtimeBinaryCapabilities.test.ts::本地版本更高时依据实际 exe 能力，不依据线上目标猜测` | `frontend/electron/services/runtimeBinaryCapabilities.test.ts::残留备份的能力不能覆盖当前 exe：当前支持=%s` |
| `frontend/electron/services/runtimeInitializationService.test.ts::依赖段重试走 dependencies sync` | `frontend/electron/services/runtimeInitializationService.test.ts::依赖重试发现 Python 缺失时先修复 Python，再恢复依赖` |
| `frontend/electron/services/runtimeInitializationService.test.ts::运行环境普通重试重新准备整套环境，而不只检查 uv` | `frontend/electron/services/runtimeInitializationService.test.ts::实际普通 Python 重试在已知支持能力时仍完整准备` |
| `frontend/src/utils/initializationDecision.test.ts::未提供错误码时仍尊重不可重试结果` | `frontend/src/utils/initializationDecision.test.ts::不可重试结果 %# 不提供重试入口` |
| `frontend/src/views/EditView/User/components/useOkwwCustomArguments.test.ts::restores the enabled switch when disabling fails to save` | `frontend/src/views/EditView/User/components/useOkwwCustomArguments.test.ts::restores the previous draft and switch when enabled=%s fails to save` |
| `frontend/src/views/Initialization/useInitializationFlow.test.ts::preserves legacy, unknown, diagnostic and failed messages verbatim` | `frontend/src/views/Initialization/useInitializationFlow.test.ts::reinstalls a missing Runtime after a failure from %s, keeping failed downloads retryable` |
| `tests/core/test_task_state_changes.py::test_rollback_keeps_emitted_process_notice_but_query_reads_live_tree` | `tests/core/test_task_log_updates.py::test_append_after_process_state_rollback_replaces_sent_baseline` |
| `tests/models/test_queue_config.py::QueueConfigStartupModeMigrationTest.test_load_migrates_disabled_legacy_startup_setting` | `tests/models/test_queue_config.py::QueueConfigStartupModeMigrationTest.test_load_migrates_legacy_startup_setting` |
| `tests/models/test_queue_config.py::QueueConfigStartupModeMigrationTest.test_load_prefers_current_startup_mode_over_legacy_setting` | `tests/models/test_queue_config.py::QueueConfigStartupModeMigrationTest.test_load_migrates_legacy_startup_setting` |
| `tests/scripts/test_changelog_script.py::test_unreleased_is_only_allowed_at_the_top` | `tests/scripts/test_changelog_script.py::test_invalid_changelog_is_rejected` |
| `tests/scripts/test_changelog_script.py::test_duplicate_entry_is_rejected` | `tests/scripts/test_changelog_script.py::test_invalid_changelog_is_rejected` |
| `tests/scripts/test_changelog_script.py::test_free_text_line_is_rejected` | `tests/scripts/test_changelog_script.py::test_invalid_changelog_is_rejected` |
| `tests/scripts/test_changelog_script.py::test_comment_inside_a_version_section_is_rejected` | `tests/scripts/test_changelog_script.py::test_invalid_changelog_is_rejected` |
| `tests/scripts/test_changelog_script.py::test_indented_entry_is_rejected` | `tests/scripts/test_changelog_script.py::test_invalid_changelog_is_rejected` |
| `tests/scripts/test_changelog_script.py::test_fragment_malformed_header_line_is_named_instead_of_missing_project` | `tests/scripts/test_changelog_script.py::test_invalid_fragment_is_rejected` |
| `tests/scripts/test_changelog_script.py::test_fragment_text_limit_is_inclusive` | `tests/scripts/test_changelog_script.py::test_fragment_name_decides_category_and_body_is_one_line` |
| `tests/scripts/test_changelog_script.py::test_release_note_first_line_keeps_project_pr_numbers_and_author` | `tests/scripts/test_changelog_script.py::test_release_note_has_contract_first_line_contributors_and_compare_link` |
| `tests/task/test_hsr_update_before_run.py::test_prefetch_cancel_after_partial_builtin_download_removes_private_directory` | `tests/task/test_hsr_update_before_run.py::test_cancelled_builtin_prefetch_removes_private_partial` |
| `tests/task/test_hsr_update_before_run.py::test_prefetch_failure_cleans_only_when_downloader_releases_ownership` | `tests/task/test_hsr_update_before_run.py::test_hsr_prefetch_failure_releases_only_owned_files` |
| `tests/task/test_hsr_update_before_run.py::test_prefetch_digest_failure_reclaims_private_directory` | `tests/task/test_hsr_update_before_run.py::test_hsr_prefetch_digest_failure_cleans_package` |
| `tests/task/test_m9a_login_flow.py::test_alternating_title_and_empty_frames_do_not_succeed` | `tests/task/test_m9a_login_flow.py::test_unconfirmed_title_frames_do_not_declare_success` |
| `tests/task/test_m9a_login_flow.py::test_welcome_banner_confirms_handover` | `tests/task/test_m9a_login_flow.py::test_title_frames_confirm_handover` |
| `tests/task/test_m9a_login_flow.py::test_title_logo_fragment_confirms_handover` | `tests/task/test_m9a_login_flow.py::test_title_frames_confirm_handover` |
| `tests/task/test_m9a_login_flow.py::test_title_logo_full_word_confirms_handover` | `tests/task/test_m9a_login_flow.py::test_title_frames_confirm_handover` |
| `tests/task/test_m9a_login_flow.py::test_mas_login_rejects_official_resource` | `tests/task/test_m9a_login_flow.py::test_mas_login_rejects_other_servers` |
| `tests/task/test_m9a_login_flow.py::test_mas_login_rejects_other_server_resource` | `tests/task/test_m9a_login_flow.py::test_mas_login_rejects_other_servers` |
| `tests/task/test_maa_avd_shim.py::test_package_shim_missing_gets_ours` | `tests/task/test_maa_avd_shim.py::test_package_shim_selection` |
| `tests/task/test_maa_avd_shim.py::test_older_package_gets_ours` | `tests/task/test_maa_avd_shim.py::test_package_shim_selection` |
| `tests/task/test_okww_push_log_rules.py::test_failure_rules_cover_chinese_and_english_logs` | `tests/task/test_okww_push_log_rules.py::test_node_rules_cover_chinese_and_english_logs` |
| `tests/task/test_whimbox_autoproxy.py::test_upstream_verdict_retries_only_when_reason_changes` | `tests/task/test_whimbox_autoproxy.py::test_retry_follows_upstream_verdict` |
| `tests/task/test_whimbox_autoproxy.py::test_no_retry_for_environment_fatal_and_success` | `tests/task/test_whimbox_autoproxy.py::test_retry_follows_upstream_verdict` |
| `tests/test_main_port.py::ResolveHttpPortTest.test_production_keeps_legacy_port` | `tests/test_main_port.py::ResolveHttpPortTest.test_default_port_follows_application_environment` |
| `tests/tools/test_bluearchive_activity.py::TestHasRunningActivityIn.test_end_boundary_does_not_count_as_running` | `tests/tools/test_bluearchive_activity.py::TestHasRunningActivityIn.test_activity_time_boundaries` |
| `tests/tools/test_skland_response.py::SklandResponseTest.test_duplicate_message_remains_compatible` | `tests/tools/test_skland_response.py::test_already_signed_responses` |
| `tests/tools/test_skland_response.py::SklandResponseTest.test_english_duplicate_message_remains_compatible` | `tests/tools/test_skland_response.py::test_already_signed_responses` |
| `tests/utils/test_mumu_json_parse.py::test_status_starting_when_launch_reports_error` | `tests/utils/test_mumu_json_parse.py::test_status_respects_player_state_and_launch_failure` |
| `tests/utils/test_mumu_json_parse.py::test_status_starting_before_player_state_finishes` | `tests/utils/test_mumu_json_parse.py::test_status_respects_player_state_and_launch_failure` |
| `tests/utils/test_mumu_json_parse.py::test_status_offline_ignores_leftover_player_state` | `tests/utils/test_mumu_json_parse.py::test_status_respects_player_state_and_launch_failure` |

## 后端未通过节点

清理前后的正式全量检查均使用工作树内独立的 `--basetemp`。以下34个节点在两次全量检查中均失败，本轮保留：

```text
tests/core/test_queue_execution.py::test_extra_script_failure_warns_and_continues_normal_task
tests/core/test_queue_execution.py::test_queue_actions_use_accepted_snapshot_after_queue_is_deleted[NoAction]
tests/core/test_queue_execution.py::test_queue_actions_use_accepted_snapshot_after_queue_is_deleted[Sleep]
tests/core/test_queue_execution.py::test_stop_cancels_queue_script_without_scheduling_power[after]
tests/core/test_queue_execution.py::test_stop_cancels_queue_script_without_scheduling_power[before]
tests/task/test_bettergi_program_update.py::test_manager_starts_config_session_with_real_runtime_tree
tests/task/test_legacy_config_wait.py::test_src_captures_latest_path_after_config_lock
tests/task/test_maa_config_directory.py::test_folder_follows_maa_source_without_changing_config[False-native]
tests/task/test_maa_config_directory.py::test_folder_follows_maa_source_without_changing_config[True-native]
tests/task/test_maa_fluxdown_update.py::test_existing_channel_is_migrated_once[beta]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[annihilation-stops]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[completed-cultivation-budget]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[cultivation-recovery]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[daily-limit]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[data-update-recovery]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[failed-paused-cultivation]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[mixed-depot]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[mixed-event-depot]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[mixed-fight]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[native-queue]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[runtime-paused-cultivation]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[sanity-only]
tests/task/test_maa_retry.py::test_task_failure_retry_scope[source-queue]
tests/task/test_maa_wait_logs.py::test_install_write_wait_is_published_before_config_lock
tests/task/test_okww_game_update.py::test_client_only_auto_update_preserves_optional_launcher[True]
tests/task/test_okww_game_update.py::test_manual_update_allows_launcher_to_restore_missing_client
tests/task/test_okww_game_update.py::test_manual_update_checks_resolved_game_outside_launcher_tree
tests/task/test_okww_game_update.py::test_manual_update_uses_launcher_when_legacy_feed_is_unchanged
tests/task/test_okww_maintenance.py::test_login_maintenance_skips_proxy_without_retry[False]
tests/task/test_okww_maintenance.py::test_login_maintenance_skips_proxy_without_retry[True]
tests/task/test_script_pre_post_retry.py::test_hsr_before_after_scripts
tests/task/test_script_pre_post_retry.py::test_user_scripts_pair_on_terminal_failure[GeneralUserConfig]
tests/task/test_script_pre_post_retry.py::test_user_scripts_pair_on_terminal_failure[MaaUserConfig]
tests/task/test_script_pre_post_retry.py::test_user_scripts_pair_on_terminal_failure[SrcUserConfig]
```

清理后全量另一次失败如下，异常为目录换入时的 `PermissionError: [WinError 5]`；节点本身未修改，所在文件单独重跑23项全部通过：

```text
tests/task/test_maafw_prefetch.py::test_prefetched_manager_rechecks_source_after_same_version_reimport[False-False-False]
```
