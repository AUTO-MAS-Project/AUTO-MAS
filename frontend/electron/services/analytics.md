# 匿名使用统计

Electron 主进程按 Aptabase 的单事件协议向
`https://telemetry.auto-mas.top/api/v0/event` 发送数据。App Key 是公开的客户端写入标识，
不包含管理或查询凭据。Vue 通过受限 preload / IPC 交给主进程，不初始化 Web 或 Electron SDK。

## 当前采集范围

| 事件 | 含义 | 自定义字段 | 频率 |
| --- | --- | --- | --- |
| `app_started` | 主进程进入 ready | 无 | 每进程最多一次 |
| `renderer_ready` | 主窗口完成 Vue 挂载 | `duration_bucket` | 每进程最多一次 |
| `backend_start_finished` | 串行启动作业的真实结果 | `outcome`、`runtime_mode`、耗时桶 | 合并的启动请求不重复 |
| `initialization_decided` | 直接进入、完整初始化或强制更新的启动决策 | `decision`、`runtime_mode`、耗时桶 | 每进程最多一次 |
| `initialization_stage_finished` | Runtime 实际命令及旧安装阶段的返回结果 | `stage`、`runtime_mode`、`outcome`、`known_code`、`failed_stage`、耗时桶 | 每次实际执行一次，不按进度帧统计 |
| `initialization_recovery_selected` | 初始化失败后的恢复动作 | `action`、`stage`、`mirror_kind`、耗时桶 | 每次用户选择；后续结果另计 |
| `initialization_finished` | 初始化尝试的整体结局 | `flow_kind`、`runtime_mode`、`outcome`、`failed_stage`、耗时桶 | 每次尝试一次 |
| `screen_view` | 白名单业务页面导航成功 | `screen`、`script_type` | 相邻同类页面去重 |
| `script_create_finished` | 新建、模板导入、复制、项目复用 | `create_kind`、`script_type`、`outcome`、耗时桶 | 每次创建流程一次 |
| `user_create_finished` | 用户创建接口结果 | `script_type`、`outcome`、耗时桶 | 在音效、默认名和导航之前 |
| `config_write_finished` | 脚本、用户、设置的共享写入结果 | `owner_kind`、`section_kind`、`script_type`、`outcome`、耗时桶、`sample_rate` | 实际写入作业；成功固定 1/10 采样 |
| `task_start_result` | 启动请求受理或失败 | `source`、`mode`、`target_kind`、`outcome`、耗时桶 | 每次实际请求一次 |
| `task_observed_finished` | 常驻订阅收到已观察任务的完成消息 | `mode`、`script_type`、`outcome`、耗时桶 | 创建、完成都收到的样本 |
| `task_stop_result` | 共享单任务停止请求的受理结果 | `source`、`mode`、`request_outcome`、耗时桶 | 每次实际请求 |
| `task_resume_requested` | 指定脚本起点或用户范围的启动请求 | `source`、`resume_kind`、`scope_kind`、`request_outcome`、耗时桶 | 与通用启动事件分开说明用途 |
| `queue_manage_finished` | 队列及队列项创建、删除、配置与排序 | `action`、`queue_kind`、`count_bucket`、`outcome`、耗时桶 | 每次实际写入；整批排序一次 |
| `queue_schedule_changed` | 定时、循环及启动调度设置 | `schedule_kind`、`action`、`outcome`、耗时桶 | 实际写入结果，不记录日期时刻 |
| `plan_manage_finished` | 计划基础记录创建、重命名、删除与排序 | `action`、`plan_type`、`count_bucket`、`outcome`、耗时桶 | 每次实际管理请求 |
| `script_run_started` | 自动代理进入一次脚本执行流程 | `mode`、`script_type` | 顺序队列逐项、循环队列逐轮 |
| `script_run_finished` | 本窗口观察到该次脚本执行结局 | `mode`、`script_type`、`outcome`、耗时桶 | 开始、结束都收到的样本 |
| `native_config_action_finished` | 原生配置打开、查看、保存/关闭请求及丢弃通知 | `script_type`、`operation`、`outcome`、耗时桶 | 每次实际请求；重复丢弃帧去重 |
| `config_restore_finished` | MAS/原生备份恢复与强制确认结果 | `script_type`、`target_kind`、`forced`、`outcome`、耗时桶 | 每次实际恢复请求 |
| `community_login_finished` | 米游社、森空岛扫码会话的终态 | `provider`、`stage`、`outcome`、耗时桶 | 每次生成尝试一个终态，不逐次轮询 |
| `notification_test_finished` | 已配置通知的总体测试响应 | `test_kind`、`request_outcome`、耗时桶 | 每次实际测试请求 |
| `notification_channel_changed` | 内置通知渠道启用、停用的保存结果 | `channel_kind`、`action`、`outcome`、耗时桶 | 每次实际写入；包括绑定后的自动启停 |
| `notification_binding_finished` | QQ 通知绑定、重绑及解绑结果 | `channel_kind`、`action`、`outcome`、耗时桶 | 每次绑定会话一个终态；状态查询不计 |
| `webhook_test_finished` | 独立 Webhook 测试的返回结果 | `scope_kind`、`outcome`、耗时桶 | 每次测试一次；不含地址或响应正文 |
| `update_download_finished` | 本窗口发起下载的结局 | `source`、`outcome`、耗时桶 | 完成、取消、失败共用一个终态 |
| `update_check_finished` | 手动检查结果及首次自动检查摘要 | `trigger_kind`、`outcome`、`update_available`、耗时桶 | 手动按实际共用请求；自动每进程最多一次 |
| `update_download_started` | 本地下载尝试首次获得进度或请求响应 | `source_kind`、`release_channel`、耗时桶 | 与下载终态共用操作前代次，每次尝试最多一次 |
| `update_source_changed` | 用户确认换源的结果 | `from_kind`、`to_kind`、`trigger_kind`、`outcome`、耗时桶 | 每次实际换源请求，不按速度帧统计 |
| `update_install_requested` | 立即或稍后安装的选择 | `choice`、`request_outcome`、耗时桶 | 稍后不发安装请求；受理不代表安装器已启动 |
| `connection_incident_finished` | 非计划断线的一次恢复事故 | `outcome`、`recovery_kind`、耗时桶 | 多轮重连归并为一次 |

