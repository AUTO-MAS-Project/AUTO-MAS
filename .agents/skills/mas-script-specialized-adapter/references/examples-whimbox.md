# 案例：Whimbox（无限暖暖 / 奇想盒）

奇想盒是叠纸《无限暖暖》的第三方一条龙工具（Electron 壳 + 嵌入式 Python 后端），MAS 走 **PC 前台直控线**（与 BetterGI 同族）：游戏在真实桌面运行，脚本靠截图 + 模拟输入操作。本文件只记**读代码推不出来**的部分。

**事实来源与时效**：下列上游事实按 `nikkigallery/Whimbox`（真上游，非 fork）的 **v3.0.5** 源码逐条核对；复核时注意本地 checkout 的 `origin` 可能是停在旧版的 fork，**必须 `git fetch upstream --tags`** 再比。v3.0.6 / v3.0.7 未改动本文件涉及的接口——`main.py`、`task/task_template.py`、`task/daily_task/all_in_one_task.py`、`common/logger.py`、`config/config.py`、`ability/ability.py`、assets 三件套、`common/cvars.py` 在该区间均为 0 提交，变了的是三个 UI 自动化任务文件与图片资源；实机已验证：装在 3.0.7 的目录读出的目录与 3.0.5 完全一致（8 步骤 / 14 参数）。另外：Electron 壳不在该 Python 仓内，涉及壳的事实（`python-embedded` 布局、env、`whimbox_app.exe`）按**发行版安装目录实证**，无法从上游 git 复核。

## 上游形态（决定实现边界）

- **无头入口**：`python-embedded/python.exe -s -m whimbox.main startOneDragon`（cwd=安装根）。MAS 复刻 app 的拉起方式（PATH 前插 `python-embedded` + `PYTHONHOME`），提权分支见 `tools/launcher.py`。
- **游戏不是它启的，是它点出来的**：`os.startfile(launcher_path)` 启动叠纸启动器（进程名 `xstarter.exe`），再用 OCR 找「启动游戏」按钮点击。**整条链路没有传参点**——想给游戏传命令行参数（如 UE 的 `-ResX`）没有插入位置。
- **分辨率只检测不修复**：`check_shape()` 要求游戏窗口宽高比 ∈ (1.55, 1.80)（容差用来吸收 1920×1081 这类异常值），不满足即失败并提示用户；上游没有设置分辨率的入口。
- **配置三件套**：`site-packages/whimbox/assets/` 下的 `default_config.json`（模板）、`setting_options.json`（值域）、`material.json`（材料）——MAS 的任务目录从这里机械转换，**发版不管理字段定义**。
- **上游会删未知键**：`configs/config.json` 加载时合并新默认键、删除模板外的键，所以物化只能写模板里已存在的键。

## 产品决策（读代码看不出为什么）

- **两态（脚本 / 直控），没有「用户」态**：根因是**上游不按账号分档配置、MAS 也无法指定运行账号**——`change_account` 是它自己的循环行为，账号由它 OCR 识别。于是"用户"这个维度在上游既不能配、也不能指定跑，脚本/用户两态下发时落到同一份 `config.json`、行为完全一致。存量「用户」值由 `WhimboxConfigModeValidator` 归一到「脚本」。
- **没有快速配置**：快速配置唯一的消费点（直控态注入面板字段）与「直控 = MAS 零写入」相悖（与 ZzzOd 封锁同因），且「脚本」态面板覆盖的本来就是上游一条龙参数全集，没有可划的高频子集；字段干脆不存在。前端必须**显式**传 `:quick-config="undefined"`——Vue 的 Boolean casting 会把"不传"归一成 `false`，反而渲染出死开关。
- **面板只覆盖一条龙相关两节**（`OneDragon` + `OneDragonDefaultSteps`）：键位（27 个）、后台任务、LLM、启动器路径等一律走直控在 app 里设。这是"不把上游配置面板原样搬进来"的落地，不是尚未实现。

## 配置安全

- **overlay 语义**：运行前强制归档 `config.json` → 脚本态按当前模板键集物化该用户覆盖集 → 结束（成功/失败/崩溃）**无条件还原**；直控态从物化入口直接返回，MAS 零写入。
- **恢复双池**：`mas` 是**纯字段侧车**（覆盖集 + 流程开关 `IfRunAllAccounts` + 来源标注 + 展示快照），`native` 是 `config.json`（按物理路径指纹分桶）。`auto_close_game` 由适配层恒置 true，没有页面字段、不进侧车。
- **侧车字段判据**：会注入原生配置的字段进备份（`Task.*`、`OneDragon.*`）；只由 MAS 消费的执行域字段（前后置脚本、通知、剩余天数）不进。**来源（`Info.Mode`）与展示快照只预览不回填**——回填旧来源会静默翻转「MAS 是否写入上游」。
- **恢复后必须重拉表单**：否则旧表单值下次保存会把恢复结果覆盖掉。
- **上游目录常是受保护目录**：奇想盒默认装在 `C:\Program Files\whimbox_app`，该目录对普通用户只读，而上游自己的无头入口**要求管理员**（`_prepare()` 里 `is_admin()` 不通过就 `exit()`）。于是写 `configs/config.json` 这条链有两个提权点：上游进程靠脚本设置的「以管理员运行」（UAC 拉起子进程），**MAS 自身的写入必须 MAS 已提权**——两者不是一回事，报错时要说清（`_write_config_or_hint` 已按此给文案）。MAS 未提权时 脚本态必然 EACCES；改成「直控」（MAS 零写入）可以正常跑。

