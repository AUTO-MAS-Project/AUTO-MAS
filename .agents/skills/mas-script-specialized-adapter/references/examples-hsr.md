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

第一级读的是**计划对象**（见下节）上的 `Managed.TaskMapping`：脚本态传进来的是脚本配置，它那份 `Managed.TaskMapping` 恒为空，自然落到第二级——脚本态不允许用户级引擎覆盖，靠的就是这一点，不要另加守卫。

## 配置来源：单轴三态，决定计划 owner

- 唯一的模式轴是 `Info.Mode`。插件版遗留的 `Control.Mode`（managed/direct）已删除，`HSRUserConfig.load()` 读**原始字典**把 `Control.Mode=direct` 迁成「直控」；`Control` 组只剩直控引擎开关 `SRA` / `M7A`。
- **计划** = `TaskSwitch` / `Stage` / `TaskOpt` / `Managed`，由 `declare_hsr_plan_items` 单点声明，`HSRUserConfig` 与 `HSRConfig` 组名、键名、默认值完全相同。脚本态读脚本配置上的共享计划（本脚本下所有脚本来源用户共用），用户态读用户自己的那份；`Info` / `Data` / `Notify` / `Control` 恒按用户。
- 运行时用 `native_control.resolve_plan(user_config, script_config)` 取计划对象。**读计划键传 `plan`，读其余键传 `user_cfg`，不混用**：`ConfigBase.get` 对不存在的项抛 `AttributeError`，而 `HSRConfig.Info.Name` 是脚本名——拿脚本配置读用户键要么炸、要么静默读错。混读的函数（队列构建、历战余响开始日、货币战争开拓者名）加 `plan` 参数，不要整个换掉 `user_cfg`。
- `/hsr/managed-config` 响应的 `plan_owner`（`script` / `user`）告诉前端表单保存到脚本配置还是用户配置；脚本级 `Managed.TaskMapping` 不在 `HSRConfig` schema 里开放。

## 外部配置接管（最容易出事的一面）

HSR 直接读写两个上游的真实配置文件。当前备份覆盖 M7A 的 `config.yaml` 与 SRA 的 `settings.json` / `cache.json` / `configs/`。

必守语义：

1. 备份清单是 `(label, source, backup, existed)` 四元组。**`existed=False` 的项在恢复阶段要删除任务期新增的路径，不是跳过。**
2. 恢复按逆序执行，每项独立捕获异常、最后汇总抛出，避免一个失败阻断其余恢复。
3. `final_task` 与 `on_crash` 共用同一套恢复逻辑；新增外部配置目标时两条路径都要能恢复。
4. **新增引擎或配置文件必须同步扩展备份清单——只写入不备份等于永久改坏用户的原生配置。**

## 并发保护

进程内路径锁按规范化路径键加锁：多个 HSR 脚本指向同一份安装时互斥，手动更新外部脚本与运行中任务互斥。

冲突抛 `HSRExternalPathBusyError`，**API 层要转成可读错误，不要静默等待**。锁租约必须在 `final_task` / `on_crash` 释放。

## 直控

- **仅 `AutoProxy` 支持直控**，其他模式 `check()` 直接返回错误。
- 跑哪几个引擎由 `Control.SRA` / `Control.M7A` 决定；一个都没勾时回落到已配置路径的引擎，不报错。
- **直控直接使用脚本当前的原生配置**（SRA 把 `--inline run` 指向真实 profile，M7A 以真实安装根目录启动），零配置可跑，不复制、不建隔离目录——这就是 SKILL.md 里「直控＝直接使用外侧脚本原生配置，由原生 GUI 或上游入口维护」的落地。`check()` 一律要求 CLI/Assistant 可执行且原生配置文件存在。
- 直控快照（`Direct.*`、导入 / 清除接口、隔离目录）**已删除**：「一个脚本挂多个账号、各跑不同计划」由用户态承担（每用户一份计划叠在活配置上），不要再加回第二套机制。存量记录里的 `Direct.*` 加载即忽略、下次保存即丢弃。

## 云模式契约（`Game.Platform = Cloud`）

