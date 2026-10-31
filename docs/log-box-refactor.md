# log_box 重构需求与实施记录

> 本文保留重构前的历史需求与验证记录，不作为当前接口规范；当前用法见
> [日志处理规范](../.agents/skills/mas-script-specialized-adapter/references/logbox-api.md)。

更新：2026-10-29。分支：`refactor/log-box-pipeline`。本文件作为后续阶段的需求基线。

## 需求来源与优先级

依据本聊天从 PR #1729 讨论开始的用户原话整理，未将助手的建议当作用户确认的需求：

1. 最初因 MFW 新增任务详情讨论通知结构。用户说明 log_box 原本是「声明式的非阻断节点采集」，专项主要声明 `push_log.py` 与配置地址，采集处理交给 box；box 异常不得导致脚本失败，正则能力保留供自配。
2. 用户说明 BGI 绕过 log_box 是历史遗留，希望先内部重构；曾提出严格格式，以及把最终推送、控制台展示收进 box，担心扩展性和改动规模。
3. 明确硬约束：「用户侧无感，最终推送结果不变」。这优先于最初统一通知位置的设想；没有授权重新分配个人统计与全局报告的订阅范围。
4. 用户询问特殊一条龙是否仍能专项自适配：必须保留专项解析、重试归并、账号路由扩展，不强制改写为正则。
5. 最新明确顺序：「重构+非日志类的接口开发，然后看end要不要切换接入方式，然后再接入MFW」。不能跳到 MFW，也不能把 MaaEnd 切换视为既定结论。

## 约束与非目标

- 相同输入、开关及运行结果下，通知正文、顺序、时间戳、状态符号、失败过滤和调度台展示保持一致。
- 配置位置、默认值、三态开关、通知触发与订阅范围不变。不新增用户手工配置。
- box 负责采集/结果交付和公共节点渲染；通知渠道发送、订阅决策和任务成败仍归宿主。将整套通知服务搬进 box 并非已确认需求。
- 专项仍拥有原有权威解析；不新增上游状态推断，不复制一套判态逻辑。
- 工作线程只处理快照，宿主线程绑定和交付；关闭幂等，取消先等待交付再传播，不让结果污染下一账号。
- 非阻断指重处理离开事件循环，且普通采集异常不影响脚本结果；并非零收尾等待，也不承诺线程/正则强制超时。
- 保留旧 `get_collect`、正则表达式、处理器及兼容导出。脚本子进程 stdout 通道尚未端到端接通，不因本重构宣称可用。
- 不改 API/config/schema/frontend，不新增遥测事件或更新日志条目：本阶段仅内部变动。

## 完成情况（以提交和实测区分）

| 阶段 | 状态 | 证据/限制 |
| --- | --- | --- |
| 管线、结果契约、公共报告渲染拆分 | 已提交 | `8f3caa48a`；`LogEntry`/`Node`，保留原始文本 |
| 用户托管会话、NTE | 已提交并实测 | `8b2e105b2`；用户两次确认 |
| 翻译管理、OKWW/BAAH/MaaEnd 日志接入 | 已提交 | `9dae59971`；OKWW/MaaEnd 用户实测；BAAH 自动回归，未声称实跑 |
| 动态快照与 ZZZ 账号路由 | 已提交并实测 | `ebf39fedb`；单账号实跑，多账号归属自动回归 |
| BGI 结构化来源试点 | 已提交并实测 | `5988b48a3`；16:23 分步表 6 行，统计通知发起，任务报告 Webhook 成功；不据此声称个人渠道送达 |
| 独立非日志接口 | 本轮实现待提交 | `EntrySpec` + `get_entry_session`；无用户/文件依赖，共用关闭屏障；BGI 使用显式 EntrySpec，保留用户交付 |
| MaaEnd 来源切换评估 | 已完成当前实现初评，暂保留日志 | task_dict 不是等价的报告来源，缺少时间与失败细节；见下文 |
| MFW 接入 | 未开始实现 | 需前两阶段契约稳定后实施 |

BGI 前两次失败为后端旧类与延迟加载的新专项混用，重启后已消失；修改公共类后必须完整重启后端。
最近 BGI 运行有两步失败、首次超时后重试成功，属于运行结果，不能把接入通过说成所有任务成功。
全量历史回归有 7 项既有前后置脚本测试失败，前序已对基线复现；应持续单独披露，不能报全绿。

## 非日志接口契约

`EntrySpec(bind=...)` 不包含规则、日志路径、翻译等无关参数。
`bind` 在宿主线程返回 `LogBinding(read=..., deliver=...)`：

- `read` 在工作线程返回 `list[LogEntry]`，包含原始文本、类型和可选时间戳；不自行补造任务状态。
- 独立会话必须声明 `deliver`，不要求伪造用户对象；适用于已有报告区块、自定义归属等目标。
- `get_user_session(EntrySpec, user=..., mode=...)` 使用已有用户落点，允许专项自定义路由。
- 返回值先整批验证，格式错误不交付部分有效项。绑定、读取、交付失败只记录诊断，关闭不会重新尝试或重复推送。
- 自定义交付回调应尽量短；若其自身写入一半后抛错，box 无法回滚外部副作用，不承诺事务。
- 输入快照由专项在宿主固定，box 不深拷贝任意对象；绑定和交付回调不得夹带阻塞 IO。
- 原 `LogSpec(source="entries")` 继续兼容，但新接入优先 EntrySpec。

