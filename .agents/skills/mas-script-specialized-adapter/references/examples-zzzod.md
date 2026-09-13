# 案例：ZzzOd（绝区零 / zzz-od）

ZzzOd 基于 `one-dragon` 框架家族，用户级配置是 **MaaEnd 式字段化**（ConfigItem 字段为事实源，web 直接编辑），但运行方式是 **注入式**：运行时由用户字段生成 zzz-od YAML 写入绑定实例槽，zzz-od 原生一条龙负责执行与游戏内切账号。不要把 zzz-od 的实例槽当 MAS 配置目录（两者结构同构但 owner 不同），也不要用 ok-ww 的三态/快速配置模型套它。

具体字段、路径、函数名现场读 `app/task/ZzzOd/` 确认。本文件只记推不出来的部分。

## 产品决策（读代码看不出为什么）

- **用户↔实例槽固定绑定，注册表零持久写入**：绑定下标存用户配置 `Info.SlotIdx`，首次运行/配置时按全局查重分配最小空闲 idx；运行/会话窗口内以合成注册表视图临时呈现 MAS 槽（详见下节），窗口外 zzz-od 原生世界零 MAS 痕迹。不要把「槽目录持久」误解为「注册表持久」——持久的是 `config/{idx:02d}` 目录（配队等），注册表（`one_dragon.yml`）从不写入 MAS 条目。
- **任务网格只把 `DEFAULT_GROUP=True` 的应用作为可选项**。自动战斗等独立工具应用不是一条龙任务；但已保存/导入的启用非默认任务照常显示并执行（对齐 zzz-od 原生「已开启的非默认组应用保留」语义），不要在聚合层过滤掉。
- 任务编排 `OneDragon.AppList` 是 JSON 字符串字段（顺序即执行顺序），前端开关=加入/移出、拖拽=调序；不做 zzz-od 式逐任务子配置页。
- **任务卡片 ⚙ 走数据驱动元数据表**（`app/task/ZzzOd/tools/app_options.py` 的 `TASK_APP_FIELDS`，加任务=加表项）：字段类型 select/bool/number/plan_list 决定前端渲染（plan_list 或字段多走弹窗，少量字段走弹层）；复杂配置不进 MAS 的任务在 `TASK_APP_JUMPS` 注册（式舆防卫战/迷失之地/枯萎之都），卡片显示跳转按钮引导进一条龙主界面；随便观已字段化进 `TASK_APP_FIELDS`，兑换码无配置字段（两表均不进）。
- **动态选项与一条龙原生 GUI 同源，全部静态读取**（`tools/compendium.py`，勿写死）：副本级联与图层=安装目录 `assets/game_data/compendium_data.yml`；咖啡= `coffee_data.yml` 排程；代理人名=`assets/game_data/agent/*.yml`；配队方案/挑战配置/锄大地路线名单=扫描 `config/auto_battle`、`config/{lost_void,hollow_zero}_challenge`、`config/world_patrol_route_list`（与上游列表函数同规则）。**唯一随槽而异的源是 `predefined_teams`**（`zzz_od_config.predefined_team_options` 读目标槽 `team.yml`，「游戏内配队」(-1) 前置，须给 `resolve_field_options` 传 `config_dir`）；`team` 类型字段/列展示同 select、保存转 int 下标（上游按 int 消费，写 str 会破坏 `-1` 判断）。字段静态 `options` 会前置合并到动态源之前（如「随机」「全部」）；`show_when` 支持条件列表与 `not` 取反（配队方案与游戏内配队互斥、合成电池隐藏，对齐上游体力计划 GUI）。
- **上游取值三态要核对**：部分枚举存 enum name 而非 value（随便观游历任务/邦布价格存 `HOUR_20`/`S4` 这类 name），锄大地的界面消失/重试处理存英文常量，体力计划等级等存中文 value——照抄 config 的 `get` 默认值与 GUI 的 ConfigItem 定义，不要凭惯例猜。
- **`plan_list` 保存按 plan_id 保留既有 `run_times`**（`merge_plan_list`）：MAS 只改计划内容、不重置一条龙运行计数，新行补 uuid（对齐上游 `ChargePlanItem.__post_init__`）；行内字段白名单=columns+隐藏持久字段（tab_name/run_times/plan_id）。
- **预备编队（前端独立组件 `ZzzOdPredefinedTeams.vue` + `/zzzod/teams(/save)` 端点）**：
  - 数据源是实例槽的 `config/{idx:02d}/team.yml`（上游 `TeamConfig`），**固定 20 个编队**：读取侧 `expand_team_list` 与上游 `team_list` 属性同规则补「编队N/全配队通用」默认项；保存整表写回，成员 `agent_id_list` 按行保留（优先传入行 > 既有行同下标 > unknown×3）
  - **成员下拉的坑**：`assets/game_data/agent` 数据文件只覆盖部分角色（老版本遗留），新角色（yixuan/dialyn 等）不在其中——必须正则解析上游源码 `src/zzz_od/game_data/agent.py` 的 `AgentEnum` 拿全量 id→名映射，数据文件只作兜底；否则下拉选不了新角色、已存 id 显示原始英文。**正则要兼容两种写法**：老角色单引号单行 `Agent('anby', '安比', ...)`，新角色双引号多行 `Agent(\n "sunna",\n "千夏",`——用 `Agent\(\s*['"]([\w]+)['"],\s*['"]([^'"]+)['"]`（`\s*` 跨行、引号两种都匹配），只认单引号同行会漏新角色
  - **MAS 不提供 OCR 识别**（上游「预备编队识别」是进游戏扫描成员的能力）：成员在一条龙侧识别后落盘 team.yml，MAS 只读写这份配置，两侧靠配置文件中转、无直接调用