## 陷阱

- **重试只救「没有上游结论」的异常**：上游自己判负（`failed`）或环境性致命（`fatal`，如缺管理员权限）时，重试等于把整条一条龙再跑一遍（含重新启动游戏），而原因不会在几分钟内自己变——`_should_retry` 因此只在「提前退出/卡死/未判定」时按 `Run.RunTimesLimit` 重试，`failed` 仅当**失败原因与上一轮不同**（情形在变）才继续；同一结论连着出现即收口并提示用户处理后手动运行。这是有意偏离「非 Success 一律重试」的家族写法，理由是上游的 `failed` 是它跑完流程给出的结论，与「进程崩了」不是一类。
- **日志文案就是判定面**：成败取自**上游自己的顶层任务结果面**——收尾行 `任务结束，程序退出`（`main.py:81`，无论成败都打，只证明进程正常走完）＋ 完成行 `一条龙任务完成: {message}`（`main.py:80`）的消息形态：消息含结果块头「任务结果如下：」＝正常跑完（单步 ✅/❌ 在块里透传），不含＝上游自己把顶层任务判成失败/中止（如开局进不了游戏，`all_in_one_task.py:315-316`），透传其失败原因、不断言完成度。**日志里还有第二处文案依赖**：`AutoProxy.py` 的 `_DISPATCH_LINE_PREFIXES`（`✅`/`❌`/`🛑`/`账号列表:`/`当前账号:`/`已完成账号列表：`）按原文前缀把进展转述到调度台（这些行确实落文件，`log_to_gui` 末尾有 `logger.info`，`task_template.py:351`），上游改 emoji 或文案后实时进展会**静默消失**。改文案时必须同时改这两处。
- **收尾步骤会覆盖结果块**：`step8`（打结果块）之后还有 `step_close_game`（适配层恒写 `auto_close_game=true`，上游必然排它，`all_in_one_task.py:135-136`）；它失败时 `update_task_result(FAILED, "关闭游戏失败")`（`:501-502`）覆盖刚写的结果块，而结果块只在完成行打印一次——那条路径下分步 ✅/❌ 在上游那里根本不存在（可用性待真机核实，`close_handle` 内部吞异常）。
- **结果块不带原因，「未完成原因」段单独补**：上游默认步骤的 ❌ 行只有三态（`_format_default_summary_line` 不拼 message，只有前置/后置自定义步骤的 `_format_custom_summary_line` 才带 `：{message}`），失败原因只在上游自己的 `❌ …` 日志行里。报告因此分两块呈现：结果块原文 + 「未完成原因（上游提示原文）」逐行列出（`AutoProxy.failure_notes` 收集 `❌`/`🛑` 行，判据是**本行带时间列**——结果块续行没有时间列，不过滤会把块里的 `❌…未完成` 重复收进去）。**不做「行→步骤」映射**：那是上游私有语义，映射表属禁止项，用户按文案自己就能对上。另有「**非失败提示**」表（`WHIMBOX_BENIGN_MARKERS`）把上游以 ❌ 打出、实为正常状态的文案排除出原因段——目前一条 `正在挖掘，无法收获`（`dig_task_v2.step2` 在挖掘位仍在冷却时判 FAILED，对用户是「今日没得收」）。**结果块原文一律不改写**：那行 `❌美鸭梨挖掘未完成` 是上游自己的判定，要变成 ✅/⏭️ 得提上游 issue。
- **traceback 与单步 ❌ 都不是进程级失败**：traceback 由每个 TaskTemplate 的 catch-all 打印（`task_template.py:259-267`），**单步子任务的异常同样会打**，上游的处理是「记 ❌ 后继续跑下一步」；按关键词判 fatal 会杀掉上游本来会跑完的一轮（顶层异常已由「完成行消息不含结果块头」自然判负）。同理不得把已完成/已跳过的行之外的单步 ❌ 当进程失败。
- **停滞判定只有看门狗一条路径可达**：feed 只在**有新行**时才派发事件，LogMonitor 的 60 秒空闲回调不产生事件；因此 `Run.RunTimeLimit` 的停滞收口必须由 `_exit_watchdog` 每轮调 `_evaluate_and_release()` 完成（进程退出与停滞超时共用该循环），否则「进程活着但日志静默」会永久挂起。
- **部分内置步骤依赖上游下载的跑图路线，缺了就整轮中止**：`step_home_task` 构造时硬编码 `AutoPathTask(path_name="家园日常")`（`all_in_one_task.py:336`），路线不在上游脚本库里直接 `raise ValueError('路线"家园日常"不存在，请先下载该路线')`（`navigation_task/auto_path_task.py:59-62`）——异常冒到顶层 catch-all，**整轮在第 2 个日常步骤中止**（不是跳过该步、也不是单步 ❌）；前置/后置自定义步骤走 `_run_custom_path`，同样缺路线只记 ❌ 继续。路线库是上游 app 内自行下载管理的资源（`scripts_manager`），MAS 不读也不代下（黑箱），适配层无门槛可降——只能靠判定面把上游那句可操作文案透传给用户（已透传）。
- **游戏窗口前置会被系统拒绝**：上游抢前台用 `AttachThreadInput` + `SetForegroundWindow`，被拒时报 `(5, 'AttachThreadInput', ...)` / `(0, 'SetForegroundWindow', ...)`，最终呈现为「游戏窗口前置失败」（上层抛 `Exception` → 顶层判负）。常见成因是前台焦点被别的窗口占着（如 MAS/Electron 窗口）或窗口与调用进程不在同一权限级别；属上游领域，`run_once` 内它会自己「自动重试一次」。
- **游戏侧配置改不动，也不要试**：无限暖暖（UE5）的 `Saved/Config/Windows/GameUserSettings.ini` 是强加密（`_XYP_` 前缀 + 高熵密文，16 字节对齐），`Logs/` 同样逐行加密，且游戏带内核级反作弊 ACE（`AntiCheatExpert/` 含 `.sys` 驱动）。**MAS 不应代管游戏侧设置**（分辨率、画质）——加密、反作弊、启动链路无插参点，三重堵死；`Engine.ini` 之类的外部注入只在用户自担风险时试。
- **目录缓存的实际边界**：`_catalog_cache` 是实例级的，而 surface 由调用方逐次新建（API 每次请求、每用户轮次），**跨请求不共享**——不要据此推断有跨请求缓存。
- **资产不可读要响亮失败**：三件套读不到时 `read_catalog` 抛错（由 API 转 400 + 可操作文案），不返回空目录——空目录会把"读不到"伪装成"上游没有这些字段"。`config.json` 同理走 `read_dict_file`：**缺失或合法空映射 `{}`** 按模板播种（上游首启同款，空配置本就等价全默认），**损坏**抛 `ConfigCorruptedError` 原样上抛（任务异常路径带路径上报，用户可在编辑页用配置恢复还原），不得静默拿模板副本顶上。
- **会话哨兵比运行哨兵宽松**：`ScriptConfig` 模式只查 `whimbox_app.exe` 单哨兵（会话仅拉起 app，后端未初始化也要能进设置会话去修环境）；`AutoProxy` 走三件哨兵（跑一条龙需要完整后端）。