耗时区间为 `<1s`、`1-5s`、`5-30s`、`30-120s`、`>120s`。
数量区间为 `0`、`1`、`2-5`、`6-20`、`20+`，排序按一批记录，不按对象逐条发送。
系统字段仅含应用版本、系统名称和版本、系统语言、Chromium 版本、传输实现版本与生产标记。
事件带 UTC 时间和内存中的随机会话 ID，不使用安装标识或对象 ID。会话空闲一小时或满 24 小时更换；
关闭遥测时也清除会话。会话与匿名估算使用量不等于安装量、真实账号数或长期唯一用户。

主界面就绪只表示 Vue 已挂载，不表示初始化、后端或任务已完成。辅助窗口、renderer 重载和第二实例
不增加同一进程的计数。请求失败也占用这次计数，不重试，因此事件缺失不能解释成应用故障。

初始化准备步骤完成不代表成功；确认主连接可用后才记成功，跳过步骤、强行进入但未确认连接、
失败分别记录。启动时自动跳过已完成的安装步骤仍需确认连接，单独标记 `flow_kind=skip`。

阶段统计在主进程执行边界记录：Runtime 自身校验/更新为 `runtime_binary`，完整准备命令为
`bootstrap`，单项命令对应 `python`、`repository` 或 `dependency`；失败时另带有限枚举的
`failed_stage`。不把界面补齐的阶段或接管的 pip/Git 算成成功。旧链路完整初始化与单步重试
在实际安装、拉取及依赖调用返回时记录。错误码只保留显式白名单，其他一律 `unknown`。
恢复选择只记录按钮动作、阶段和内置镜像类别，不记录镜像键、地址或诊断内容。

QQ 绑定以当前扫码会话返回网关 `connected` 为完成；取消、替换、过期、失败和卸载分别终结，
迟到响应不计入新会话。绑定/解绑的结果先于后续渠道开关保存及页面刷新确认，开关写入单独统计。
Webhook 测试按接口实际响应记录成功或失败，网络异常记 `unknown`，不据此断定对端未收到。

更新检查沿用既有共用请求和取消能力；同一请求每种触发只记一次。自动检查由 renderer 首次
观察和主进程进程级去重共同限制，不按标题栏十分钟或弹窗四小时轮询累计。手动检查加入
自动检查的在途请求时，各触发记录一次结果，不能把二者相加当独立网络请求数。结果在接口
返回时确认，音效或弹窗失败不改写已确认的检查结果。不采集最新版本号、更新公告或错误原文。

下载开始在当前本地尝试的首帧进度或 HTTP 返回时记录；尚未知道后端来源时用 `unknown`，
不读取额外配置或猜测。版本只归为正式、公测或未知，不发送版本字符串或操作 UUID；重试
是新尝试，换源仍属于同一次尝试。快照恢复、释放后迟到响应不产生新开始；观察中途丢弃的
尝试可能没有开始或终态，不能把两者当严格全量漏斗。自动转源不假装用户点击换源；低速提示
确认与手动入口分开归类，接口确认前不把来源目标当成已切换结果，网络异常记 `unknown`。

