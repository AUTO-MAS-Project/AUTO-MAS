# 案例：BetterGI（better-genshin-impact 线，原神一条龙）

BetterGI 基于 BetterGI 程序（`BetterGI.exe`）跑原神一条龙，与 ZzzOd 同属
一条龙家族但物理形态不同：**无持久槽位**——用户独立配置模式下运行时把
字段物化到临时槽位 `User/OneDragon/MAS独立配置.json` + 前缀配置组，运行
结束删除/还原；MAS 前端是唯一编辑入口。本文件只记读代码推不出来的部分，
文件与字段现场读 `app/task/BetterGI/` 与 `views/BetterGIUserEdit/` 确认。

## 配置分层（决定备份对象）

| 层 | 位置 | 性质 |
| --- | --- | --- |
| 用户字段 | `UserData`（Info/OneDragon/Switch/Data/Notify） | 前端编辑，事实源之一 |
| per-user 副本 | `data/{script_id}/{user_id}/` 的 `OneDragon/`（一条龙副本）、`ScriptGroup/`（配置组）、`GlobalDomain/`（秘境刷取） | **前端端点直接读写**（`/scripts` 的 read/write_user_script_group、read/write_global_domain_settings 等）——就是页面编辑对象 |
| BGI 全局主配置 | `{RootPath}/User/config.json` | **MAS 每次运行临时补写队伍/策略叶子、结束还原**（`apply_global_battle_*` + `snapshot/restore_global_battle_config`）——唯一被触碰的持久原生文件 |
| BGI 一条龙实配 | `{RootPath}/User/OneDragon/*.json`（含「默认配置」） | 直控+关闭时直接跑；用户独立配置模式 MAS **零接触** |
| 临时槽位 | `{RootPath}/User/OneDragon/MAS独立配置.json` + 前缀配置组 | 运行时物化、结束删除（`_restore_one_dragon_config`） |

## 配置恢复接入要求（mas=per-user 副本 + 字段侧车；native=全局 config.json）

BetterGI 已接入通用配置恢复（mas/native 双池 + 字段侧车 + viewOnly 查看
会话），后续改动必须符合 [config-restore.md](config-restore.md) 通用要求，
另守以下 BetterGI 特有项：

- **mas 池 = per-user 副本目录 + 页面字段侧车**：副本是前端端点直接读写的
  编辑对象（对齐 OkNte「ConfigFile 即页面编辑对象」），字段侧车承载 UserData
  里会物化/注入的字段（OneDragon 段全部 + Task.OneDragonConfigName +
  Switch.Resource + Info.Mode 仅预览）；Id/Password/前后置脚本/通知/Data
  由 MAS 自己消费（登录与执行域）**不进侧车**。恢复 = 副本目录回滚 +
  字段回填 UserData。
- **per-user 副本与来源无关、恒按用户分桶，无 owner 解耦**（对齐 General）：
  直控用户前端同样编辑副本落盘，mas 池对三态都存在——不要按 MAA/MaaEnd
  「直控无 mas 池」套 BetterGI。