云·星穹铁道没有本地客户端：**浏览器归 MAS，游戏自动化归三月七**。浏览器托管在 `tools/cloud_browser.py`，平台分叉集中在 `tools/account_switch.py`（`resolve_game_platform` / `is_cloud_platform`）。

- **MAS 托管浏览器**：用三月七发行包自带的 Chrome for Testing（版本取 `3rdparty/WebBrowser/chrome/win64/` 下唯一目录名，不写死）拉起独立 `chrome.exe`，**每个 MAS 用户一份 `--user-data-dir`**（`data/{script_id}/{user_id}/cloud-profile`，相对后端 cwd）。登录态就是这份 profile 里的 cookie；多账号靠 profile 隔离，不靠账号密码。新 profile 由 MAS 预写 `Preferences`（剪贴板 / keyboard_lock 权限）并经 CDP 注入 `initial_local_storage.json` 与自动战斗开关——这三件三月七只在「新建浏览器」路径做，连接路径跳过。
- **三月七走「连接已有浏览器」路径的五个硬条件**，缺一条它就会自己新建浏览器（用它写死的 profile，多账号失效）或连不上：
  1. 进程名在三月七的集合里——用包内 `chrome.exe`；
  2. argv 里有**独立元素** `--march-7th-assistant-sr-cloud-game`；
  3. 无窗口属性一致——不加 `--headless=new`，patch `browser_headless_enable: False` + env `MARCH7TH_BROWSER_HEADLESS_ENABLE=false`；
  4. `browser_debug_port` 等于本轮浏览器的调试端口——**patch 必须在浏览器就绪之后写**，端口从当前用户的 `CloudBrowser` 取；
  5. chromedriver 与 Chrome 同版本——两者都取自同一个三月七包，钉 `browser_type: integrated` + env `MARCH7TH_BROWSER_TYPE=integrated`。
  另外 `--user-data-dir` 不能省：新版 Chromium 对默认 profile 忽略 `--remote-debugging-port`。
- **云只用三月七**：SRA 只会新建自己的浏览器，接不上 MAS 的。`resolve_script_assignment` 在云平台直接返回三月七，用户 / 脚本 `TaskMapping` 与四级回落都不参与；SRA 直控在 `check()` 报错；SRA 路径有没有都不影响云（外部脚本更新照常）。不要为云加 SRA 分支。
- **平台钉扎两处一致**：环境变量（`build_platform_m7a_env`，托管与直控共用，优先于 config.yaml）与 config.yaml patch（`build_platform_m7a_patch`，叠在每个模块 patch 最后）。客户端平台也要钉 `MARCH7TH_CLOUD_GAME_ENABLE=false` / `cloud_game_enable: False`。**patch 的所有新键都要进 `M7A_PLATFORM_PATCH_WHITELIST`**，否则 `merge_whitelist` 静默丢弃。直控不写用户配置：只钉环境变量，浏览器开在用户 config.yaml 自己的 `browser_debug_port` 上，被占就报错。
- **生命周期**：任一时刻只有一个 MAS 云浏览器（三月七找浏览器只认标记不认账号）。用户开始 = 关上一个用户的、起本用户的（`prepare_game_for_account_switch`，登录计划 `cloud` 按切号处理）；**同一用户的模块之间不关**（下一个三月七进程连回去已在游戏里，不重新排队）；每个三月七模块开跑前查存活，三月七启动失败路径会按标记杀掉浏览器，死了就重起，连续两次起不来判不可重试；任务结束 `close_game_if_needed` 按 pid 关并按命令行标记兜底清理本脚本的残留。云平台不注册 `StarRail.exe` 存活检测、不碰分辨率注册表与游戏路径。
- **三月七自建浏览器必须拦下**：三月七的启动重试遇异常会先 `stop_game()` 杀掉所有带标记的浏览器，重试时找不到就自建（日志 `正在启动 {browser_type} 浏览器`），自建的不在 MAS 的按用户 profile 里。三层兜底：patch 钉 `browser_persistent_enable: False`（自建只能用临时 profile，不落到它按安装目录共享的 `UserProfile`；连接路径不受影响）；输出回调见到那行立刻终止三月七、按普通可重试失败补跑、本轮不写 LastLogin；起浏览器前与收尾时清掉带标记且 profile 在三月七 `UserProfile` 下或没有 profile 的 chrome（`cleanup_m7a_self_started_browsers`，不带标记的一律不碰）。
- **失败分类**：登录超时 / 排队超时 / 时长为 0 / 付费耗尽 / 浏览器起不来是 `HSRNonRetryableTaskError`，本用户剩余模块不跑、不进 `RunTimesLimit`；「未登录」「请在浏览器中完成登录操作」不判失败，转调度台提示与用户通知。文案一律照抄三月七原文（见 `tools/log_detect.py` 的云 marker），三月七一次运行内部会重试 3 遍，只在模块已失败时按 marker 归类。
- **LastLogin 是只读展示**：运行中记在 runtime，配置解锁后合并写回 `Cloud.LastLogin`（与 `CompletionWriteback` 同一时机）；「登录云游戏」接口跑三月七自带的 `game` 任务当登录探针，受外部路径锁保护、与任务互斥，config.yaml 用完逐字节还原。
- **不嵌进 Electron**：让三月七连 MAS 自己的 Electron 会被它的 `close_all_m7a_browser()` 终止 MAS 主进程，且 chromedriver 版本对不上。浏览器保持独立进程。