- **非侵入红线（所有 ZzzOd 对接必须遵守）**：MAS **零 import、零执行、零修改**一条龙代码——对接手段只有四种：① 读写实例 YAML 配置（含直控/注入窗口）；② 正则静态解析源码常量（`*_const.py` 应用目录、`agent.py` 代理人名单，只读不执行）；③ 读静态游戏数据（`assets/game_data/*.yml`）；④ 以 CLI 参数拉起官方启动器。任何需要 `import zzz_od` / 调用其运行时 / 改其源码资源的设计都是错的。

## 存储模型：为什么与 MAA/OK-WW 系不同

MAS 通用模型是「每用户一份完整配置，脚本级=`data/{script_id}/Default/ConfigFile`、用户级=`data/{script_id}/{user}/ConfigFile`」（MAA/OK-WW/OK-NTE/HSR 系全如此）。ZzzOd **刻意不走目录副本**，物理形态必须跟目标脚本的吞入方式走：

| | MAA/OK-WW/OK-NTE/HSR 系 | ZzzOd（one-dragon） |
|---|---|---|
| 脚本配置形态 | 每用户自包含文件树，脚本按目录切换即换账号 | 单一共享树 `config/`：全局注册表 `one_dragon.yml` + 实例槽 `config/{idx:02d}`，配队/应用配置跨槽共享 |
| 用户配置落盘 | `data/{script_id}/{user}/ConfigFile/` 整树副本 | 脚本配置 `UserData` 的 `ZzzOdUserConfig` 字段对象（web 编辑的事实源），运行时物化注入绑定槽 |
| 运行方式 | 脚本读对应目录即该用户 | 内置切换=一进程内注入全部启用用户槽（合成视图 + `--instance`） |

不能照搬 MAA 目录副本的三条硬理由：① **N 倍重复**——每棵副本树都含全局注册表、全部原生实例与资源文件；② **破坏共享语义**——一条龙原生模型里配队/应用配置按实例槽组织、跨文件引用，拆成独立副本会割裂引用关系；③ **多账号跑不了**——一条龙没有「跨多棵树跑多账号」的运行模式，内置切换依赖单树多槽。

结论：统一的是「每用户一份完整配置」的语义（ZzzOd=`UserData 字段 + 绑定槽物化`两半合一），不是物理目录布局。

## 两态来源

