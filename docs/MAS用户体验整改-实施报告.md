# MAS 用户体验整改 · 实施报告

对应审查报告：docs/MAS用户体验系统性审查与整改报告.md（基线 origin/dev @ d93c88054）。
本报告记录按该报告 §8 任务拆分落地的代码、验证证据与偏差；逐场景验收结论见 docs/MAS用户体验整改-验收记录.md。

## 1. 结论

报告的 9 项任务（PLATFORM-01/02、FRONTEND-01~05、BACKEND-01）全部落地，另补 FRONTEND-06（配置加载结果呈现，报告未列但属交付判据 6 的缺口）。
独立验收（QA-01）对报告 §10 的 18 条场景给出 13 pass / 5 部分通过 / 0 整条 fail；其提出的 6 条缺陷（2 高 / 1 中 / 3 低）已在本轮全部修复并回归。

## 2. 交付判据（报告 §12）对照

| 判据 | 落点 | 证据 |
| --- | --- | --- |
| 1 最终业务结果可查询 | `TaskOutcome` 契约 + GET /api/dispatch/task/{taskId} 返回 taskOutcome；POST /api/dispatch/stop 直接返回终态 | app/models/schema.py（TaskOutcome）、app/core/task_manager.py:1107-1198、app/api/dispatch.py:114-130 |
| 2 WS 断线不丢结果 | 发送失败的终态帧留存 + 重连补发；前端按 taskId+finishedAt 去重 | app/core/ws/publisher.py:38,57,90、app/api/core.py:MainConnection.on_connect(Publisher.replay_pending)、frontend/src/views/Scripts.vue:676-705、frontend/src/composables/useNativeGuiSession.ts:165-200 |
| 3 数据改变有明确去向 | 9 个 ScriptConfig 每条收尾路径登记 saved/discarded/completed_without_write；配置加载态不自动写回 | app/core/config_session.py、app/task/*/ScriptConfig.py、app/models/ConfigBase.py:1066-1290 |
| 4 失败有恢复动作 | 统一错误分类 → 恢复文案 + 可重试组件；队列/计划/历史/设置/签到页局部重试 | frontend/src/utils/appError.ts、frontend/src/components/RetryableErrorState.vue、frontend/src/views/{queue,plan,history,setting,gamesign} |
| 5 展示值能说明是否落盘 | 保存状态机 + 页面级/字段级指示 | frontend/src/utils/saveState.ts、frontend/src/composables/useSaveQueue.ts、frontend/src/components/{EditorSaveStatus,SaveStateIndicator}.vue |
| 6 自动修正/默认回退可见可追踪可恢复 | 加载报告接口 + 呈现面板（原值→新值+原因+时间、恢复时间、损坏副本路径） | app/api/setting.py（GET /api/setting/config-load）、frontend/src/components/ConfigLoadStatusPanel.vue、frontend/src/utils/configLoadReport.ts |
| 7 原生会话各入口语义一致 | 统一会话状态机（编辑/查看分离、停止后查终态、未知保留现场） | frontend/src/composables/useNativeGuiSession.ts、frontend/src/views/Scripts.vue、frontend/src/views/EditView/Script/OkwwScriptEdit.vue |
| 8 不跨脚本黑箱边界 | 只透传后端下发的丢弃原因，未读任何上游私有状态或私有格式 | frontend/src/utils/configSessionDiscard.ts（reason → 词条） |
| 9 P0/P1 有验收记录 | 独立验收记录 + 本轮缺陷修复 | docs/MAS用户体验整改-验收记录.md |

## 3. 实施清单

- PLATFORM-01 任务终态契约：app/models/schema.py（新增 TaskOutcome；TaskStatusOut.taskOutcome、WSTaskCompletedData.taskOutcome 向后兼容）、app/core/task_manager.py（`Task._build_task_outcome`，final_task 同一步留存终态再发 WS/回调）、app/api/dispatch.py（POST /stop 返回 TaskOutcome）。旧 WS 消息与 `TaskStatusOut.status` 未改，旧前端不受影响。
- PLATFORM-02 WS 结果补偿：app/core/ws/publisher.py（`_TERMINAL_TYPES`、`_retain`/`_prune`/`replay_pending`，仅留存发送失败的终态帧）、app/api/core.py（连接建立后补发）。
- PLATFORM-01b 原生配置会话终态登记：app/core/config_session.py（`note_config_session_result` / `take_config_session_result` / `publish_config_session_result`），app/task/{MAA,general,SRC,ZzzOd,OkNte,Okww,BetterGI,Whimbox,MaaEnd}/ScriptConfig.py 逐条收尾登记。
- BACKEND-01 配置加载可见性：app/models/ConfigBase.py（`ConfigLoadReport`/`NormalizationEvent`、load_status ∈ ok|empty|corrupt_recovered|unreadable|defaulted、损坏先留 `.corrupt-<ts>` 副本、加载态不自动写回、密文不可解不写回占位值）、app/models/schema.py、app/core/config.py、app/api/setting.py。
- FRONTEND-01 统一结果与错误：frontend/src/utils/{appError,saveState,pageDataState}.ts + 组件 {OperationStatusBanner,SaveStateIndicator,RetryableErrorState,ResultUnknownNotice,DiagnosticsDetails}.vue + i18n 三语。
- FRONTEND-02 统一原生会话：frontend/src/composables/useNativeGuiSession.ts 重写 + use{Bettergi,Oknte,Zzzod,Maa,MaaEnd,Okww}GuiSession.ts 收薄 + frontend/src/views/Scripts.vue。
- FRONTEND-03 保存与离开守卫：frontend/src/composables/{useSaveQueue,useUserApi,useEditorLeaveGuard}.ts、frontend/src/components/EditorSaveStatus.vue、12 个用户编辑页（MAA/MaaFW/SRC/MaaEnd/ok-ww/ok-nte/BetterGI/ZZZ-OD/Whimbox/HSR/General/BAAH）。
- FRONTEND-04 页面数据状态：frontend/src/views/queue/index.vue、frontend/src/views/plan/index.vue、frontend/src/views/history/{index.vue,useHistoryLogic.ts}。
- FRONTEND-05 模拟器/设置/通知/游戏社区：frontend/src/views/Emulator.vue、frontend/src/views/Emulator/Emulator2Panel.vue、frontend/src/views/setting/{index.vue,TabNotify.vue}、frontend/src/views/gamesign/{index.vue,TabGameSign.vue}。
- FRONTEND-06 配置加载结果呈现：frontend/src/components/ConfigLoadStatusPanel.vue、frontend/src/utils/configLoadReport.ts（挂到 frontend/src/views/setting/index.vue 高级设置）。
- 缺陷修复 D1–D6（本轮）：新增 frontend/src/utils/taskOutcomeNotice.ts（终态 → 提示的唯一映射，读不到终态一律 unknown）；frontend/src/views/EditView/User/{GeneralUserEdit,SRCUserEdit}.vue 改判 taskOutcome；frontend/src/views/EditView/Script/OkwwScriptEdit.vue 更新会话改判终态；frontend/src/services/websocket/types.ts 补 taskOutcome 字段；frontend/src/components/SaveStateIndicator.vue 补 role/aria-live；Scripts.vue 与 useNativeGuiSession.ts 补 taskId+finishedAt 显式去重；i18n 补 ja-JP 的 5 条丢弃词条与 en/ja 的 setting.notify.retryLoad。
- QA-01 验收矩阵：docs/MAS用户体验整改-验收记录.md（未新增长期功能测试；新增测试仅为最小可跑检查）。
- changelog 碎片：changelog.d/20261007-181610.fix.md（`fix scheduler`，一行 ≤50 字，符合 scripts/changelog.py 约定）。

## 4. 与报告规格的偏差（3 处）

1. 字段命名用 camelCase（taskId/outcome/reason/scope/dataPreserved/retryable/messageKey/finishedAt），报告 §0 JSON 的 snake_case 视为示意：与仓库既有 `TaskStatusOut.taskId/finishedAt`、前端生成模型与 i18n 保持同一风格，避免为契约单独加一层字段名转换。
2. `outcome` 枚举增加 `completed`：报告枚举（saved/discarded/failed/cancelled/completed_without_write/unknown）无法表达非配置类任务（更新、代理运行）的成功终态，否则这类任务只能落 unknown。
3. 报告 §5 建议错误类型落在 frontend/src/api/core/request.ts；该文件是 openapi 生成物（首行 `do not edit`，`yarn openapi` 整目录覆盖），落点改为 frontend/src/utils/appError.ts，导出名与语义不变。

## 5. 明确拒绝的伪整改（对应报告 §「必须拒绝」）

- 不新增裸 `message.error`：技术原文只进 AppRequestError.detail / DiagnosticsDetails / 日志，主文案走 error.kind.* 与 error.recovery.*。
- 不只订阅 WS_TASK_CONFIG_DISCARDED：另有终态查询（GET task/{taskId}）、停止接口直接返回终态、断线补发三层补偿。
- 不只看按钮 loading：EditorSaveStatus/SaveStateIndicator 展示 idle/dirty/saving/saved/failed_draft_kept/failed_reverted/rejected/discarded/unknown。
- 不前端单方面回滚：保存失败后是否回读旧值由后端结果与 useSaveQueue 状态决定，页面展示对应终态。
- 不做只加备份不报结果：备份路径与恢复时间在 ConfigLoadStatusPanel 中可见。
- 不复制多套结果判断：终态分类统一在 frontend/src/utils/taskOutcomeNotice.ts，后端合成统一在 `Task._build_task_outcome`。
- 不读第三方脚本私有状态：只透传后端下发的丢弃原因。

## 6. 验证记录（实跑命令与结果）

- 后端：`.venv\Scripts\python.exe -m pytest tests -q` → 9 failed / 435 passed / 4 skipped；9 条全部是既有失败 tests/core/test_notify.py（tests/core/test_notify.py:25 `assert group == "Info"` 与 app/core/notify_channels.py:548 `webhook.get("Data","Url")` 不一致，HEAD 即失败）。
- 后端定向：`pytest tests/models/test_config_base.py tests/models/test_config_load_status.py tests/core/test_config_session_result.py -q` → 33 passed。
- 后端静态：`ruff format --check` / `ruff check` 9 个改动文件全过。
- 前端类型：`yarn typecheck` → 仅 3 条错误，全部来自未跟踪 WIP frontend/src/views/scheduler/schedulerStartRequest.test.ts（15,7 / 18,20 / 28,7）。
- 前端静态：`yarn oxlint` → 0 warnings 0 errors（638 文件）；`yarn oxfmt --check` → 仅上述 WIP 文件。
- 前端测试：`npx vitest run` → 3 failed / 1395 passed（124 文件）；失败为上述 WIP 用例与 frontend/src/composables/useUpdateDownload.test.ts 的两条用例并行 5s 超时（单跑 7/7 通过）。
- 定向测试：`npx vitest run src/utils/taskOutcomeNotice.test.ts src/composables/useNativeGuiSession.test.ts src/i18n src/utils/configLoadReport.test.ts src/views/history/useHistoryLogic.test.ts` → 全通过（含本轮新增 taskOutcomeNotice 10 例）。
- 前端 API 生成物由生成器更新（临时脚本从 app.api 组装 FastAPI 后 `openapi-typescript-codegen`，未手改 frontend/src/api/**）：221 paths / 536 models，新增 TaskOutcome、ConfigLoad* 模型。

## 7. 未验证 / 未自动化

- 真机端到端：桌面 GUI 逐个专项的真实丢弃、断线补发、超时、外部程序未写出四类文案，需人工按验收记录 §5 的清单执行。
- 窄窗口/长路径/长错误不重叠、屏幕阅读器实读（D5 已补 role/aria-live，但未做读屏实机验证）。
- 英/日词条的人工语感复核（仅通过 locales.test.ts 的键集合与编译校验）。
- 工作区原本已有 PR #1251 方向的未提交改动（frontend/src/utils/configSessionDiscard.ts 及其测试、Scripts.vue/useNativeGuiSession.ts 的部分改动、3 个 changelog 碎片、schedulerStartRequest.test.ts）；本轮在其之上继续，未回滚，最终提交时需与该方向一起处理。

## 8. 已知基线失败（非本轮回归）

- frontend/src/views/scheduler/schedulerStartRequest.test.ts：3 条 typecheck 错误 + 1 条用例失败（未跟踪 WIP）。
- frontend/src/composables/useUpdateDownload.test.ts:72：全量并行下 5s 超时，单跑通过。
- tests/core/test_notify.py：9 条既有失败。