安装接口创建后台任务后即响应，因此 `accepted` 只表示请求已受理，不能证明安装器启动、
新版本安装成功或下次成功启动。稍后安装为 `not_requested`，隐藏后台下载不等于稍后安装。
失败后的工作区恢复、普通重试和 Runtime 更新各开启新尝试；重复启动回调不重置计时或重复计数，
恢复耗时包含完整 bootstrap，Runtime 更新后的尝试也包含镜像配置准备。
脚本模板导入失败时，根据清理结果区分失败与部分完成；项目复用失败但保留基础记录为部分完成。
脚本和用户写入覆盖共享 API，合并的保存请求不会额外计数；设置遥测开关自身不产生事件。
原生配置会话内容、独立导入接口、计划等候选事件不在这批共享保存统计范围。

四种任务模式独立标记；受理不代表执行成功，跨专项整体结果标为 `multi`，不复制为各专项成功。
任务 ID 只用于两个最多 128 项的内存集合，恢复快照不创建观察样本。重复完成与重复创建去重；
进程重启或集合淘汰后不保证精确一次。没有完整收到创建和完成的任务不推断结局，
不能以观察完成数除以全部请求数声称全量成功率。

主要页面白名单包含任务台。停止请求受理不表示任务清理完成，最终取消仍看任务观察结果；
本批不包含全局紧急停止。续跑统计只描述指定脚本起点或用户范围，不推断这是失败重试；
循环模式忽略的脚本起点不记为续跑，普通配置与更新任务不进入该事件。
范围只归入全部、脚本用户或队列用户，不发送范围中的 ID 或对象数量明细。

队列配置、循环队列项调度共用显式 API 边界，不改变保存、排序、回读或失败处理；
“立即运行一次”只是修改下次执行时间，记为 `run_once`，不据此记任务已启动。
队列和计划类别仅复用已有读取与成功写入，在最多 128 项的本机映射中关联；缺少类别用
`unknown`，不会额外请求后端。队列时间集合管理、具体日期和计划表格编辑尚未纳入。
计划 `create` 表示基础记录已创建，默认名称保存另记 `rename`，不是完整配置引导完成；
名称保存失败不会回改基础记录创建结果，音效或回读失败也不改写已确认的管理结果。
仅发固定计划类别，不发名称、计划内容、精确时刻、命令或任意字段值。

逐脚本事件沿用 MAS 现有脚本执行边界与结果判定：混合队列分别记录各专项，循环每轮单独记录；
原生配置和脚本更新不计入。尚未轮到、被禁用或占用而跳过的条目没有开始事件。
`script_run_started` 表示进入执行流程，可能随后预检失败、无用户或因维护全部跳过，
不等于游戏内任务已执行或已成功。结束结果分别为 `success`、`failed`、`skipped`、`no_user`、
`incomplete`、`error`、`cancelled`，复用现有 MAS 状态，不读取上游内部数据。
轮次 ID 和任务 ID 仅用于本机 WS 关联与最多 128 项的内存去重，不发送至 Aptabase。
重复边界不增加次数，恢复快照不补报；缺失开始、断线、退出或关闭遥测造成的样本不推测结局。
后端逐轮消息通过运行时任务注册表后台发送，最多 32 项在途，拥塞时直接丢弃；
结束帧等待开始帧的发送结果，但脚本执行和收尾均不等待统计消息。进程关闭取消在途消息。
整任务完成不提前清掉逐轮观察，以容纳晚到的最后一轮终态。

原生配置的 `open/view/save/close/timeout` 只记录请求受理或失败，不宣称 GUI 已打开或配置已保存；
手动保存、关闭及自动超时由实际调用入口明确分类，与停止失败时是否保留会话无关。
主列表保存共用同一入口；仅清理页面观察、没有发出停止请求的超时不虚构请求事件。
MAA 的改动丢弃消息单独记为 `discard/discarded`，只取固定分类，不取原因正文。
恢复请求的 `confirmation_required` 表示还需二次确认，强制恢复是另一请求；不传备份时间或文件名。
已知的 `onedragon` 和 `native` 备份池统一归入 `target_kind=native`，原始恢复参数保持不变。
扫码会话只记录生成、扫码、保存阶段的最终结果。凭据已由后端确认保存后，即使本地回填失败仍记
`saved`；无目标账号仅记 `confirmed_unsaved`。过期、取消、重新生成和卸载分别记录，
票据、二维码地址、凭据及账号标识均不进入事件。旧会话异步响应和关闭期间的会话不补报。
通知测试仅记录总体请求的 `accepted/rejected/unknown`，网络异常为结果未知，
不提供逐渠道送达率，不采集通知渠道配置、收件人或正文。Webhook 测试尚未纳入。