`Info.Mode` 两态：`用户`（本配置字段，运行时注入绑定槽）/ `直控`（页面选一条龙实例直接编辑其原生配置：账号字段白名单 + 任务编排 + `instance_run`，保存即写回原始 YAML；运行仍 `--onedragon` 裸跑，MAS 不注入）。无脚本态——脚本级只保留 RootPath 与运行开关，不留用户级配置。直控账号字段读取合并 zzz-od 默认值（原生只落盘非默认字段），保存时默认值跳过不落盘。进入/退出直控页时自动对一条龙原生配置做指纹去重备份（防误操作改坏后无恢复点）。

## 直控模式：单一用户 + 实例管理（2026-09 定稿）

**每脚本仅允许一个直控用户**（前端切模式拦截 + 后端 `update_user` ZzzOd 守卫抛 ValueError，双保险）。为什么不能多个：直控是**脚本级全局视图**——实例列表、活跃实例、`instance_run` 全在一份 `one_dragon.yml` 里，多直控用户读到写的都是同一份状态，互相干扰且"每个用户独立运行意图"从架构上不成立（曾按多用户实现踩实这一坑：用户1 配 A、用户2 配 B，但活跃/运行实例互相覆盖，运行也分不开）。多账号直接在这**唯一**直控用户的实例管理里配置（实例即账号），或走用户模式注入——两态各司其职。

直控实例管理（全部映射 `one_dragon.yml`，MAS 零消费，变更前指纹备份）：

| UI | 映射字段 | 端点 | 说明 |
| --- | --- | --- | --- |
| 添加/重命名/删除实例 | `instance_list` 条目 | `instances/add` `rename` `delete` | 删除受 MAS 绑定槽保护 + 至少留一个；删除连带实例目录 |
| 「设为活跃」（灰 tag 点击） | 实例条目 `active` | `instances/set-active` | **显式**操作；页面选实例编辑不自动改活跃（自动同步曾导致用户间互相切活跃，已移除） |
| 「启动实例」开关 | 实例条目 `active_in_od` | `instances/active-in-od` | 参与「全部启用实例」运行的名单 |
| 「运行前切换账号」开关 | 实例条目 `force_login_before_run` | `instances/force-login` | 一条龙原生能力，作用点见下节 |
| 「运行实例」下拉 | 全局 `instance_run` | `instances/run-mode` | **全局设置，与编辑哪个实例无关**——独立端点，不要挂回 native-config/save 的实例通道（旧实现把 disabled 和保存都耦合在"所选实例"上，未选实例时既灰又存不了，已修） |

「在一条龙内配置」在直控下走**脚本级原生会话**（`startSession(scriptId, false, instanceIdx)`）：完整原生实例列表，不隔离不注入；**传当前编辑实例下标时会话窗口临时把原生活跃切到它**（GUI 打开即所见实例，结束还原原活跃，纯 `one_dragon.yml` active 标志操作）；启动前 `restore_instance_view` 自愈崩溃残留的合成视图。用户模式仍走合成视图会话。会话关闭后直控页重拉所选实例配置。

直控账号字段区：账号/密码（B服为 B服账号名）带红色 `*` 必填标记（区服联动），因账号切换需要完整登录信息（见下节）；字段顺序=后端 `_NATIVE_ACCOUNT_FIELDS` 元数据顺序（数据驱动栅格），**options 必须随元数据一起走**——曾把 `game_language` 的 options 写丢导致下拉退化为文本框显示原始值 `cn`。

## 一条龙侧账号切换链路（直控开关的真实作用点）

完整排查见 `.dev/zzzod-account-switch.md`。要点（`zzz-od` 源码）：