## 快速配置：明确不支持（方案 B）

**HSR 不支持快速配置**：SRA/M7A 的原生配置由脚本 GUI 维护，MAS 侧托管字段（每日关卡等）的写入深度耦合托管运行器（临时配置覆盖而非直接写原生文件），不存在可独立下发的快速配置子集，故 `Info.IfQuickConfig` 开关不产生任何行为差异，前端不渲染该开关（死开关；声明见 `app/task/HSR/tools/native_control.py` 的 `resolve_user_control`）。不要按普适承诺给 HSR 加快速配置面板，也不要在实现中把「直控+开启」与「直控+关闭」造出差异。

## 其他必守规则

- **关卡字段保持脚本原生形状**（SRA `id`+`level`，M7A `instance_type`+`name`），不引入 MAA 式统一关卡词表。
- **客户端平台切号统一走 SRA StartGame**，M7A 模块也依赖该登录路径；不要为 M7A 另起切号实现（云平台的切号是换浏览器 profile，见「云模式契约」）。
- 完成态一律经 `CompletionWriteback` 在真实成功后写回，**不在模块执行中途直接改 `Data`**。
- 周期判定用 ISO 周字段 + 完成日期**双字段**，不靠日期差推算。
- 兑换码只存状态指纹，不存明文。
- 人工排查不接管任务模块执行，**不要把自动代理的模块编排逻辑复制进来**。
- 托管字段运行时动态渲染，**新增字段扩展后端字段定义，不在 Vue 里加分支**。
- 脚本态共享计划落在 `HSRConfig` 同名组上、由 MAS 表单编辑；不新增 `ScriptConfig.py` 或原生编辑器遮罩会话。

## 配置恢复接入要求

已接入通用配置恢复（mas/native 双池 + 字段侧车，无会话），机制见 [config-restore.md](config-restore.md)；后续改动**必须符合**：