在 Aptabase 的 Release Dashboard 选择 `script_run_started`，属性选择 `script_type`，
可自动得到时间范围内各专项进入执行流程的次数；切换 `script_run_finished` 可查看结束结果。
选择 `mode` 可比较顺序与循环，选择 `outcome` 可查看各结果次数，无需导出再手工相加。
当前官方后台的自定义趋势图只支持按事件名保存，属性分类选择为临时页面状态；
不提供同时按专项与结果交叉分组的固定图表、成功率公式或定时报表。
因此这些高级报表仍需后续补展示或分析能力，当前不宣称已有自动成功率看板。
旧版本只有整任务事件，不能从历史 `multi` 或整轮循环汇总反推出逐脚本次数。
下载只观察本地启动的操作，取消 API 与 WS 共用一次终态；快照只对账，超时或网络结果不明记
`observation_unknown`，不推断后台失败。主动关闭、计划内重启和被其他窗口接管不算断线事故；
自动恢复达到上限标记 `recovery_stopped`，不是后端最终结局。观察中途退出直接丢弃。

主进程最多 4 个并发请求，每分钟总计最多 120 条，每事件族最多接受 60 次调用。
保存成功按进程内成功序号固定抽取每 10 次中的第 1 次，失败不参与此采样，输出
`sample_rate=10/1`；限频、断网、关闭、并发上限仍会丢弃，不能把乘以采样倍率的数量当精确总数。
采样序号不落盘，导航采用相邻去重和同一频率预算。没有后台心跳、进度或逐日志事件。

## 开关与传输

- 复用 `Function.IfEnableTelemetry`；使用现有 YAML 优先、仅升级前读取旧 JSON 的配置读取器。
  不用前端缓存中的 true 覆盖后端选择。配置缺失、损坏或值未确认时停采，不缓存启动事件。
- 运行中关闭立即中止可取消的请求。开启还须确认后端持久化配置；不补发关闭期间的操作，
  操作开始前取得的代次在关闭后失效。已经到达服务端的数据无法由本地开关撤回。
- 开发、纯浏览器、CI、单元测试、E2E 与显式禁用遥测的环境不发送生产统计。
- 仅主窗口的主 frame 和应用本地入口能使用 IPC；主进程验证事件与字段，不接受自由文本、
  未知字段、嵌套值、账号、路径、配置、日志或网络地址。
- 固定 HTTPS 目的地，禁止重定向，不携带 Cookie，五秒超时。不排队、不重试、不写磁盘，
  不等待发送来决定业务或退出结果。退出时直接取消，不为遥测延长关闭流程。
- 服务端和反向代理会接触连接 IP。正式统计默认保留 1825 天（约 5 年），到期后后台清理；
  这是服务端策略，客户端开关不负责删除已接收的数据。

## 保留策略核对

2026-10-23 检查 1Panel：运行镜像为官方 `ghcr.io/aptabase/aptabase:main`；
对实际 ClickHouse 执行只读的 `SHOW CREATE TABLE default.events`，确认表启用了 `TTL ttl`。

当日官方源码在
[EventRow.cs](https://github.com/aptabase/aptabase/blob/4cca4bb394819c3591c019f758ce09c2844e544e/src/Features/Ingestion/Buffer/EventRow.cs)
固定声明正式事件保留 `5 * 365` 天、调试事件保留 `182` 天，过期时间从事件时间计算。
本客户端仅允许正式环境发送，沿用正式事件的默认策略。容器使用浮动 `main` 标签，
本次没有核验运行中程序集的常量或镜像对应提交；这里记录官方默认值，不作镜像版本一致性的保证。
未来更换镜像或数据库策略时需重新核对说明。

ClickHouse 在后台处理 TTL，不保证过期时刻立即物理删除。本次没有检查反向代理日志、
容器日志或备份的留存期限，上述期限仅指统计事件。未修改服务端配置或写入测试事件。

## 扩展约束

后续业务事件需同时增加类型契约和主进程运行时白名单，并重新确定每类事件的限频与去重边界。
异步操作在开始前获取 context，完成时携带原代次，不在完成后重新获取代次来补报。
不要把请求受理当作执行成功，不把恢复快照当新事件，不扩展到通用请求或日志拦截器。

协议参考：[Aptabase 单事件实现](https://github.com/aptabase/aptabase-electron/blob/main/src/main.ts)、
[官方自建 SDK 说明](https://github.com/aptabase/aptabase/wiki/How-to-build-your-own-SDK)。