## 后续顺序与验收

### A. 完成非日志接口

本轮补无用户入口与契约测试，保留 BGI 文本转换函数；验证关闭/启用、线程归属、缺失目标、错误形状、读取与交付失败、并发/重复关闭、取消。
与现有专项一起回归，完整重启后端后再实测 BGI。当前阶段不推进 MFW。

### B. 评估 MaaEnd

对照 stdout 节点与现有结构化结果：名称与 id、执行顺序、阶段、重试取轮、同名任务、开始但无终态、崩溃/取消、路线失败明细、时间戳。
只有新来源完整覆盖旧报告信息且来源属于公开结果面时才切换。否则保留日志采集：统一生命周期不等于统一来源。
当前初评结论：不切换。`AutoProxy.check_log` 的 `task_dict` 是按任务名/id 管理的剩余执行状态，
不提供与原节点报告等价的时间、顺序和路线失败原因；`push_log.py` 的 DETAIL 规则仍从 stdout
提取这些信息。仅把 task_dict 包装成 EntrySpec 会丢信息，还会将执行判态结构绑定到通知。
证据：`app/task/MaaEnd/AutoProxy.py` 的 check_log 与 final_task；`app/task/MaaEnd/push_log.py`
的 MAAEND_PUSH_RULES/maaend_resolve。MaaEnd 继续使用现有日志会话，待上游提供信息完整的
公开结构化结果入口时再复评。物资统计仍为独立业务，不混成节点。

### C. 最后接入 MFW

先保留 `run_report` 的重试时间线、脱敏人话原因、事件提示、失效任务及无运行记录退路。
当前时间线进入个人统计 `task_details`，代理结果只有用户行；内部统一不能擅自把时间线追加到全局任务报告。
通过独立结构化接口对接已有报告目标，保留截图、通知条件和 worker 隔离；不得让 `tools/core` 导入 log_box 或宿主模块。
对多次重试、失败、未开始、取消、跳过和无记录场景逐字比较旧新报告，并运行 MaaFW 核心边界测试。

## 本轮验证记录

执行环境：Windows / 仓库 `.venv`。基线提交 `5988b48a3` 加本地未提交变更。
相关最小回归（entry_source、bettergi、session、reports、zzzod、oknte、adapter_sessions、maafw_core）：
`python -m pytest <上述文件> -q -p no:cacheprovider --basetemp=test-results/logbox-neutral-final`：142 passed。
完整回归：`python -m pytest tests -q -p no:cacheprovider --tb=no --basetemp=test-results/logbox-neutral-full`：
667 passed、3 skipped、29 subtests passed，7 failed 均为既有 `test_script_pre_post_retry.py` 项。
Ruff check 与格式化通过，git diff --check 通过。
独立非日志接口已获用户实跑确认：16:51 分步结果 6 行，统计通知发起，任务报告 Webhook 成功。
该阶段已提交 924a93c8d。未执行 MFW 真实游戏流程；自动回归不代替真实脚本实测。


## 未接入来源盘点与基座预留评估

2026-10-29 按当前代码只读盘点；评估后已开始补充结果状态契约，见下节。

| 对象 | 当前来源/展示 | 接入判断 |
| --- | --- | --- |
| HSR | runtime.module_results，模块、引擎、状态、原因 | EntrySpec + 自定义交付足够，不能把引擎模块状态直接等同游戏节点 |
| Whimbox | 上游结果块原文、多账号分组、失败提示；渠道另有短摘要 | 保留整块原文，可用无时间 LogEntry 与自定义交付；不拆解私有文本重建判定 |
| MAA | 理智/掉落/招募/培养统计，另有喜报 | 这些不都属于节点，不将统计、图片或喜报塞进节点模型；以后仅接真实节点来源 |
| SRC | 历史聚合与整体结果 | 无现成细粒度节点表；接口足够，数据来源须专项另行确认 |
| MFW（含 M9A、MSS） | 结构化运行记录、时间线、事件提示与截图 | 独立会话适合，但要明确失败后如何保留现有退路 |
| general | UI 规则、在线增量缓冲、marker、最终报告已复用 box 部分能力 | 部分接入；保留 UI 规则，不强迁为专项内建声明；未来迁移增量能力单列 |

参考代码：HSR/AutoProxy.py 的 _format_current_user_module_results；Whimbox/tools/marker.py
和 tools/notify.py；MAA/tools/notify.py；SRC/AutoProxy.py；general/AutoProxy.py；
MaaFW/tools/embedded/runner_task.py 的 _run_record_call/_build_task_details。

