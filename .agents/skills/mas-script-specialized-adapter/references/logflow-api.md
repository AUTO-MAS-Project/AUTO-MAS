# 在 L4 接入 LogFlow

LogFlow 是 MAS 内置的日志分析工具。L4 把本轮已经配置好来源的监视器、账号运行节点和规则交给它。分析在独立子进程完成，运行树持有实时和最终节点。未迁移专项继续按 [LogBox 指南](logbox-api.md) 维护。

## 单账号进程监控

让监视器使用专项已有的启动函数。启动函数返回进程对象，所选 stdout 或 stderr 须接到管道。专项仍用其原有的执行结果决定本轮成败。

```python
from auto_mas_core.log_flow import LineRule, LogFlow, LogMonitor, SimpleFlowDeclaration

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

# L4 执行方法。launch_script 返回进程，on_log_lines 沿用既有原始日志回调。
monitor = LogMonitor((0, 0), "", self.on_log_lines, process_factory=self.launch_script)
flow = LogFlow(monitor, self.user_info, RULES)
await self.spawn(flow)

nodes = self.user_info.log_analysis.nodes
reason = self.user_info.log_analysis.close_reason
exit_code = monitor.source_returncode
```

直接 `await flow.run()` 执行同一生命周期。临时调度组件用 `await self.spawn(flow)` 将取消沿 L4 调用链传递。正常结束或取消由 `TaskBase.final_task` 排空监控尾部、关闭采集进程并提交最后一批节点和采集终态。账号运行状态仍由 L4 决定。

## 读取运行树中的节点

普通 `POST /api/dispatch/get` 只传 `taskId` 时省略分析节点。要读取某个正在运行的账号或最近完成的账号，在同一接口里显式选择托管运行 ID 和账号运行 ID。

```json
{
  "taskId": "<任务运行 UUID>",
  "logAnalysis": {
    "scriptRunId": "<托管运行 UUID>",
    "userRunId": "<账号运行 UUID>"
  }
}
```

在 `data[taskId].scripts.data[scriptRunId].users.data[userRunId].log_analysis` 读取 `nodes` 和 `close_reason`。节点每批提交到账号运行树，更正保留同一 `node_id`，撤回从当前 `nodes` 移除。`close_reason` 在采集结束前为空，结束后可为 `complete`、`timeout`、`worker_error` 或 `capacity`。当前查询返回选中账号的快照。

请求必须来自本机。携带 `Origin` 时须为 HTTP 或 HTTPS 回环来源，响应禁止缓存。打包版 Electron 正式接入时须经受信任的主进程转发。普通任务列表和 WebSocket 继续省略分析节点。

## 其他来源与通知

- 监视文件或已有来源时，可给 `LogMonitor` 配置 `source_runner`。它使用监视器启动本轮文件或进程监控并等待业务结束。LogFlow 在收尾时停止监控。由该函数自行启动且未交给监视器持有的业务资源仍按专项现有生命周期管理。
- `LogFlow` 接受文件、自定义来源和下沉、主动上报及报告归并配置。声明规则、处理器和工厂的参数格式与 `analyze_logs()` 一致。运行期间可用 `flow.reporter` 主动上报。`analyze_logs()` 仍可用于无任务树依赖的独立分析。
- 托管层可将 `flow.result` 交给 `LogFlowTaskReport.record()`，在托管报告定稿后用 Notify 统一投递。逐条、汇总和关闭模式由调用方选择。