- **多账号循环（instance_run=全部实例）里，同 game_path 的实例切换由 `SwitchAccount` 无条件执行游戏内登出+重登，与 `force_login_before_run` 开关无关**；game_path 不同则关游戏重开对应客户端（天然切换）。
- `force_login_before_run`（每实例开关）的作用点是 `EnterGame(switch=False)`：该实例「启动游戏并进入」时是否先强制重新登录（覆盖仅运行当前、每实例首次进游戏、不同 game_path 重开后）。
- 前提 `has_login_info`：国服/国际服要 `account`+`password`，B服要 `bilibili_account_name`；**缺失时一条龙主动跳过强制登录**（日志 warning「登录信息未配置完整」）——开关开了没执行的排查首选。直控页密码留空不落盘（默认值跳过语义），要用强制登录必须实际填密码。
- 一条龙还有自动判定 `should_force_login`：全部实例 + 参与实例>1 + 存在同客户端实例 → 即使不开开关也强制登录。
- 边界：MAS 用户模式注入的合成注册表视图不含 `force_login_before_run`（用户模式跑 MAS 槽，本就不该生效）；一条龙本体运行中读内存值，MAS 改开关要等一条龙结束再跑才读到。

## 固定绑定与哨兵

- **合成注册表视图**：zzz-od 的 `instance_list` 是安装级全局命名空间，持久注册会让 MAS 实例混进原生世界（GUI 混排、跨脚本槽串号、「仅运行当前」误跑）。MAS **零持久写入注册表**：运行/配置会话窗口内把 `one_dragon.yml` 临时替换为「仅本脚本用户槽」的合成视图（`write_instance_view`，active_in_od=True、instance_run 多槽=全部实例/单槽=仅运行当前），窗口结束 `restore_instance_view` 恢复原生内容。`one_dragon.yml` 进程启动读一次、之后纯内存，替换窗口对启动器安全；闪退自愈靠 sidecar（`one_dragon.yml.mas-view.bak`）确定性恢复，每次窗口开始前先 restore。
- **会话/运行窗口内「只见 MAS 槽」是刻意的场景隔离，不是 bug**：视图只注册本场景的槽（配置会话=唯一槽、内置切换=全部注入槽），`--instance` 只认视图注册表内的 idx（未注册的静默丢弃）——目的是配置态不误碰/误跑原生实例、隔离跨脚本槽，与"文件层面只增量加槽目录"不冲突。要看原生实例：等窗口结束注册表还原后由一条龙自己打开（在一条龙内配置/查询会话天然只呈现 MAS 世界）；直控模式则在同一原生世界里选实例直接编辑（读的就是原生注册表）。
- **槽目录持久**：配队等复杂配置持久保留在 `config/{idx:02d}`；运行恢复只还原 MAS 注入的字段（备份内容），不删目录。
- **绑定持久在用户配置**（`Info.SlotIdx`），idx 分配全局查重：原生实例 idx ∪ 所有 ZzzOd 脚本用户 SlotIdx（`collect_used_slot_idxs`，排除本次注入/会话用户）——槽目录跨脚本共享，idx 不唯一会互相覆盖。绑定有效性要求 idx 不与原生实例/其他用户冲突（无注册表可查名字，旧版 MAS- 前缀校验随持久注册一起废弃）。
- **同脚本用户名唯一**（前端改名查重 + `check()` 兜底）：视图内槽名 `MAS-{用户名}`，重名会混；跨脚本重名由视图天然隔离。
- 有效根目录哨兵：`find_launcher_exe` 按序找 `OneDragon-RuntimeLauncher.exe` / `OneDragon-Launcher.exe`（`.bak` 不算）；离线校验另见 `tools.zzz_od_config.validate_root`（src + config/one_dragon.yml）。
- **启动器选择（用户字段 `Info.LauncherMode`，直控/用户两态通用）**：标签映射——集成=`OneDragon-RuntimeLauncher.exe`（WithRuntime 打包）、原始=`OneDragon-Launcher.exe`（旧安装器，外部 uv 拉起）。**自动**=优先 `Data.LauncherLastGood`（上次成功项），失败换另一个重试并记住下次成功的那个；原始/集成=固定（所选 exe 未安装回退默认顺序并告警）。**启动级失败靠日志证据判定**：两种启动器的一条龙运行日志都汇聚 `.log/log.txt`，启动器自身没起来（uv 缺失/同步失败早退）时该文件无应用层条目——以 `[application_launcher.py`/`[one_dragon_context.py`/`[application_factory_manager.py` 任一出现或运行记录有变化为「已启动」，避免把功能级失败误判成启动失败。原始启动器的框架日志另写 `python_launcher_framework.log`，不进 log.txt。

