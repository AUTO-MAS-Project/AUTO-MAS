# 案例：HSR 多引擎编排线

HSR 与其他专项的根本差别：**一个 `ScriptType` 编排两个互相独立的上游程序**（M7A 与 SRA），按任务模块逐个决定由哪个引擎执行。不要按「一个 ScriptType 对应一个外部程序」的心智读 HSR 代码。

任务模式只有 `AutoProxy` 与 `ManualReview`，**没有 `ScriptConfig.py`**。字段、路由、文件清单现场读 `app/task/HSR/` 与 `app/api/scripts.py` 确认。

## 单点声明不变量（最容易漂移的一处）

新增任务模块**只改 `task_mapping.py` 的 `HSR_TASK_MODULES`**：`HSRConfig` 的 `TaskMapping` 配置项、`check()` 的支持性校验、能力快照的 `tasks` 全从这里派生（`HSRConfig` 延迟导入该常量循环生成配置项）。

**手写平行分支会立刻漂移。** 同理，引擎增删时要同步 runner、`Literal["M7A","SRA"]` 声明、控制解析的引擎元组、以及备份清单——漏一处就静默失效。

## 引擎分配：四级回落，顺序不可颠倒

1. 用户级 `Managed.TaskMapping` 覆盖（字符串或对象都要容错解析）
2. 脚本级 `TaskMapping.<moduleKey>`
3. `module.default_script`
4. 按 `effective_engines` 收敛：分配到的引擎不可用时取 `supported_scripts` 中第一个可用

**每一级取到的值都必须过 `supported_scripts` 校验**，不在列表内视为未分配、继续回落。新增模块要确认这四级都有合理取值，**不要只加 `default_script`**。

## 外部配置接管（最容易出事的一面）

HSR 直接读写两个上游的真实配置文件。当前备份覆盖 M7A 的 `config.yaml` 与 SRA 的 `settings.json` / `cache.json` / `configs/`。

必守语义：

1. 备份清单是 `(label, source, backup, existed)` 四元组。**`existed=False` 的项在恢复阶段要删除任务期新增的路径，不是跳过。**
2. 恢复按逆序执行，每项独立捕获异常、最后汇总抛出，避免一个失败阻断其余恢复。
3. `final_task` 与 `on_crash` 共用同一套恢复逻辑；新增外部配置目标时两条路径都要能恢复。
4. **新增引擎或配置文件必须同步扩展备份清单——只写入不备份等于永久改坏用户的原生配置。**

## 并发保护

进程内路径锁按规范化路径键加锁：多个 HSR 脚本指向同一份安装时互斥，直控导入与运行中任务互斥。

冲突抛 `HSRExternalPathBusyError`，**API 层要转成可读错误，不要静默等待**。锁租约必须在 `final_task` / `on_crash` 释放。

## 直控

- **仅 `AutoProxy` 支持直控**，其他模式 `check()` 直接返回错误。
- 直控用户必须至少启用一个引擎开关。
- **直控默认直接使用脚本当前的原生配置**（SRA 把 `--inline run` 指向真实 profile，M7A 以真实安装根目录启动），零配置可跑，不复制、不建隔离目录——这就是 SKILL.md 里「直控＝直接使用外侧脚本原生配置，由原生 GUI 或上游入口维护」的落地。`check()` 要求 CLI/Assistant 可执行，且**没有快照的用户**还要求原生配置文件存在。
- 快照（`Direct.*Config` 加密内容 + `*ImportedAt` / `*Source` 元数据）是**可选覆盖**，只服务「一个脚本挂多个游戏账号、各 MAS 用户要跑不同计划」的场景。有快照时写进隔离目录运行，可脱离当前原生配置文件；快照冻结在导入那一刻，不跟随脚本里的后续改动，UI 上要能一键清掉退回活配置。**不要再把「必须先导入快照」写成直控的前置条件。**
- 普通用户配置 API 只返回非敏感元数据，**不返回加密快照内容**。

## 快速配置：明确不支持（方案 B）

**HSR 不支持快速配置**：SRA/M7A 的原生配置由脚本 GUI 维护，MAS 侧托管字段（每日关卡等）的写入深度耦合托管运行器（临时配置覆盖而非直接写原生文件），不存在可独立下发的快速配置子集，故 `Info.IfQuickConfig` 开关不产生任何行为差异，前端不渲染该开关（死开关；声明见 `app/task/HSR/tools/native_control.py` 的 `resolve_user_control`）。不要按普适承诺给 HSR 加快速配置面板，也不要在实现中把「直控+开启」与「直控+关闭」造出差异。

## 其他必守规则

- **关卡字段保持脚本原生形状**（SRA `id`+`level`，M7A `instance_type`+`name`），不引入 MAA 式统一关卡词表。
- **切号统一走 SRA StartGame**，M7A 模块也依赖该登录路径；不要为 M7A 另起切号实现。
- 完成态一律经 `CompletionWriteback` 在真实成功后写回，**不在模块执行中途直接改 `Data`**。
- 周期判定用 ISO 周字段 + 完成日期**双字段**，不靠日期差推算。
- 兑换码只存状态指纹，不存明文。
- 人工排查不接管任务模块执行，**不要把自动代理的模块编排逻辑复制进来**。
- 托管字段运行时动态渲染，**新增字段扩展后端字段定义，不在 Vue 里加分支**。
- 不新增 `ScriptConfig.py` 或原生编辑器遮罩会话，除非产品明确改变 HSR 的配置 owner 模型。