- **native 池 = 全局 config.json + BGI 一条龙实配**（``{RootPath}/User/config.json``
  + ``{RootPath}/User/OneDragon/*.json``，按物理根指纹分桶）。一条龙实配在
  用户独立配置模式下 MAS 零接触，但它是**用户在 BGI GUI 里的直接编辑对象**
  （直控/手工编辑场景，改坏无 MAS 侧找回点——用户实测「改了一条龙配置重进
  编辑页无备份」后纳入）；归档排除 MAS 运行时临时槽位「MAS独立配置.json」
  （运行物化、结束删除，不是用户实配）。
- **native 预览只收 mas 侧有对应概念的字段**（§3.3「两池同字段同口径」）：
  - **已启用任务**（一条龙实配反读，置顶）：实配 JSON 的 ``TaskOrder``(uid 序)
    + ``TaskEnabledList``(uid→bool) + ``TaskDefinitions``(uid→任务名) 三键
    对位合成；实配文件取 config.json 顶层 ``selectedOneDragonFlowConfigName``
    指向那份（BGI「配置」下拉所选），缺失回退首个实配；任一键缺失降级不反读；
  - 战斗配置叶子（config.json）：``autoFightConfig.strategyName`` 战斗策略
    （= 侧车 AutoBossStrategyName）、``autoDomainConfig.partyName`` 秘境队伍
    （= 侧车 PartyName）、``autoBossConfig``/``autoLeyLineOutcropConfig``/
    ``autoStygianOnslaughtConfig`` 各队伍与策略（= Plan 战斗步骤物化目标）。
  **MAS 侧无对应概念的段不进预览**——一键开关（自动拾取/剧情/钓鱼/快速
  传送/吃料理）、游戏路径、捕获模式、遮罩外观、热键等；通知凭据/米游社
  cookie 等敏感字段一律不读不展示。
- **mas 预览任务行同口径**：侧车 ``Groups``（内置组开关）显示为「已启用任务」
  罗列行（与 native 同标签）；``CustomGroups``/``Queue`` 解析 JSON 字符串
  显示罗列；不显示 Python 列表 repr。
- **运行前归档时机**：native 在 `manager.main_task`（物化前，任务级一次）；
  mas 在 `AutoProxy.main_task` 的 `_write_one_dragon_config` 前（物化会覆盖
  副本）。**注意 BetterGI 无 manager 任务级 Temp 快照机制**（与 SRC/MAA 不同），
  无恢复守卫需求。
- **viewOnly 查看会话**：BetterGI 配置会话本就「无参打开 BGI + 无基线注入
  + 无回写」（任务配置以 MAS 前端为准），viewOnly 与配置会话共享同一打开
  路径，`ScriptConfigTask` 只需收 `view_only` 参数（manager 透传），无需
  额外分支；前端查看会话超时静默关闭、关闭时不冲刷右栏配置（避免写盘）。
- **前端遮罩用 `GuiSessionMask`**：配置/查看两个实例（查看用专项
  `bettergiViewing*` 词条）；恢复按钮挂**「任务配置」标题行右侧**（该页有
  此区块；只在页面没有任务配置类区块时才退挂基本信息）。
- **清理存量死调用**：`ScriptConfigTask.on_crash` 曾调用未定义方法
  `_snapshot_one_dragon_config`（被 suppress 吞掉、永远静默失败），接入时
  已删除——不要重新引入同类「调了等于没调」的残留。

## 节点详情注入（推送报告）

- **不建 log_box 采集会话**：BGI 日志已由 LogMonitor 按相/按轮捕获进
  `log_record`（执行层一条、原生一条龙每轮重试各一条），`one_dragon_report`
  是权威解析器（Serilog 头行配对、致命信号判失败、任务名对齐、重试取轮）。
  `AutoProxy.final_task` 解析出合并分步表后，经 `tools/push_log.py` 的
  `steps_to_push_log` 转成 push_log 三元组——在这里再喂一套 log_box 逐行
  规则只会复刻解析器的上下文判定，且单会话跨重试轮的分段比 log_record 更差，
  会与判态侧形成两份并行语义（MaaEnd「聚合按任务名、判态按任务 id」同款分叉）。
  若上游日志规则足够「行内自足」（如 ok 系、MaaEnd 的 stdout 标记行）才走
  log_box 采集会话。
- **开关与聚合**：开关 = 用户级 `Notify.PushLogMode`（关闭/逐条/汇总，前端在
  用户编辑页基本信息区直接内联下拉，与 MaaEnd/ZzzOd 同型；共享组件
  `UserNotifyConfig.vue` 保留 `showPushLogMode` 门控的呈现块，默认关闭、
  按需传 prop 启用），关闭即不注入
  （push_log 保持为空）；注入点在 `AutoProxy.final_task`（on_crash 后
  final_task 仍会跑，崩溃前解析出的步骤同样进报告）。`manager.final_task`
  用 `build_user_result_text` + `mirror_report_to_dispatch` 聚合，与 ZzzOd 同型。
- **节点文本不带原因与异常计数**：只保留「✅ 成功/❌ 失败: 任务名」，
  与 `app/tools/push_log.py` 的状态行契约及汇总式渲染对齐；步内可恢复报错
  （含树脂耗尽这类预期停止）的数量与完整原因都在统计通知的分步表里，
  节点时间戳取步骤开始时刻（naive 时刻须按今天组合，
  直接 `timestamp()` 在 Windows 抛 OSError）。