## 注入运行与判态

- `--instance 1,2,...`（逗号分隔多实例）**只在 `instance_run=全部实例` 分支被读取**——instance_run 由合成视图统一落盘（窗口结束随视图恢复原生值）；且 idx 必须在视图注册表内，未注册的会被启动器静默丢弃。
- 注入只做一次，**重试不清运行记录**（zzz-od 按记录跳过已完成任务）；新建槽的目录保留（配队持久）。
- 判态：内置致命日志（未找到有效的实例 / 请先结束其他运行中的功能 再启动 / 运行应用 one_dragon 失败 / 指令[ 一条龙 ] 执行失败）→ 各槽 `app_run_record` 前后 diff；成功标志「指令[ 一条龙 ] 执行成功」出现即结束日志等待（不等启动器进程退出，LogMonitor 静默期回调节流最长 60s），终态成败仍由 diff 判定。
- **节点失败不触发重跑**：运行记录 diff 里的应用失败只记录进任务报告（次日运行
  时 zzz-od 会按运行记录自行重试失败节点），不再维护关键名单、也不按名单判整轮
  重跑（曾有的 `_ZZZOD_CRITICAL_APPS` 机制已随 #696 移除）。**运行级失败
  （启动器没起来 / 登录失败 / 配置错误）**仍由 `check_log` 致命日志关键词 +
  超时态折算 `run_book=False` 走 main_task 既有「用户运行失败 → 重试」分支。
- **「通知」应用是汇总信号**：上游 NotifyApp 在本轮存在失败任务时会把自己 round_fail（消息本身 fire-and-forget 已发出），MAS 侧在 `_failed_apps`（diff 判定）与 push_log resolve（节点行）两处剔除，避免「通知（失败）」误导。
- 直控任务编排保存保留完整顺序（`save_native_tasks` 含未启用项原位写回，对齐原生队列「灰色可任意位置」语义）；「启用在前」只由前端一键整理按钮触发。用户模式 AppList 同为整表语义（含未启用项，运行侧 `parse_user_apps` 只消费启用项）；开关/拖拽/一键整理为两模式共用封装 `useZzzOdTaskBoard`，仅落盘方式不同。
- 恢复在 `main_task` finally、`final_task`、`on_crash` 三处幂等执行：先还原合成视图，再逐槽备份恢复（目录一律保留）。

## 账号切换三模式（脚本级 `Game.AccountSwitch` 下拉）

- **单实例切换**（默认，推荐）：逐用户独立会话——注入该用户配置到绑定槽 → 单实例运行（仅运行当前，无槽间切换）→ 跑完关游戏 → 下一个用户。**manager 每次只 spawn 一个代理**，跑完一个再起下一个；失败域隔离最好（重试只重启失败用户），且单用户配置必须配账密时由 `write_instance_view(force_login=True)` 强制账密登录。
- **多实例切换**（不推荐）：全部启用用户注入各自绑定槽，`--onedragon --instance s1,s2,...` 单进程覆盖所有用户（zzz-od 内部 SwitchAccount 切游戏账号）。总时长最短，但单槽失败或切换失败会拖整轮重试、用户之间不隔离；结果按各槽 diff 归属用户（`_judge_multi`），逐用户写回统计并按各自 `PushLogMode` 推送。
- **MAS账号切换**（预留）：当前选它直接返回「暂未开放」提示、不 spawn 任何代理；能力后续接入。
- 跳过条件（剩余天数/代理次数上限/任务编排为空）在**注入名单内逐用户施加**；多实例切换的触发者可能被跳过，不要把其「跳过」状态覆盖为「运行」。

## 游戏进程管理（脚本级 `Game` 配置，对齐 ok-ww/ok-nte）