## 审查清单

- [ ] 目录字段全部来自上游下发；启发式只允许这两处且都在展示层——前端 `optionPrefix`（`get_` 前缀归一成行）、后端目录 `_infer_field_type`（按模板默认值类型推 `field_type`）。值语义判断一律不得按上游键名做（曾按 `_target` 后缀决定可清空，已改为一律可清空＝取消覆盖）
- [ ] 物化按当前模板键集过滤（模板外的键写了也会被上游删掉）
- [ ] 直控零写入；脚本/直控两条路径的还原在所有退出路径上都执行
- [ ] 无「用户」态与快速配置的理由仍是"上游不按账号配置 / 直控零写入"，不要照三态模板补齐
- [ ] marker 表与上游日志文案一致；成败取「收尾行 + 完成行消息是否含结果块头」，不把 traceback / 单步 ❌ 当进程失败；改文案时 `tools/marker.py` 与 `AutoProxy.py` 的 `_DISPATCH_LINE_PREFIXES` 两处一起改
- [ ] 停滞（`Run.RunTimeLimit`）有可达的评估路径（看门狗每轮评估，不能只在进程退出时评估）
- [ ] 统计通知走 `statistic_targets` + `dispatch`（全局渠道与渠道级重试在内），结果块进得了邮件/网页正文
- [ ] 配置恢复 `mas` 池只回填会注入原生配置的字段，来源与展示快照只预览
- [ ] 不在游戏侧做任何写入（分辨率为上游领域且技术上封死）
- [ ] 新增配置字段都有运行时消费点（schema 里存在但没人读 = 债）
