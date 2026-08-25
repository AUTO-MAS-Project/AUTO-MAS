# 案例：HSR 多引擎编排线

本案例描述当前 `dev` 的 HSR 实现。HSR 与其他专项的根本差别是：**一个 `ScriptType` 编排两个互相独立的上游程序**（March7th Assistant 与 SRA），按任务模块逐个决定由哪个引擎执行。不要按「一个 ScriptType 对应一个外部程序」的心智去读 HSR 代码。

## 架构事实

| 维度 | 当前实现 |
| --- | --- |
| 上游形态 | 两个独立发行物：M7A（`March7th Assistant.exe`）与 SRA（`SRA-cli.exe`），各自有原生配置 |
| 任务模式 | `METHOD_BOOK` 只有 `AutoProxy` 与 `ManualReview`；**没有 `ScriptConfig`**，也没有 `ScriptConfig.py` |
| 模块注册 | `app/task/HSR/task_mapping.py` 的 `HSR_TASK_MODULES`：`Daily`、`ReceiveRewards`、`DivergentUniverse`、`CurrencyWars` |
| 引擎分配 | 每模块声明 `supported_scripts` 与 `default_script`，由 `get_assigned_script()` 三级回落 |
| 配置项生成 | `HSRConfig` 延迟导入 `HSR_TASK_MODULES`，循环生成 `TaskMapping_<key>` `ConfigItem` |
| 能力协商 | `HSRCapabilitiesData` 快照（`candidate_engines` / `configured_engines` / `effective_engines` / `adapters` / `tasks` / `warnings`） |
| 用户配置来源 | `Control.Mode` = `managed` / `direct`，外加 `Control.SRA`、`Control.M7A` 两个引擎开关 |
| 原生配置接管 | 任务前备份 M7A/SRA 真实配置，任务后原子恢复；缺失项在恢复阶段被清理 |
| 并发保护 | `tools/external_locks.py` 进程内路径锁，冲突抛 `HSRExternalPathBusyError` |
| 关卡字段 | `Stage.ScriptStage`、`Stage.ScriptEchoOfWar` 直接存**脚本原生字段 JSON**，不做 MAS 统一关卡词表 |
| 登录与切号 | `HSRLoginPlan` 的 `sra_switch` / `sra_remembered` / `m7a_fallback`；切号统一走 SRA StartGame |
| 周期状态 | `Data.*` 记录 ISO 周（形如 `2025-W23`）与完成日期，仅在真实成功后写回 |
| 游戏控制 | `Game.Enabled` 总开关；`Game.ForceResolution1920x1080` 临时覆盖注册表分辨率 |

## 引擎分配的三级回落

`get_assigned_script()` 的优先级不可颠倒：

1. 用户级 `Managed.TaskMapping` JSON 覆盖（字符串或对象都要容错解析）。
2. 脚本级 `TaskMapping.<moduleKey>`。
3. `module.default_script`。
4. 最后按 `effective_engines` 收敛：分配到的引擎不可用时，取该模块 `supported_scripts` 中第一个可用引擎。

任何一级取到的值都必须过 `module.supported_scripts` 校验；不在支持列表内视为未分配，继续回落。新增模块时同步确认这四级都有合理取值，不要只加 `default_script`。

## 关键调用链

### 自动代理

1. `HSRManager.check()`：校验模式在 `METHOD_BOOK` 内、脚本配置类型为 `HSRConfig`、至少配置一个引擎路径、每个模块的分配引擎在 `supported_scripts` 内、对应 exe 存在、用户可执行性与直控前置条件。
2. `HSRManager.prepare()`：锁定脚本配置、获取外部路径锁、`_backup_external_configs()` 备份原生配置。
3. `HSRManager.main_task()`：按用户遍历，`managed` 走 `HSRAutoProxyTask`，`direct` 走 `_run_direct_user()`。
4. 模块级执行结果收敛为 `HSRModuleResult`（`completed` / `failed` / `incomplete` / `skipped` + `reason`），用于调度台日志与通知汇总。
5. `final_task()` / `on_crash()`：`_apply_completion_writebacks()` 写回完成态、恢复外部配置、释放路径锁、解锁脚本配置、清理独立进程。

### 人工排查

`HSRManualReviewTask` 通过 SRA StartGame 切号，按 `Game.Enabled` 管理游戏启停，产出 `Data.IfPassCheck`（未通过时用户标签显示「人工排查未通过」）。人工排查不接管任务模块执行，不要把自动代理的模块编排逻辑复制进来。