- **mas 池是纯字段侧车（MAS 用户配置全量），按 owner 分两表**：HSR 无 per-user 目录，用户配置即字段。用户表恒读写用户配置——Info（Mode 仅预览不回填，防静默翻转配置来源；Name/Status/Server/RemainedDay/前后脚本/Notes）、Notify、Control 引擎开关；计划表按配置来源读写——TaskSwitch 任务开关、Stage 副本配置（含原生关卡 JSON）、TaskOpt、Managed.TaskMapping/Options（运行时物化进原生），脚本态读写脚本共享计划（不含惰性的 Managed.TaskMapping），**绝不拿脚本配置读用户表**。侧车另带 `_plan_owner`（script / user）标注，预览显示「任务配置来源」，当前为脚本态时提示恢复会影响本脚本下所有脚本来源用户。侧车平铺键为 ``组.键``。**不收录** Info.Id/Password（凭据不进侧车，Notify.ToAddress/ServerChanKey 回填但预览脱敏）、Data.* 运行统计、Notify.CustomWebhooks 子表；恢复 = 用户表回填 UserData、计划表写回**当前** owner，旧侧车里已删除的 `Direct.*` 等键不回填。
- **native 池按 SRA appdata 根 + M7A 安装根组合指纹分桶**：SRA appdata 是多脚本共享目录，必须 `config_root_key` 分桶跨脚本共享、不随脚本删除；M7A `config.yaml` 随 SRA 池一并归档——只按 SRA 分桶会把不同 M7A 安装的 config.yaml 混进同一历史，跨实例恢复会写错安装，故 key 为两根指纹组合（M7A 未配置时仅按 SRA）。目标按归档内相对键 `M7A/*`、`SRA/*` 写回，只覆盖归档内包含的文件。
- **归档时机与 MAA 同型**：任务启动（manager `prepare`）归档 native（运行会写托管字段、崩溃残留会污染原生）；编辑页进入归档 native（MAS 触碰前原始态）、退出归档 mas（编辑会话包络终态）。无遮罩会话，无 viewOnly 分支。
- **预览口径**：mas 分区行（MAS 独有 = 配置来源/服务器/脚本/直控引擎；任务配置 = 任务开关/副本；通知；托管配置 = 任务映射/覆盖；直控快照 = 导入元数据），native 反读归档内**常用字段**（词表固化、零本体运行时依赖，只收录 MAS 托管白名单概念内的键）——M7A config.yaml 平铺键（清体力/副本/历战余响/体力补充/领取奖励/差分宇宙/货币战争等，键名即 MAS patch 白名单）、SRA 档案每文件一节（键形为顶层 camelCase 段 + 段内平铺点号键，见 SRA `SRACore/models/tasks_config.py`，与 MAS `_build_sra_base_config` 同口径；奖励开关兼容索引式与命名键，顺序对齐 `managed_config.SRA_REWARD_LABELS`）；`settings.json`/`cache.json` 结构未经现场核实（后者为运行缓存）**不反读内容**。两池预览载荷都带标准 `files` 字段（§3.4 基座兜底），sections 不渲染文件清单节。新增引擎/配置文件要反读时，先按上游源码核实键形再进词表，不臆造。
- **新增引擎/配置文件必须同步扩展 `collect_native_files`**——只归档不恢复等于备份了个寂寞，只恢复不归档等于永久改坏用户的原生配置。

## 审查清单

- [ ] 新增/改动模块在 `HSR_TASK_MODULES` 声明了 `supported_scripts` 与 `default_script`
- [ ] 四级回落都能取到合法引擎，每级过 `supported_scripts` 校验
- [ ] `check()` 覆盖引擎路径缺失、exe 缺失、模块分配非法、直控前置条件
- [ ] 直控仅在 `AutoProxy` 可用；未勾选引擎时回落到已配路径的引擎；原生配置文件一律要求存在
- [ ] 读计划键（TaskSwitch / Stage / TaskOpt / Managed）传 `plan`，读 Info / Data / Notify / Control 传 `user_cfg`
- [ ] HSR 不支持快速配置：未给 HSR 加快速配置面板/开关，`Info.IfQuickConfig` 无运行时消费
- [ ] 备份清单覆盖本次改动涉及的所有原生配置文件
- [ ] `existed=False` 的目标在恢复阶段被清理而非跳过
- [ ] `final_task` 与 `on_crash` 都恢复外部配置并释放路径锁
- [ ] 路径锁冲突转成可读错误，未静默等待
- [ ] 模块结果状态与 reason 能解释每个模块的最终结果
- [ ] 完成态经 `CompletionWriteback` 写回，未在执行中途改 `Data`
- [ ] 加密字段未经 API 明文外泄
- [ ] 新增托管字段走后端定义，未在 Vue 加硬编码分支
- [ ] 能力快照的 `effective_engines` 与实际可执行引擎一致
- [ ] 云平台：引擎恒为三月七；新增三月七 patch 键进了白名单；patch 在云浏览器就绪之后写；客户端专属动作（StarRail.exe、分辨率、游戏路径、SRA StartGame）都有平台分叉