建议第一个 PR 再补的最小契约：对宿主公开可查询的收尾结果，至少区分禁用、成功空结果、
成功有结果、失败；绑定/读取失败与交付失败应可诊断。当前 close 返回 None 且异常仅记录日志，
不适合让 MFW 可靠选择原有 fallback。自定义交付可能部分写入，不能自动重试或保证回滚。
具体形式在实现时选最小方案，不公开异常堆栈或敏感上下文。

已有接口足够承接：自定义路由、无时间戳、原文多行块、特殊状态原文、宿主快照和任意已有文本目标。
暂不增加：通用 metadata 字典、引擎字段、任务树/事件总线、通知渠道/HTML/图片模型、
async read、流式 feed。未发现当前未接入专项必须依赖这些新接口的证据。
流式增量与异步 IO 若以后确有需求，应以实际接入案例单独设计，不放入本次基础重构。


## 收尾结果契约补充

前阶段提交：`924a93c8d`。本补充不包含 MFW 接入；用户实跑确认后提交。

- 两种会话统一提供只读 `session.result`，值为不可变 `SessionResult` 快照。
- status 为 pending / disabled / succeeded / failed；成功空结果用 succeeded + entry_count=0，
  与禁用、失败区分。pending 不保证尚无外部写入，收尾完成前不得据此发报告或兜底。
- failure_stage 为 initialize / bind / read / deliver / cleanup，不包含异常对象或账号内容。
- entry_count 记录已整批交付成功的数量；deliver 失败时保持零，但外部可能已有部分写入。
  cleanup 失败时保留已知完成交付的数量，优先保留第一个失败阶段。
- close 仍返回 None；异常隔离、旧失败提示和通知行为不变。取消等待结束后可查询最终结果。
- MFW 后续可按状态与失败阶段选择现有退路，不能看到 failed 就自动重跑交付，尤其 deliver/cleanup。
- 最小回归：146 passed（session_result、entry_source、session、reports 及四组专项兼容测试）；
  Ruff 检查和格式化通过。全量 683 passed、3 skipped、29 subtests passed，
  仍仅 7 项既有前后置脚本测试失败。命令：python -m pytest tests -q -p no:cacheprovider
  --tb=no --basetemp=test-results/logbox-result-full。


收尾结果补充实测复核：2026-10-29 17:36 BGI 返回 Success，分步表 6 行，统计通知发起，
任务报告 Webhook 成功；用户确认推送与结果正常。本轮未发现新的节点交付异常。
提交前相关回归再次 146 passed，Ruff 与 git diff --check 通过。


## 审核后类型契约修正

dev 至 c846c0d6c 双方独立审核后发现一项 P3：LogEntry 允许无时间戳，用户与 sink
落点仍标注 float。现已同步 UserItem、LogUser、_append 及同步采集 sink/factory 类型，
并明确兼容旧二元组；未改运行时输出或外部 API。回归使用真实 UserItem 接收
无时间戳三元组，与旧二元组共同逐条渲染；相关测试 116 passed，Ruff 通过。
此修正经用户授权提交推送。最终全量回归 684 passed、3 skipped、29 subtests passed，
仍为 7 项既有前后置脚本失败；Ruff check/format 与 git diff --check 通过。

非日志来源推荐在专项 push_log.py 声明 EntrySpec，由宿主准备只读快照。
bind 在宿主返回 LogBinding，read 在工作线程把快照转为 LogEntry 列表。
普通用户节点用 get_user_session；特殊报告落点用 get_entry_session 并提供 deliver。
调用方必须 await close 后再组装报告，可从 result 区分成功空结果与失败。


## PR #1744 审核与 dev 同步

已合入 upstream/dev（2ac826c8c），保留新专项注册入口与 log_box 报告入口；
唯一文本冲突在 task_manager.py import，MaaEnd 上游采集选项修正自动合并保留。
审核三点处理：entries LogSpec 缺 bind 在声明时拒绝；自定义 deliver 可返回实际
接受的条目数（0 到输入数量），返回 None 继续兼容接受整批的旧回调；ZZZ 明确返回
过滤后数量。两类会话共用计数逻辑，失败不自动重试。失败路径测试新增阶段和交付尝试断言。
相关回归 201 passed，包含新注册机制和 MaaFW 核心边界。

同步后完整回归：900 passed、3 skipped、29 subtests passed、8 failed。
7 项为原有前后置脚本问题；新增 test_existing_channel_is_migrated_once[beta] 在未修改的
upstream/dev 隔离导出副本中同样失败（stable != beta），未扩大本 PR 修复范围。
完整命令：python -m pytest tests -q -p no:cacheprovider --tb=no
--basetemp=test-results/logbox-dev-review-full。


## Ubuntu CI 文件身份修正

原 LogSource 用 inode + ctime 识别轮转，但 POSIX ctime 在普通追加时会变化，
导致从头重读历史内容。现按平台识别：Windows 保留 inode + 创建时间；POSIX 使用
inode + 设备号。新增确定性平台测试覆盖追加、轮转尾部、截断及无 inode 的 Windows 替换。
旧算法运行 POSIX 用例稳定失败，修正后相关回归 161 passed。未修改原 CI 断言。
本机无已安装的 WSL Linux 发行版，实际 Ubuntu 验证交由新一轮 CI。
