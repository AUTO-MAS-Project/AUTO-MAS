# MAS 用户体验整改 · 独立验收记录

- 验收人：qa-verify（QA-01，共享任务 task-7）
- 验收对象：本轮未提交的工作区改动（PLATFORM-01 / PLATFORM-01b / PLATFORM-02 / BACKEND-01 / FRONTEND-01..05）
- 依据：`docs/MAS用户体验系统性审查与整改报告.md` 第 10 节（10.1 P0 / 10.2 P1 / 10.3 P2-P3）
- 声明：验收期间**未修改任何实现文件**（app/**、frontend/src/** 只读），本文件是唯一写入。所有"pass"均附文件:行或真实命令输出；无证据的一律写"未自动化验证"。
- 方法：源码路径逐行核对 + 后端运行期脚本（stdin 传入，未落盘）+ 既有/新增最小测试实跑。**未做真机桌面 GUI/WS 端到端**，也未跑全量 vitest（由 Lead 统一跑，避免并行 flake）。
- 后续：本记录是**验收当时的快照**；其 §3 列出的 D1–D6 已在本轮修复并回归，修复落点与证据见 [MAS用户体验整改-实施报告.md](MAS用户体验整改-实施报告.md) §3 与 §6。

## 0. 已知基线（验收时已排除，非本轮回归）

| 项 | 位置 | 说明 |
| --- | --- | --- |
| typecheck 3 条错误 | frontend/src/views/scheduler/schedulerStartRequest.test.ts(15,7) TS2554 / (18,20) TS2339 / (28,7) TS2554 | 未跟踪 WIP，HEAD 即存在；`yarn typecheck` 退出码 1 只由这 3 条产生 |
| 并行 vitest 偶发超时 | frontend/src/composables/useUpdateDownload.test.ts | 单文件通过，既有 flake |
| 后端 9 个失败 | tests/core/test_notify.py（app/core/notify_channels.py:548 读 `"Data"`，tests/core/test_notify.py:25 的 `_Webhook.get` 只认 `group=="Info"`） | HEAD 与工作区均无人改动 |

## 1. 结论汇总

| 章节 | 条目数 | pass | 部分通过 | fail |
| --- | --- | --- | --- | --- |
| 10.1 P0 | 5 | 3（P0-2 / P0-4 / P0-5） | 2（P0-1 / P0-3，因 D1–D3 的页面级 fail） | 0 整条 fail |
| 10.2 P1 | 8 | 8 | 0 | 0 |
| 10.3 P2-P3 | 5 | 2（P2-1 / P2-5） | 3（P2-2 / P2-3 / P2-4） | 0 |
| 合计 | 18 | 13 | 5 | 0 |

**缺陷：6 条（高 2 / 中 1 / 低 3），集中在"旧页面 WS 完成处理器仍只看 legacy outcome"**（D1–D3），以及 i18n 缺词条（D4）、读屏（D5）、无显式终态去重（D6）。

## 2. 验收矩阵

### 2.1 10.1 P0

**P0-1 配置丢弃：打开原生配置 → 改任务结构 → 保存 → 显示"改动未写入 + 原因 + 下一步"，不显示保存成功 —— 部分通过**

- 终态契约：app/models/schema.py:6158 `class TaskOutcome(OutBase)`（outcome ∈ saved|discarded|failed|cancelled|completed|completed_without_write|unknown）；app/models/schema.py:6207 `TaskStatusOut.taskOutcome`；app/models/schema.py:6221 `WSTaskCompletedData.taskOutcome`。
- 判定：app/core/task_manager.py:1107 `Task._build_task_outcome`；scope=="native_config" 时 app/core/task_manager.py:1136 `take_config_session_result(task_id)`；kind=="discarded" → outcome="discarded" + messageKey 映射 app/core/task_manager.py:1147-1160（structure → `edit.configSessionDiscardedStructure`、unreadable → `…Unreadable`、not_written → `…NotWritten`，未知 reason → `taskOutcome.discarded`）；读不到登记且非 view_only → `unknown` / `config_session_result_missing` / dataPreserved=False（app/core/task_manager.py:1180-1189），**绝不默认成 saved**。
- 登记：app/core/config_session.py:43 `note_config_session_result`、:66 `publish_config_session_result`（discarded → Publisher.send(TASK_CONFIG_DISCARDED)，失败仅 warning，app/core/config_session.py:88-96）；结构变化登记见 app/task/MAA/ScriptConfig.py:437-444。
- 前端：frontend/src/composables/useNativeGuiSession.ts:181-187（DISCARDED → `resetSession()` + state='discarded' + `showDiscardWarning(reason)`，不弹成功）；frontend/src/utils/configSessionDiscard.ts:14-38（reason → i18n key；`Modal.warning` 渲染原因与下一步，role="alert"）；frontend/src/views/Scripts.vue:673-704 同构。
- 运行期矩阵证据：脚本直接调 `Task._build_task_outcome` 12 条全部符合设计，其中 `discarded structure/unreadable/not_written` → outcome=discarded + 对应 messageKey。
- **缺口（fail 场景）**：从 GeneralUserEdit / SRCUserEdit 发起的原生配置会话不走统一路径，仍会弹成功提示，见 D1 / D2。

**P0-2 断线丢弃：保存前断 WS → 后端完成任务 → 恢复连接 → 页面补齐最终结果 —— pass（代码路径 + 运行期脚本，未做真机断线）**

- 留存：app/core/ws/publisher.py:38 `_TERMINAL_TYPES = frozenset({TASK_COMPLETED, TASK_CONFIG_DISCARDED})`；:81-88 仅当 `send()` 返回 False 时 `_retain(id, type, message)`，送达成功则 `_pending.pop(f"{id}|{type}")`；:40-41 `_RETAIN_MAX=200` / `_RETAIN_TTL_SECONDS=1800`；:90-99 `replay_pending()` 重发成功才 pop；:102 同键去重；:112 `_prune()` 按 TTL。
- 触发点：app/api/core.py:129 `MainConnection.on_connect(Publisher.replay_pending)`；app/core/ws/manager.py:69 追加 hook、:117-119 `_run_connect_hooks(generation)`。
- 前端兜底：frontend/src/composables/useNativeGuiSession.ts:147-158 `fetchOutcome` 重试 5×300ms（`OUTCOME_QUERY_ATTEMPTS=5` / `OUTCOME_QUERY_RETRY_MS=300`）；HTTP 查询端点 app/api/dispatch.py GET `/api/dispatch/task/{taskId}`（app/core/task_manager.py:1379 `get_task_status`，_recent_results TTL 1800s、上限 200，app/core/task_manager.py:109-110）；订阅表 frontend/src/services/websocket/subscriptions.ts 为 module 级 Map，不随断线清空 → 重连后补发帧仍能路由。
- 运行期证据（monkeypatch `app.core.ws.publisher.MainConnection`）：send 返回 False 的 task.completed 被留存（_pending=1，key `"t1|task.completed"`）；同 key 二次留存去重且保留最新 data；TASK_NOTICE 不留存；TASK_CONFIG_DISCARDED 也留存；send 恢复 True 后 `replay_pending()` 清空 _pending；TTL 过期被 `_prune()` 丢弃；插入 205 条后 `len(_pending)==200`。
- 去重：**没有 taskId+finishedAt 显式去重**，见 D6（幂等来自"终态后 taskId 置空 + 退订"，非显式判重）。

**P0-3 停止 HTTP 成功但业务失败：stop 返回成功、终态 discarded/failed —— 部分通过**

- 后端：app/api/dispatch.py:110-151 `stop_task` —— 有 taskOutcome 直接返回（133-135）；`taskId=="ALL"` → outcome="cancelled"（136-142）；找不到任务 → `TaskOutcome(code=404, status="error", outcome="unknown", dataPreserved=False)`，**HTTP 仍 200**（143-151）；异常 → code=500 / outcome="unknown"（124-131）。`_exit_result` 赋值点：app/core/task_manager.py:398/405-409/422-424。
- 前端统一路径：frontend/src/composables/useNativeGuiSession.ts:246-269 `runStop`（`response.code !== 200` → `enterUnknown` + return false，256-261；HTTP 200 也等 300ms `DISCARD_FRAME_GRACE_MS` 再 `applyOutcome`，262-264）；:164-207 `applyOutcome`：SAVED→success（仅在 announceSaved 时）、DISCARDED→丢弃告警、FAILED→`message.error(t('taskOutcome.failed'))`（189-194）、COMPLETED_WITHOUT_WRITE→state='discarded'（196-203）、cancelled/completed→静默（205-207）。frontend/src/views/Scripts.vue:673-704 同样只按 taskOutcome 分派。
- **fail 场景（D1–D3）**：GeneralUserEdit.vue:661-680、SRCUserEdit.vue:673-682、OkwwScriptEdit.vue:800-805 的 `task.completed` 处理器仍按 legacy `data.outcome === 'success'`（或无条件）弹成功，忽略 `data.taskOutcome`。由于 app/core/task_manager.py:1222 的 legacy `outcome` 仍取 `self._exit_result`（discarded 会话正常退出 → "success"），这些页面会在业务失败/未写入时显示成功。

**P0-4 从 /scripts 打开每个支持的专项，成功/丢弃/失败/超时文案一致 —— pass（有 i18n 缺口，见 D4）**

- 单一分派点：frontend/src/views/Scripts.vue:673-704 `applyTaskOutcome`（UNKNOWN → 保留现场；SAVED → `message.success(connection.savedMessage)`；DISCARDED → `showConfigDiscardWarning`，用 `discardWarned` 去重；FAILED → `message.error(t('taskOutcome.failed'))`；COMPLETED_WITHOUT_WRITE → `message.info`；cancelled/completed → 静默）。
- 超时/未知：frontend/src/views/Scripts.vue:662-670 `enterUnknownState`（保留连接可查询）+ frontend/src/components/ResultUnknownNotice.vue（`resultUnknown.title` / 查询按钮）；文案键在 zh-CN/en-US/ja-JP 均存在。
- 丢弃原因文案统一由 frontend/src/utils/configSessionDiscard.ts:14-19 的同一组键渲染（useNativeGuiSession.ts:124 与 Scripts.vue:691 共用）。

**P0-5 重复点击：连续点保存/停止只允许一个有效请求 —— pass**

- 停止：frontend/src/composables/useNativeGuiSession.ts:275-281 `stoppingPromise` 复用；frontend/src/views/Scripts.vue:731-734 `activeConnections.has(targetId)` 直接拦截并提示、:824 `settling` 短路、:816-848 `connection.stopPromise` 复用 → 只发一次。
- 保存：frontend/src/composables/useSaveQueue.ts:132-143（同 key 已有排队项时 `pending.exec = exec` 覆盖，只保留最后一次 + settlers 追加）。
- 未逐一核对旧页面（GeneralUserEdit/SRCUserEdit）自身 stop 按钮的幂等实现（这些页面本轮只加了保存侧 `EditorSaveStatus`/`useEditorLeaveGuard`）→ 该子项**未自动化验证**。

### 2.2 10.2 P1

| 项 | 结论 | 证据 |
| --- | --- | --- |
| 快速连续编辑最后值必保存 | pass | frontend/src/composables/useSaveQueue.ts:132-143；:89-91 state=running?'saving':queueLength>0?'dirty':lastOutcome |
| 保存失败显示草稿保留或回滚（与后端真值一致） | pass | frontend/src/composables/useSaveQueue.ts:33-38 `UNRESOLVED_STATES`、:46-60 `classifySaveError`（网络类 → unknown，禁止显示为已保存）；frontend/src/views/MAAUserEdit/useMAAFieldSave.ts:17-24 `failureOutcome`、:63-89 `reconcileField` 回读后端真值（失败保留输入）、:99-119（`save()` 返回 false → 造 Error，不再把异常记成 saved） |
| 任意导航离开触发保护 | pass | 12/12 页三口：11 页 frontend/src/views/EditView/User/{BAAHUserEdit.vue:733, ZzzOdUserEdit.vue:2899, WhimboxUserEdit.vue:521, BetterGIUserEdit.vue:4713, GeneralUserEdit.vue:942, MaaEndUserEdit.vue:966, HSRUserEdit.vue:1152, OkwwUserEdit.vue:555, OkNteUserEdit.vue:545, SRCUserEdit.vue:604} + useMaaFWUserPage.ts:338；第 12 页 frontend/src/views/MAAUserEdit/useMAAEditorLifecycle.ts:153/154/162-173（beforeunload 判定 `hasPendingEdits`，由 frontend/src/views/EditView/User/MAAUserEdit.vue:1302-1303 提供）；守卫本体 frontend/src/composables/useEditorLeaveGuard.ts:34-75 |
| 队列/计划网络失败不显示假空 | pass | frontend/src/views/queue/index.vue:458-466（`error_with_previous_data` / `error_without_data`，保留旧列表）、模板 :87/:53/:75；frontend/src/views/plan/index.vue:662-670、:38/:60/:72；frontend/src/views/history/useHistoryLogic.ts:145-153（searchState）、frontend/src/views/history/index.vue:29/:45；状态枚举 frontend/src/utils/pageDataState.ts:6-13 |
| 配置 JSON 损坏不直接覆盖原文件 | pass | app/models/ConfigBase.py:145-187（JSONDecodeError/非 dict → `shutil.copyfile` 到 `<原名>.corrupt-<YYYYmmdd-HHMMSS>`，status="corrupt_recovered"）；app/models/ConfigBase.py:1128-1131 `_allow_auto_commit`、:1221-1231 加载时只 warning 不写回；测试实跑通过（`test_corrupt_json_is_not_overwritten_and_backup_is_queryable`，tests/models/test_config_load_status.py:64-84，断言原文件逐字保留 + backup 名 + 内容一致） |
| 密文不可解不静默写回占位值 | pass | app/models/ConfigBase.py:433-435 `UNREADABLE_SECRET_PLACEHOLDER`；:922-963 `setValue`（密文结构正确但本机解不开 → 只记 `last_correction`，不改 self.value；`looks_like_dpapi_blob` 原样存）；:984-1007 `getValue`（`if_decrypt=False` 返回原密文）；测试实跑通过（`test_unreadable_secret_is_never_replaced_on_disk`，tests/models/test_config_load_status.py:123-149，断言磁盘密文逐字保留、占位不落盘） |
| 非法枚举纠正可见前后值 | pass | app/models/ConfigBase.py:62-79 `NormalizationEvent`（field/oldValue/newValue/reason/time）、:124-142、:1235-1248（有纠正事件 → status="defaulted"）；端点 app/api/setting.py:131-149 GET `/api/setting/config-load`；测试实跑通过（`test_invalid_enum_correction_exposes_old_and_new_value`，tests/models/test_config_load_status.py:86-106，断言 oldValue=="z" / newValue=="a"）；前端展示 frontend/src/components/ConfigLoadStatusPanel.vue:52-70 |
| 恢复后页面重新读取并显示恢复时间 | pass | 后端 app/models/ConfigBase.py:114-121 `_file_mtime_text`（注释：恢复备份会覆盖文件，该时间即恢复时间）+ 测试 `test_file_time_follows_restore`（tests/models/test_config_load_status.py:151-164，`os.utime` 后 report["fileTime"]==恢复时间）；前端 frontend/src/components/ConfigLoadStatusPanel.vue:40-47 渲染 `fileTime`/`backupPath`，挂载于 frontend/src/views/setting/index.vue:453，取数 frontend/src/api/services/GetService.ts:963（url `/api/setting/config-load`）；映射 frontend/src/utils/configLoadReport.ts + 测试 frontend/src/utils/configLoadReport.test.ts（实跑 5 passed） |

### 2.3 10.3 P2-P3

| 项 | 结论 | 证据 |
| --- | --- | --- |
| 技术错误不作主文案且诊断可复制 | pass | frontend/src/utils/appError.ts:187-229（`buildDetail` 拼 HTTP 状态码/传输码/url/message/JSON(body)；技术原文只进 `detail` 与 `console.error('[appError]', …)`）；主文案按 `error.kind.*`（frontend/src/components/RetryableErrorState.vue `KIND_KEYS`）；frontend/src/components/DiagnosticsDetails.vue:69-70 + `navigator.clipboard.writeText` 复制按钮；实跑 src/utils/appError.test.ts 等通过 |
| 中英日词条语义一致 | 部分通过 | 缺词条见 D4；已有自动化 frontend/src/i18n/locales.test.ts（127 行，7 用例，含"源码里用到的 key 在中文词表里都有"）；本轮新增键在 zh/en/ja 多数齐全（`retryAction`/`copyDiagnostics`/`diagnostics`/`taskOutcome`/`saveState`/`resultUnknown`/`configLoad`） |
| 窄窗口/长路径/长错误不重叠 | 部分通过（布局未自动化） | frontend/src/components/DiagnosticsDetails.vue:69-70 `white-space: pre-wrap` + `word-break: break-all`；frontend/src/components/ConfigLoadStatusPanel.vue:172-174 `word-break: break-all`；其余（OperationStatusBanner/RetryableErrorState/ResultUnknownNotice）依赖 ant-design-vue Alert 自身换行。**无任何布局/窄窗自动化测试 → 未自动化验证** |
| 屏幕阅读器能读加载/错误/成功 | 部分通过 | a-alert 渲染 `role="alert"`（frontend/node_modules/ant-design-vue/es/alert/index.js:179）→ OperationStatusBanner / RetryableErrorState / ResultUnknownNotice 有可访问告警；frontend/src/utils/configSessionDiscard.ts:26 显式 role="alert"。**缺**：frontend/src/components/SaveStateIndicator.vue 与 frontend/src/components/EditorSaveStatus.vue 用 a-tag，无 role/aria-live → 保存状态变化不被播报（D5）。**未自动化验证** |
| 后台轮询失败不每 10 秒弹 Toast | pass | frontend/src/views/Emulator/Emulator2Panel.vue:150-199 `loadDevices({silent})`：silent 分支只 `loadError.value`/`logger.error`（167-173、191-195），不弹 Toast，且只 `mergeStatus`/`mergeSettings` 不整表替换（177-187）；frontend/src/views/Emulator.vue:943-948 用 OperationStatusBanner + retryable `@retry="pollDevices"` |

## 3. 缺陷清单（按严重度）

### D1（高）GeneralUserEdit 的 WS 完成处理器忽略 taskOutcome，丢弃/未写入仍弹"通用配置完成"

- 位置：frontend/src/views/EditView/User/GeneralUserEdit.vue:661-680（判定在 :665 `if (data.outcome === 'success' && !generalSessionViewOnly.value)`，成功提示在 :666 `message.success(t('edit.configurationUserP0Done', …))`；随后 :669-673 退订并清 `generalTaskId`）。
- 后端依据：app/core/task_manager.py:1222 legacy `outcome=self._exit_result`，discarded 会话正常退出即 "success"；而 `taskOutcome` 在 :1225 同时下发。
- 复现：从 /general 用户配置页发起原生配置会话，让收尾落 discarded（例如目标配置文件不存在 → app/task/general/ScriptConfig.py:215-222 登记 discarded "not_written"），任务完成后页面仍弹"配置完成"。
- 影响：P0-1 / P0-3 假成功。

### D2（高）SRCUserEdit 同类问题

- 位置：frontend/src/views/EditView/User/SRCUserEdit.vue:673-682（:676 `if (data.outcome === 'success' && !viewOnly)` → :677 `message.success`）。
- 复现：SRC 会话在 `mas_config_dir` 为空（app/task/SRC/ScriptConfig.py:322-330 登记 completed_without_write "direct_control"）或 kill 失败（app/task/SRC/ScriptConfig.py:293-299 登记 discarded "not_written"）收尾时，非 view_only 会话仍弹成功。

### D3（中）OkwwScriptEdit 的 task.completed 无条件弹成功

- 位置：frontend/src/views/EditView/Script/OkwwScriptEdit.vue:800-805（:801 `message.success(t('edit.wutheringWavesUpdateTask'))`，不看 `data.outcome` 也不看 `data.taskOutcome`）。
- 该任务为 `mode: TaskCreateIn.mode.UPDATE`（frontend/src/views/EditView/Script/OkwwScriptEdit.vue:778），`_exit_result=="error"` 时 `taskOutcome.outcome=="failed"` 且仍会发 task.completed → 与 :791-798 的 error toast 并存，最后一条提示是"更新完成"。

### D4（低）i18n 缺词条

- ja-JP 完全没有 5 个 `edit.configSessionDiscarded*`（zh-CN.ts:2290-2297、en-US.ts:2414-2421 有；ja-JP.ts grep 0 命中）→ 日文用户看到英文回退文案。
- en-US 与 ja-JP 都没有 `setting.notify.retryLoad`（zh-CN.ts:4464，被 frontend/src/views/setting/TabNotify.vue:205 使用）→ 英/日文界面出现中文"重试"。

### D5（低）保存状态指示无读屏支持

- frontend/src/components/SaveStateIndicator.vue、frontend/src/components/EditorSaveStatus.vue 用 a-tag 且无 `role`/`aria-live`；对照 ant-design-vue Alert 有 `role="alert"`（frontend/node_modules/ant-design-vue/es/alert/index.js:179）。保存成功/失败切换不会被读屏播报。

### D6（低）没有显式 taskId+finishedAt 去重

- 现状：frontend/src/composables/useNativeGuiSession.ts:211-226 `settleOnTaskEnd` 以 `const id = taskId.value; if (!id) return` 短路（终态后 `resetSession()` 置空 taskId），进入 confirming/stopping 时也 return；frontend/src/views/Scripts.vue:633-647 `clearConfigSession` 退订；frontend/src/composables/useTaskRuntimeState.ts:202 `releaseTaskSubscriptions(taskId)`。全仓 grep 无按 `finishedAt` 的判重。
- 风险窗口：app/core/ws/manager.py:132-165 发送超时（timeout=5.0）注释明说"帧已进缓冲区、之后仍可能送达…只能记为未确认送达"→ 返回 False → 帧被留存 → 重连补发；若首帧其实已送达，就会重复投递同一 task.completed。
- 实测影响：当前各订阅者在首帧处理时即退订/清 taskId，重复帧无接收者，**未能复现出重复提示**；但该幂等是隐式的——新增的订阅者若不在收尾时退订，就会重复提示。建议后续补 `taskId+finishedAt` 判重。

### 观察项（不计缺陷）

- app/core/config_session.py:40 `_PENDING` 无 TTL/上限（对比 publisher 有 `_RETAIN_MAX`/`_RETAIN_TTL_SECONDS`）。当 ScriptConfig 的内层 `final_task` 抛异常（如 app/task/OkNte/ScriptConfig.py:191-198、app/task/Okww/ScriptConfig.py:157-163 先 publish discarded 再 raise）时，外层 app/core/task_manager.py:1127 因 `_exit_result=="error"` 先返回 failed，登记不会被 take → 该 task_id 的登记常驻内存（量级极小，不影响用户可见结果）。
- app/task/general/ScriptConfig.py:233-253 与 app/task/OkNte/ScriptConfig.py:191-220 在 `ConfigPathMode` 既非 "Folder" 也非 "File" 时不复制仍登记 saved；但 app/models/schema.py:2440/2576 `Optional[Literal["File","Folder"]]`、app/models/config.py:4172-4173/4364-4365 `OptionsValidator(["File","Folder"])`、app/core/config.py:566-571 迁移归一 → 判为不可达，未记缺陷。

## 4. 已知缺口与未自动化验证清单

1. **无真机端到端**：未在真实桌面 GUI + 真实 WS 断线场景跑 P0-1/P0-2/P0-3 全流程；结论基于源码路径 + 运行期脚本（`_build_task_outcome` 12 行矩阵、Publisher 留存/补发 8 项断言）+ 单测。
2. **未跑全量 vitest / 全量 pytest**（按约定由 Lead 跑全量 vitest）；本次实跑的验证见第 5 节命令。
3. **未自动化验证**：窄窗口/长路径布局（P2-3）、读屏播报（P2-4）、旧页面 stop 幂等（P0-5 子项）、12 编辑页保存态在真实浏览器中的呈现。
4. **前端渲染未逐页截图核对**：Scripts.vue 与 ConfigLoadStatusPanel 的文案渲染仅到"键存在 + 组件绑定"层面。
5. tests/ 新增（tests/core/test_config_session_result.py、tests/models/test_config_load_status.py 与前端 *.test.ts）按 tests/AGENTS.md 默认不提交，留在工作区。

> 补充说明（2026-10-07）：本轮已补做真实浏览器 + 本地后端的 E2E。仍未宣称覆盖
> Electron 原生窗口、真实游戏客户端或人为断开 WebSocket；这些边界在下节单独列出。

## 5. 实跑命令与真实输出

1. `.venv\Scripts\python.exe -m pytest tests/core/test_config_session_result.py tests/models/test_config_load_status.py -q`
   → `........ [100%]` / **8 passed in 4.09s**
2. 后端终态矩阵脚本（stdin 传入 `.venv` python，未落盘）：12 行全部符合设计（含 discarded 三 reason 的 messageKey、无登记非 view_only → unknown/config_session_result_missing/dataPreserved=False）。
3. Publisher 留存/补发脚本（monkeypatch `app.core.ws.publisher.MainConnection`）：留存/同键去重/非终态不留存/`replay_pending` 清空/TTL 裁剪/上限 200 全部符合。
4. `npx vitest run`（frontend 目录）
   - src/utils/{appError,saveState,configSessionDiscard}.test.ts + src/composables/{useEditorLeaveGuard,useNativeGuiSession,useSaveQueue}.test.ts + src/views/MAAUserEdit/useMAAFieldSave.test.ts + src/views/history/useHistoryLogic.test.ts → **Test Files 8 passed (8) / Tests 48 passed (48)**，2.83s
   - src/views/EditView/User/MaaFWUserEdit/{useMaaFWUserPage,useMaaFWUserSaveStatus}.test.ts + src/views/EditView/MaaFWFlavor/MaaFWFlavorPages.test.ts → **3 passed / 24 passed**（仅 `[Vue warn] Failed to resolve component: a-spin/a-modal/a-segmented`）
   - src/i18n/{locales,index,status}.test.ts → **3 passed / 15 passed**
   - src/utils/configLoadReport.test.ts → **1 passed / 5 passed**
5. `yarn typecheck`（frontend 目录，exit code 1）→ 仅 3 条错误，全部落在已知基线未跟踪 WIP 文件 frontend/src/views/scheduler/schedulerStartRequest.test.ts(15,7)/(18,20)/(28,7)；**本轮新增/改动代码无类型错误**。

## 6. 真实 E2E 记录（2026-10-07）

### 6.1 环境与启动

| 项目 | 记录 |
| --- | --- |
| 分支基线 | `codex/mas-ux-e2e`，创建自 `origin/dev` `9626c0785` |
| 启动命令 | `frontend`: `yarn dev:fullstack` |
| Vite | `http://127.0.0.1:5173/`，启动成功 |
| 后端 | `http://127.0.0.1:36164/`，OpenAPI HEAD 200，WebSocket `ws://127.0.0.1:36164/api/core/ws` 为 `open` |
| 浏览器 | Codex In-app Browser，本地页面 `http://127.0.0.1:5173/#/` |
| Electron 限制 | `electron-dev:wait` 子进程退出码 `2147483651`，未打开原生窗口；随后直接用浏览器加载同一 Vite 前端和同一后端完成 E2E，不把该限制写成通过 |

### 6.2 流程与结果

| 编号 | 操作 | 观察到的结果 | 判定 |
| --- | --- | --- | --- |
| E2E-01 | 打开首页，等待后端和 WebSocket 初始化 | 首页显示 `v5.6.2`、后端运行中、WS open；没有空白页或初始化阻塞 | PASS |
| E2E-02 | 首次公告点击「我知道了」，随后调用确认接口并刷新页面 | `POST /api/info/notice/confirm` 返回 `code=200`；刷新后公告不再重复拦截首页 | PASS |
| E2E-03 | 进入「托管管理」→「新建托管」 | 页面显示脚本类型搜索、通用/MFW/专项分组，`通用脚本` 默认可选，按钮根据步骤从「下一步」切换为「创建并配置」 | PASS |
| E2E-04 | 选择「通用脚本」→「自定义配置」→「创建并配置」 | 成功进入通用脚本编辑页；必填路径、日志格式、配置来源等控件均可见，未出现假成功或空白页 | PASS |
| E2E-05 | 修改「托管名称」为 `E2E 临时通用脚本`，点击「返回」 | 返回托管管理后，卡片立即显示同名脚本；改动没有被静默吞掉，列表数据与编辑输入一致 | PASS |
| E2E-06 | 进入「测试路由」与「遮罩彩蛋测试」 | 两个路由均能打开；遮罩测试页显示当前时间、触发状态和可执行按钮 | PASS |
| E2E-07 | 保存结果截图 | 已在本轮浏览器工具记录中捕获托管管理页截图：卡片显示 `E2E 临时通用脚本`、类型 `General`、编辑/添加账号/更多操作 | PASS |

### 6.3 失败与边界记录

1. `yarn dev:fullstack` 的 Vite 和后端均正常，只有 Electron wrapper 子进程以 `2147483651` 退出；这不是前端页面通过的依据，已改用同端口浏览器执行并保留该失败记录。
2. 浏览器开发 shim 产生以下已知警告：`getRuntimeLaunchMode is not a function`、`windowIsMaximized is not a function`、Ant Design `Modal.mask` prop 警告。它们不影响上述页面操作，但不能据此宣称 Electron 主进程能力已通过。
3. 后端定向 pytest 本轮首次因 Windows 临时目录不可写而无法启动；改用明确临时目录后进程长时间无输出并已中止，故不把该命令记为通过。前端终态相关 Vitest 仍为 **2 files / 17 tests passed**。
4. 本次创建的 `E2E 临时通用脚本` 是本地验收数据，不作为长期测试夹具；提交前不纳入仓库测试文件，也不把运行时生成目录纳入 PR。
5. `yarn build` 两次均完成 5921 个模块转换后，在 Vite/esbuild 清理临时目录阶段报 Windows `Access is denied`；不是源码转换或类型错误，故记为环境阻断而非通过。
