# ok-script MAS 结构化事件协议

> 状态：草案 v1
> 适用范围：OK-EF、OK-WW、OK-NTE 等 ok-script 系项目与 AUTO-MAS 的运行结果接管。

## 1. 目标

MAS 通过 `working/logs/mas-events.jsonl` 接收 ok-script 的结构化运行事件。该协议用于替代“扫描 GUI 文本日志判断结果”的不稳定路径，让 MAS 自己展示运行步骤、子任务失败和最终状态。

兼容规则：

- 外部脚本尚未写入 `mas-events.jsonl` 时，MAS 继续回退读取 `ok-script.log`。
- MAS 一旦读到合法结构化事件，当前轮运行以结构化事件作为判态来源。
- 传统文本日志仍会进入历史记录和 OK-EF 日报解析，但不再覆盖结构化事件的终态。

## 2. 文件位置

事件文件固定放在脚本文本日志同目录：

```text
{ok-script-root}/data/apps/{resource-name}/working/logs/mas-events.jsonl
```

示例：

```text
E:\Tools\ok-ef\data\apps\ok-ef\working\logs\mas-events.jsonl
```

要求：

- 编码使用 UTF-8。
- 每行写入一个完整 JSON 对象。
- 写入后尽量 flush，避免 MAS 轮询时长时间读不到事件。
- 不完整 JSON 行会被 MAS 忽略，等待下一次补齐。

## 3. Envelope

每行事件至少包含：

```json
{"version": 1, "event": "step", "message": "已进入任务界面"}
```

字段：

- `version: number`：当前固定为 `1`。
- `event: string`：事件名。
- `message: string`：展示给 MAS 的文本。
- `task: string`：可选，当前步骤或子任务名称。
- `success: boolean`：可选，终态事件建议填写。
- `failures: array`：可选，子任务失败列表，元素格式为 `{"task": "...", "message": "..."}`。

未知字段允许保留；MAS 会忽略未知事件名与未知协议版本。

## 4. 事件名

- `run_started`：脚本开始接管任务。
- `step`：普通进度步骤。
- `task_completed`：某个子任务完成。
- `task_failed`：某个子任务失败，但整轮仍可继续执行。
- `summary`：汇总说明，不代表终态。
- `run_completed`：整轮结束。
- `run_failed`：整轮异常结束。

不要把“未连接游戏窗口”作为独立异常字段写给 MAS。连接窗口应作为普通 `step` 或脚本内部等待过程处理；只有最终确认无法恢复时，才用 `run_failed` 写清楚真实原因。

## 5. 终态规则

整轮成功：

```json
{"version": 1, "event": "run_completed", "success": true, "message": "日常任务完成"}
```

成功但部分任务失败：

```json
{
  "version": 1,
  "event": "run_completed",
  "success": true,
  "message": "日常任务完成，部分子任务失败",
  "failures": [
    {"task": "⭐转交运送委托", "message": "未完成任何转交运送委托操作"},
    {"task": "⭐演算", "message": "未找到等级信息标志，可能没有进入演武集算关卡界面"}
  ]
}
```

整轮失败：

```json
{"version": 1, "event": "run_failed", "success": false, "message": "任务执行超时"}
```

## 6. 写入侧建议

Python 侧建议使用追加写入：

```python
import json
from pathlib import Path


def emit_mas_event(log_dir: Path, payload: dict) -> None:
    event_file = log_dir / "mas-events.jsonl"
    event_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, **payload}
    with event_file.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        fp.flush()
```

推荐顺序：

1. 启动任务后写 `run_started`。
2. 每个关键阶段写 `step`。
3. 子任务失败时写 `task_failed`，并继续执行后续任务。
4. 结束时只写一个 `run_completed` 或 `run_failed`。
5. 如果有子任务失败，把最终失败列表放入 `run_completed.failures`，MAS 会展示“Success! 但部分任务失败”。

## 7. 插件事件

MAS 读到合法结构化事件后，会额外发布插件事件：

```text
ok_script.event
```

该事件是 ok-script 领域明细事件，不替代 `script.start`、`script.success`、`script.error` 或 `script.exit`。插件需要做生命周期收口时仍应优先监听 `script.exit`；需要查看 ok-script 子任务过程时再监听 `ok_script.event`。