- 字段：`Enabled`（启用游戏配置，任务前启动的总控）/ `LaunchBeforeTask`（任务前由 MAS 启动游戏，检测到游戏进程已在运行则跳过）/ `Path`（**游戏本体** `ZenlessZoneZero.exe`，不是一条龙启动器）/ `Arguments` / `WaitTime`（拉起后等待秒数）。
- **关闭游戏由 MAS 负责**：不传一条龙 `--close-game`——收尾/失败重试/手动停止调度都走 `kill_managed_process(kill_game=CloseOnFinish)`，按进程名结束游戏本体（游戏由启动器拉起、可能不在启动器进程树内，进程管理器跟踪不到）。`CloseOnFinish` 不依赖 `Enabled`（历史上默认开启，避免存量配置悄悄变「不关游戏」）。

## 在一条龙内配置（配置会话，双向联动）

用户配置界面只覆盖高频字段；配队等复杂配置由用户在原生界面维护。用户页顶部按钮**两种模式常显**，`useZzzodGuiSession` 派发 `SCRIPT_CONFIG`（taskId=userId）。会话与 MAS 字段**双向联动**，不是旁观式打开：

- **打开前基线注入**：`inject_user_fields` 把本页字段写入绑定槽（不清运行记录）——GUI 所见即本页配置；先归档原生配置快照，再以合成视图呈现（`write_instance_view` 仅含本槽、`active` 指向本槽）；
- **关闭时回读**：`_readback_user_fields` 把 GUI 落盘的任务编排（`_group.yml` 全量顺序含未启用项，整表进 AppList）与账号字段写回 MAS 字段——区服/路径/语言/B服名无条件回读，账号/密码仅槽值非空才回读（留空=沿用登录态，避免清空被读回）；前端遮罩关闭时重拉表单；
- 配队等 MAS 不管的内容不注入不回读，持久留在槽里；
- Default（脚本级）会话直接拉起 GUI，无注入/回读。

## 配置恢复（基座统一分发 + 专项池声明）

ZzzOd 的「配置恢复」接入通用基座（专项只声明池，详见 config-restore.md）：

- 池声明：`app/task/ZzzOd/tools/restore_service.py` 的 `RESTORE_POOLS`
  （mas=用户槽 / onedragon=原生，`RESTORE_SCRIPT_NAME="一条龙"`）；备份内部
  业务（槽占用守卫、字段回填、预览构建）依赖门面 helper，留在
  `app.core.config`（`get_zzzod_backup_preview` / `restore_zzzod_backup` /
  `ensure_zzzod_mas_backup` / `ensure_zzzod_direct_backup`），池函数经
  `ctx.config` 薄委托。
- core 门面：`restore_service()` isinstance 分发 + `list/ensure/restore/
  preview_config_backup` 四个通用方法；HTTP 层只有通用端点 `/backup/*`
  （list/ensure/restore/preview），preview 的 `data` 载荷 = ZzzOd 结构
  （info/account/tasks/instances）。
- 前端：`ZzzOdUserEdit.vue` 用 `ConfigRestoreSection` 组件（`scriptName`
  传统一名「一条龙」、内置预览渲染直接吃解包后的载荷），`restoreApi` 调
  `BackupService` 通用函数；三时机 ensure 走通用 ensure（`ensurePoolBackup`
  收 `'mas'`/`'onedragon'` 字符串）。
- 会话遮罩：配置/查看会话拉起原生 GUI 期间用 `GuiSessionMask`（纯 UI）。
- **归档三时机落地**：① 进入编辑页归档 onedragon（用户模式 `ensureDirectBackup`、
  直控 `enterDirectMode` 内同函数）——MAS 操作前原始态；② 退出编辑页
  `onUnmounted` 归档（直控 onedragon 终态；用户模式绑定槽 mas 终态 +
  onedragon 终态）——**mas 槽快照一律走统一入口 `archive_mas_config_backup`
  （先物化账号+编排进槽再快照**：账号/编排只存在 UserData，槽只有会话/运行
  才被注入，直接快照会漏掉，恢复这种备份会把它清空）；③ 运行
  前 `_prepare_injection` 两者都归档（原有）。
  `ensure_zzzod_mas_backup` 对未绑定槽跳过（无可恢复内容）。
  归档全部指纹去重：内容无变化不产生新条目，恢复列表只留真实变更点。