## 配置恢复接入要求

已接入通用配置恢复（mas/native 双池 + 字段侧车，无会话），机制见 [config-restore.md](config-restore.md)；后续改动**必须符合**：

- **mas 池是纯字段侧车（MAS 用户配置全量）**：HSR 无 per-user 目录，用户配置即字段——收录 Info（Mode 仅预览不回填，防静默翻转配置来源；Name/Status/Server/RemainedDay/前后脚本/Notes）、TaskSwitch 任务开关、Stage 副本配置（含原生关卡 JSON）、TaskOpt、Notify、Control 引擎开关、Managed.TaskMapping/Options（运行时物化进原生）、Direct 快照**元数据**（*ImportedAt/*Source）。侧车平铺键为 ``组.键``（Info.Mode 与 Control.Mode 历史同名，裸键会撞）。**不收录** Info.Id/Password 与 Direct 加密快照内容（凭据/密文不进侧车，Notify.ToAddress/ServerChanKey 回填但预览脱敏）、Data.* 运行统计、Notify.CustomWebhooks 子表；恢复 = 回填 UserData。
- **native 池按 SRA appdata 根 + M7A 安装根组合指纹分桶**：SRA appdata 是多脚本共享目录，必须 `config_root_key` 分桶跨脚本共享、不随脚本删除；M7A `config.yaml` 随 SRA 池一并归档——只按 SRA 分桶会把不同 M7A 安装的 config.yaml 混进同一历史，跨实例恢复会写错安装，故 key 为两根指纹组合（M7A 未配置时仅按 SRA）。目标按归档内相对键 `M7A/*`、`SRA/*` 写回，只覆盖归档内包含的文件。
- **归档时机与 MAA 同型**：任务启动（manager `prepare`）归档 native（运行会写托管字段、崩溃残留会污染原生）；编辑页进入归档 native（MAS 触碰前原始态）、退出归档 mas（编辑会话包络终态）。无遮罩会话，无 viewOnly 分支。
- **预览口径**：mas 分区行（MAS 独有 = 配置来源/服务器/脚本/直控引擎；任务配置 = 任务开关/副本；通知；托管配置 = 任务映射/覆盖；直控快照 = 导入元数据），native 反读归档内**常用字段**（词表固化、零本体运行时依赖，只收录 MAS 托管白名单概念内的键）——M7A config.yaml 平铺键（清体力/副本/历战余响/体力补充/领取奖励/差分宇宙/货币战争等，键名即 MAS patch 白名单）、SRA 档案每文件一节（键形为顶层 camelCase 段 + 段内平铺点号键，见 SRA `SRACore/models/tasks_config.py`，与 MAS `_build_sra_base_config` 同口径；奖励开关兼容索引式与命名键，顺序对齐 `managed_config.SRA_REWARD_LABELS`）；`settings.json`/`cache.json` 结构未经现场核实（后者为运行缓存）**不反读内容**。两池预览载荷都带标准 `files` 字段（§3.4 基座兜底），sections 不渲染文件清单节。新增引擎/配置文件要反读时，先按上游源码核实键形再进词表，不臆造。
- **新增引擎/配置文件必须同步扩展 `collect_native_files`**——只归档不恢复等于备份了个寂寞，只恢复不归档等于永久改坏用户的原生配置。

## 现状缺陷（别照抄，也别再加一处）

HSR 用户编辑 Section **同时存在于两处目录**（`views/EditView/User/HSRUserEdit/` 与 `views/HSRUserEdit/`）。这是现状不是规范——新增 Section 先确认相邻文件在哪一处，**不要制造第三处**。

## 审查清单

- [ ] 新增/改动模块在 `HSR_TASK_MODULES` 声明了 `supported_scripts` 与 `default_script`
- [ ] 四级回落都能取到合法引擎，每级过 `supported_scripts` 校验
- [ ] `check()` 覆盖引擎路径缺失、exe 缺失、模块分配非法、直控前置条件
- [ ] 直控仅在 `AutoProxy` 可用，且要求至少一个引擎开关
- [ ] HSR 不支持快速配置：未给 HSR 加快速配置面板/开关，`Info.IfQuickConfig` 无运行时消费
- [ ] 备份清单覆盖本次改动涉及的所有原生配置文件
- [ ] `existed=False` 的目标在恢复阶段被清理而非跳过
- [ ] `final_task` 与 `on_crash` 都恢复外部配置并释放路径锁
- [ ] 路径锁冲突转成可读错误，未静默等待
- [ ] 模块结果状态与 reason 能解释每个模块的最终结果
- [ ] 完成态经 `CompletionWriteback` 写回，未在执行中途改 `Data`
- [ ] 加密字段未经 API 明文外泄
- [ ] 新增托管字段走后端定义，未在 Vue 加硬编码分支
- [ ] 用户编辑 Section 未新增第三处目录
- [ ] 能力快照的 `effective_engines` 与实际可执行引擎一致