### 直控

- 仅 `AutoProxy` 支持直控；`check()` 在其他模式下直接返回错误。
- 直控用户必须至少启用一个引擎开关，否则 `check()` 拦截。
- `Direct.SRAConfig` / `Direct.M7AConfig` 是 `EncryptValidator` 加密快照，配套 `*ImportedAt` / `*Source` 元数据。
- 已导入快照可脱离当前原生配置文件运行，`check()` 只要求 CLI/Assistant 可执行，避免原生配置器改名误阻断直控。
- 导入入口是 `POST /api/scripts/hsr/direct-config/import`，同样受外部路径锁保护。

## 外部配置接管

HSR 直接读写两个上游程序的真实配置文件，这是它最容易出事的一面。

`_backup_external_configs()` 当前覆盖：

```text
M7A:  <M7APath>/config.yaml
SRA:  <SRA AppData>/settings.json
      <SRA AppData>/cache.json
      <SRA AppData>/configs/
```

必须遵守的语义：

1. 备份清单是 `(label, source, backup, existed)` 四元组。`existed=False` 的项在恢复阶段要**删除任务期新增的路径**，不是跳过。
2. 恢复按 `reversed(targets)` 逆序执行，每项独立捕获异常，最后汇总抛出，避免一个失败阻断其余恢复。
3. 恢复完成后清理 `temp_path/ExternalConfig`，`temp_path` 空目录一并移除。
4. `final_task` 与 `on_crash` 共用同一套恢复逻辑；新增外部配置目标时两条路径都要能恢复。
5. 新增引擎或新增配置文件时必须同步扩展备份清单。只写入不备份等于永久改坏用户的原生配置。

## 并发保护

`tools/external_locks.py` 维护进程内 `dict[str, asyncio.Lock]`，按规范化后的路径键加锁：

- 多个 HSR 脚本指向同一份 M7A/SRA 安装时，互斥。
- 直控配置导入与正在运行的任务互斥。
- 冲突抛 `HSRExternalPathBusyError`，API 层需转成可读错误，不要静默等待。
- 锁租约 `HSRExternalPathLockLease` 必须在 `final_task` / `on_crash` 里通过 `_release_external_path_lock()` 释放。

## API 表面

| 路由 | 用途 |
| --- | --- |
| `GET /api/scripts/hsr/capabilities` | 内置 HSR 能力快照；不暴露原生编辑器会话 |
| `GET /api/scripts/hsr/stage-options` | 体力副本动态选项（按引擎解析原生资源） |
| `GET /api/scripts/hsr/managed-config` | 托管模式动态字段定义 |
| `POST /api/scripts/hsr/direct-config/import` | 导入原生配置快照 |

四条路由都带 `tags=["HSR"]`。能力/字段类响应用 `BaseModel` + `OutBase` 包装（`HSRCapabilitiesOut`、`HSRManagedConfigOut`、`HSRStageOptionsOut`、`HSRDirectConfigImportOut`）。普通用户配置 API 只返回直控的非敏感元数据，不返回加密快照内容。

## 前端表面

| 位置 | 内容 |
| --- | --- |
| `views/EditView/Script/HSRScriptEdit.vue` | 脚本级：双引擎路径、游戏、Run 限制、`TaskMapping` |
| `views/EditView/User/HSRUserEdit.vue` | 用户级主页面 |
| `views/EditView/User/HSRUserEdit/` | `DirectControlSection.vue`、`ManagedTaskSection.vue`、`DynamicManagedFields.vue` |
| `views/HSRUserEdit/` | `StageConfigSection.vue`、`capabilityView.ts`、`types.ts` |
| `composables/useHSRPluginApi.ts` | 能力快照、关卡选项、托管字段、直控导入；含 `filterHSRCapabilityWarnings` |
| `router/index.ts` | `hsr` 片段：`HSRScriptEdit` / `HSRUserAdd` / `HSRUserEdit` |

**注意目录分裂**：HSR 的用户编辑 Section 同时存在于 `views/EditView/User/HSRUserEdit/` 与 `views/HSRUserEdit/` 两处。这是现状不是规范；新增 Section 时先确认相邻文件放在哪一处，不要再制造第三处。

托管字段是**运行时动态渲染**的：`DynamicManagedFields.vue` 按 `HSRManagedField` 的 `type` / `options` 渲染，不是逐字段硬编码表单。新增托管字段优先扩展后端字段定义，而不是在 Vue 里加分支。

## 配置字段

### 脚本配置（`HSRConfig`）