- 文件级快照/回写原语见 [config-archive.md](config-archive.md)。

## 陷阱

- **`ScriptItem.result` 是只读计算属性**（从 user_list 实时拼接），报告正文用局部变量 `build_user_result_text(...)` 承载，对其赋值会抛 AttributeError（ZzzOd 曾踩）。
- **配置会话必须双向联动**：只激活槽不注入基线 → GUI 与本页配置不一致；只注入不回读 → GUI 内改动下次运行被 MAS 字段覆盖（用户改动静默丢失）。回读时账号/密码非空才读，否则「留空沿用登录态」语义被破坏。
- **重试重判的幂等**：重试带着同一全零基准重判，推送条目按用户整体重建（clear 后重采），统计只在状态变化时写——否则 ProxyTimes 多次自增、推送重复。
- **instance_run 随视图恢复**；注册表零持久写入是设计核心，勿把合成视图改成持久注册（会重新引入 GUI 混排/跨脚本串号）。
- 直控模式不需要注入但仍校验 zzz-od 有活跃实例；用户态不需要（绑定槽自动注册）。
- manager `final_task` **所有模式**都写回 UserData（ScriptConfig 会话也会产生 SlotIdx 落盘）。
- schema 变更后离线导出再生成（`PYTHONPATH=. python .dev/export_openapi.py` → `npx openapi --input ../.dev/openapi.json`），禁止手改生成文件。
- **openapi-typescript-codegen 三个坑**（0.29.0 实测）：① 请求模型用中文 `Literal[...]` 会生成重复 `_` 标识符导致 TS 编译失败——枚举校验放后端原语（如白名单校验），schema 用 `str`；② **路径前缀重叠的端点会被静默丢弃**（`/instances/active` 被 `/instances/active-in-od` 吞掉，无任何报错）——端点命名避免互为前缀（用 `set-active` 不用 `active`）；③ 生成器 `--output ./src/api` 是相对 cwd 的——必须在 `frontend/` 目录下执行，曾误生成整套到仓库根 `src/api`。

## 审查清单

- [ ] 用户↔槽绑定经 `ensure_user_slot` 唯一入口，idx 与原生实例/其他用户 SlotIdx 无冲突
- [ ] 内置切换只 spawn 一个代理；注入名单逐用户施加跳过条件
- [ ] `--instance` 与 `instance_run=全部实例` 成对出现且结束恢复
- [ ] 槽内容在成功/失败/取消/超时/异常五条路径恢复；注册表按设计保留
- [ ] 任务网格只提供默认组任务；已保存非默认任务不被静默过滤
- [ ] 结果按槽归属用户；推送按各用户 PushLogMode 且重试不重复
- [ ] 配置会话双向联动：基线注入 + 关闭回读 + 恢复原活跃实例；SlotIdx 与回读结果落盘
- [ ] 查看会话（viewOnly，如「查看历史备份」）：不注入基线、不回读字段、无保存入口——预览不得污染 MAS 字段
- [ ] 直控页面编辑：账号保存走「保存设置」按钮，任务/运行实例即时增量提交（不把未保存的账号草稿一并落盘）；账号字段白名单过滤且默认值不落盘
- [ ] 直控单一用户约束：切「直控」时前端拦截 + 后端 `update_user` 守卫都校验（每脚本仅一个直控用户）
- [ ] 直控实例管理的字段映射走 one_dragon.yml 原语（`_registry_rmw`），变更前指纹备份；删除受 MAS 绑定槽与「至少一个实例」保护
- [ ] 运行实例（`instance_run`）走独立 run-mode 端点，不与「编辑所选实例」的通道/disabled 耦合
- [ ] 直控账号字段元数据（顺序与 options）一致；`game_language` 等下拉字段的 options 未丢失
- [ ] 报告正文走 `build_user_result_text` 局部变量，未对 `ScriptItem.result` 赋值
