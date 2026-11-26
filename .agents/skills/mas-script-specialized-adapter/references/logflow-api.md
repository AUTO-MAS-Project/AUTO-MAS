# 在 L4 接入 LogFlow

适用于已插件化的专项和希望复用 MAS 日志分析的调用方。LogFlow 是宿主提供的工具，专项在账号执行器内调用。未迁移专项继续按 [LogBox 指南](logbox-api.md) 维护。

## 用 MAS 日志采集节点

为每次账号执行创建自己的监控器。在启动日志生产端之前打开分析，在退出分析之前停止或排空监控器。下面的执行器片段复用专项已有的日志回调和脚本执行方法。

```python
from auto_mas_core.log_flow import (
    LineRule,
    LogMonitor,
    SimpleFlowDeclaration,
    analyze_logs,
)

RULES = SimpleFlowDeclaration(
    rules=(
        LineRule(
            match=r"^完成：",
            extract=r"$(完成：(.+))",
            node_type="步骤",
            status="success",
        ),
    ),
)

# L4 的执行方法体。report 由托管层创建并在结束时统一发送。
monitor = LogMonitor((0, 0), "", self.on_log_lines)
analysis = None
try:
    async with analyze_logs(
        RULES, monitor=monitor, prepare_report=report_mode != "关闭"
    ) as analysis:
        self.user_info.bind_log_analysis(analysis)
        try:
            await self.run_script_with_monitor(monitor)
        finally:
            await monitor.stop()
finally:
    if analysis is not None and (result := analysis.result) is not None:
        await self.user_info.record_log_analysis(result)
        report.record(self.user_info, report_mode, result)
```

`analyze_logs` 使用独立分析进程，默认收尾等待两秒。超时会返回已采集节点和 `reason="timeout"`，报告末尾注明采集不完整。执行器按专项自己的结果来源判断任务成败。取消时，专项的监控收尾须覆盖已启动的日志流，工作进程在有界收尾后向调用方继续传播取消。

## 在框架里观察运行中的节点

L4 把独立分析显式绑定到本次账号。框架或专项从该账号运行节点调用
`capture_log_analysis()`，可在任务仍运行时取得当前有效节点和同一时点的游标。
用 `node_id` 识别同一个节点，用 `revision` 判断是否已更新。采集是否结束由
`close_reason` 表示，账号执行状态仍由 `info.status` 表示。

## 查询结果

本机调用现有的 `POST /api/dispatch/get`，在请求正文传 `{"taskId":"<运行 UUID>"}`。通过 `data[taskId].scripts.data[scriptRunId].users.data[userRunId].log_analysis` 读取结果。树里的账号键是本轮运行 UUID，账号配置 ID 仍在 `info.user_id`。

- `nodes` 是最终有效节点，已撤回节点从结果中移除。
- `close_reason` 可为 `complete`、`timeout`、`worker_error` 或 `capacity`。没有结果时该账号省略 `log_analysis`。
- 当前任务与最近完成任务均可查询。最近结果受任务数量、保留时长和缓存容量限制。节点文本和附加字段在公开查询前做脱敏。

### 运行中查询和断线补读

用同一个 `POST /api/dispatch/get` 请求，在 `taskId` 外传入 `logAnalysis`。
该模式只返回选中账号的 `logAnalysis`，可用于实时进度界面或本机组件。

```json
{
  "taskId": "<任务运行 UUID>",
  "logAnalysis": {
    "scriptRunId": "<托管运行 UUID>",
    "userRunId": "<账号运行 UUID>"
  }
}
```

- 省略 `cursor` 时返回当前有效节点及同一时点的游标。分析开始后即使还没有节点，也可能返回有效游标。
- 补读时把上一响应的 `{sessionId, sequence}` 作为 `logAnalysis.cursor` 原样传回。增量按 `sequence` 顺序返回，`limit` 取 1 至 100，默认 50。`hasMore` 为真时继续读取下一页。
- 以 `node_id` 更新当前节点表，以 `revision` 跳过已处理的旧版本。`withdrawn: true` 表示移除该节点。重复提交相同游标可重读同一批顺序事件。
- `closeReason` 表示采集终态。末页可能没有节点但有终态，仍应更新采集状态。脚本任务状态通过现有任务状态查询读取。
- HTTP `409` 表示游标过期、超前或属于其他运行。清空本地节点表并重新获取快照。变更历史已淘汰时，若最终结果仍在缓存中，首读仍可返回结果，此时 `cursor` 为 `null`。没有可用结果时返回 `404`。
- 节点查询仅限本机，响应禁止缓存。HTTP 请求携带 Origin 时须为 HTTP 或 HTTPS 回环来源。打包版 Electron 的 file 页面可能产生 null Origin，未来接入时应通过受信任的主进程转发。最终结果与变更历史各有保留预算，随进程重启一起清理。默认任务列表、WebSocket 和 MCP 沿用原有数据范围。


## 来源、表达式和扩展

- 原生日志传本轮 `LogMonitor`。文件源传 `FileInput(path=...)`，默认从打开时的文件位置跟随。支持和主动上报一起使用。
- 主动上报传 `accept_push=True`。在上下文内用 `analysis.reporter` 的 `text`、`node`、`withdraw`。`accepted` 表示已入队，`backpressure` 表示有界队列暂满，`closed` 表示分析已经关闭。
- 专项声明使用 `SimpleFlowDeclaration`。单行规则用 `LineRule`，多行窗口用 `WindowRule`。可选的 `preprocess`、`postprocess` 和 `functions` 用可导入的 `FunctionRef`。通用脚本读取当次 WebUI 快照并用 `GeneralFlowDeclaration(patterns=..., hooks=...)`。
- 自定义来源和下沉通过 `source`、`sink` 传 `WorkerFactorySpec`。自定义文本处理器配置在 `SimpleFlowDeclaration.processor`。工厂和源码路径随本次调用传给子进程，参见 `WorkerPluginPackage`。扩展应使用可序列化的参数。
- `LogFlowTaskReport` 由托管层持有。账号执行器用 `record` 写入结果，托管在任务报告定稿后调用一次 `send`。可选用 `LogAnalysis.report_lines(mode=...)` 取得逐条、汇总或关闭模式的文本。若只采集节点，把 `prepare_report` 设为 `False`，可跳过报告归并器。

接入专项时，模拟测试至少覆盖正常结束、取消和超时，逐条与汇总通知，以及两轮调用不会串号。正式迁移再按专项要求对照真实脚本、配置与通知。