- `Info.M7APath`、`Info.SRAPath`（各自 `FolderValidator`，可只配一个）
- `Game.Enabled`、`Game.Path`、`Game.Arguments`、`Game.WaitTime`
- `Game.ForceResolution1920x1080`、`Game.RedeemCodesOnlyWhenChanged`
- `Run.RunTimesLimit`、`Run.DailyTimeLimit`、`Run.WeeklyTimeLimit`
- `Run.LowPerformanceMode`（仅 M7A 差分宇宙，映射 `weekly_divergent_stable_mode`）
- `TaskMapping.<moduleKey>`（由 `HSR_TASK_MODULES` 循环生成，`OptionsValidator(supported_scripts)`）

### 用户配置（`HSRUserConfig`）

- `Info.Id` / `Info.Password`：`EncryptValidator`
- `TaskSwitch.Daily` / `ReceiveRewards` / `DivergentUniverse` / `CurrencyWars`
- `Stage.Channel`、`Stage.ScriptStage`、`Stage.ScriptEchoOfWar`
- `TaskOpt.EchoOfWarWeekday`
- `Control.Mode` / `Control.SRA` / `Control.M7A`
- `Managed.TaskMapping` / `Managed.Options`（均 `JSONValidator`）
- `Direct.{SRA,M7A}Config` / `*ImportedAt` / `*Source`
- `Data.EchoOfWar*`、`Data.Weekly*`、`Data.{SRA,M7A}RedeemCodeFingerprint`

`Data.*RedeemCodeFingerprint` 只存状态指纹，不存兑换码明文。`Game.RedeemCodesOnlyWhenChanged` 依赖这个指纹判断是否需要执行兑换。

## 实现规范（HSR 必遵守）

- 新增任务模块只改 `HSR_TASK_MODULES`：`HSRConfig` 的 `TaskMapping` 项、`check()` 的支持性校验、能力快照的 `tasks` 都从这里派生。手写平行分支会立刻漂移。
- 引擎新增/删除时同步 `HSRScriptRunner`、`HSRCapability*` 的 `Literal["M7A", "SRA"]`、`resolve_user_control()` 的引擎元组和备份清单。
- 关卡字段保持脚本原生形状（SRA `id`+`level`，M7A `instance_type`+`name`）。不要引入 MAA 式统一关卡词表。
- 切号统一走 SRA StartGame；M7A 模块也依赖该登录路径，不要为 M7A 另起切号实现。
- 完成态一律经 `CompletionWriteback` 在真实成功后写回，不在模块执行中途直接改 `Data`。
- 周期判定使用 ISO 周字段 + 完成日期双字段，不要只靠日期差推算。
- 不新增 `ScriptConfig.py` 或原生编辑器遮罩会话，除非产品明确改变 HSR 的配置 owner 模型。
- 不手改 `frontend/src/api/**`。

## 审查清单

- [ ] 新增/改动的模块在 `HSR_TASK_MODULES` 中声明了 `supported_scripts` 与 `default_script`
- [ ] `get_assigned_script()` 四级回落都能取到合法引擎
- [ ] `check()` 覆盖引擎路径缺失、exe 缺失、模块分配非法、直控前置条件
- [ ] 直控仅在 `AutoProxy` 可用，且要求至少一个引擎开关
- [ ] 外部配置备份清单覆盖本次改动涉及的所有原生配置文件
- [ ] `existed=False` 的目标在恢复阶段被清理而非跳过
- [ ] `final_task` 与 `on_crash` 都恢复外部配置并释放路径锁
- [ ] 路径锁冲突转成可读错误，未静默等待
- [ ] `HSRModuleResult` 状态与 `reason` 能解释每个模块的最终结果
- [ ] 完成态经 `CompletionWriteback` 写回，未在执行中途改 `Data`
- [ ] 加密字段（`Info.Id`/`Password`、`Direct.*Config`）未经 API 明文外泄
- [ ] 新增托管字段走后端字段定义，未在 `DynamicManagedFields.vue` 加硬编码分支
- [ ] 用户编辑 Section 未新增第三处目录
- [ ] 能力快照的 `effective_engines` 与实际可执行引擎一致

## 最小验证

按仓库根目录的 [`tests/AGENTS.md`](../../../../tests/AGENTS.md) 选择受影响的最小测试。当前 HSR 的专项测试入口是 `tests/task/test_hsr_direct_control_result.py`；改动直控结果收敛时至少运行该文件。前端改动时只运行实际存在且受影响的 `*.test.ts`。
