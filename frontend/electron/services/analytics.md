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
| `initialization_finished` | 初始化尝试的整体结局 | `flow_kind`、`runtime_mode`、`outcome`、`failed_stage`、耗时桶 | 每次尝试一次 |
| `screen_view` | 白名单业务页面导航成功 | `screen`、`script_type` | 相邻同类页面去重 |
| `script_create_finished` | 新建、模板导入、复制、项目复用 | `create_kind`、`script_type`、`outcome`、耗时桶 | 每次创建流程一次 |
| `user_create_finished` | 用户创建接口结果 | `script_type`、`outcome`、耗时桶 | 在音效、默认名和导航之前 |
| `config_write_finished` | 脚本、用户、设置的共享写入结果 | `owner_kind`、`section_kind`、`script_type`、`outcome`、耗时桶、`sample_rate` | 实际写入作业；成功固定 1/10 采样 |
| `task_start_result` | 启动请求受理或失败 | `source`、`mode`、`target_kind`、`outcome`、耗时桶 | 每次实际请求一次 |
| `task_observed_finished` | 常驻订阅收到已观察任务的完成消息 | `mode`、`script_type`、`outcome`、耗时桶 | 创建、完成都收到的样本 |
| `update_download_finished` | 本窗口发起下载的结局 | `source`、`outcome`、耗时桶 | 完成、取消、失败共用一个终态 |
| `connection_incident_finished` | 非计划断线的一次恢复事故 | `outcome`、`recovery_kind`、耗时桶 | 多轮重连归并为一次 |

耗时区间为 `<1s`、`1-5s`、`5-30s`、`30-120s`、`>120s`。
系统字段仅含应用版本、系统名称和版本、系统语言、Chromium 版本、传输实现版本与生产标记。
事件带 UTC 时间和内存中的随机会话 ID，不使用安装标识或对象 ID。会话空闲一小时或满 24 小时更换；
关闭遥测时也清除会话。会话与匿名估算使用量不等于安装量、真实账号数或长期唯一用户。

主界面就绪只表示 Vue 已挂载，不表示初始化、后端或任务已完成。辅助窗口、renderer 重载和第二实例
不增加同一进程的计数。请求失败也占用这次计数，不重试，因此事件缺失不能解释成应用故障。

初始化准备步骤完成不代表成功；确认主连接可用后才记成功，跳过步骤、强行进入但未确认连接、
失败分别记录。启动时自动跳过已完成的安装步骤仍需确认连接，单独标记 `flow_kind=skip`。
脚本模板导入失败时，根据清理结果区分失败与部分完成；项目复用失败但保留基础记录为部分完成。
脚本和用户写入覆盖共享 API，合并的保存请求不会额外计数；设置遥测开关自身不产生事件。
原生配置会话内容、独立导入接口、计划等候选事件不在这批共享保存统计范围。

四种任务模式独立标记；受理不代表执行成功，跨专项整体结果标为 `multi`，不复制为各专项成功。
任务 ID 只用于两个最多 128 项的内存集合，恢复快照不创建观察样本。重复完成与重复创建去重；
进程重启或集合淘汰后不保证精确一次。没有完整收到创建和完成的任务不推断结局，
不能以观察完成数除以全部请求数声称全量成功率。
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
