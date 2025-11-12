# PopenLogMonitor 使用示例

## 基本用法

```python
import asyncio
from subprocess import Popen, PIPE
from datetime import datetime
from app.utils.LogMonitor import PopenLogMonitor

# 定义回调函数
async def log_callback(log_lines):
    print(f"收到 {len(log_lines)} 行日志")
    for line in log_lines:
        print(line, end='')

# 创建监控器实例
monitor = PopenLogMonitor(
    time_stamp_range=(0, 19),  # 时间戳在日志行的位置范围
    time_format="%Y-%m-%d %H:%M:%S",  # 时间戳格式
    callback=log_callback,
    encoding="utf-8"  # 默认值
)

# 创建进程（确保 stdout 或 stderr 被设置为 PIPE）
process = Popen(
    ["python", "your_script.py"],
    stdout=PIPE,
    stderr=PIPE,
    text=False  # 以字节模式读取，由 monitor 负责解码
)

# 启动监控（默认监控 stdout）
await monitor.start(
    process=process,
    start_time=datetime.now()
)

# 监控 stderr 的例子
await monitor.start(
    process=process,
    start_time=datetime.now(),
    stream_type="stderr"
)

# 等待一段时间或等待进程结束
await asyncio.sleep(10)

# 停止监控
await monitor.stop()
```

## 与原 LogMonitor 的区别

| 特性 | LogMonitor | PopenLogMonitor |
|------|-----------|-----------------|
| 数据源 | 日志文件 (Path) | Popen 实例 |
| start 参数 | `log_file_path: Path` | `process: Popen` |
| 额外参数 | - | `stream_type: "stdout"\|"stderr"` |
| 文件检查 | 检查文件存在性和修改时间 | 检查进程状态 |
| 结束条件 | 手动停止 | 进程结束或手动停止 |

## 注意事项

1. **创建 Popen 时必须将需要监控的流设置为 PIPE**：
   ```python
   process = Popen(..., stdout=PIPE, stderr=PIPE, text=False)
   ```

2. **text 参数应设置为 False**：让 PopenLogMonitor 负责解码，以便正确处理编码问题。

3. **进程结束后监控自动停止**：当进程结束时，monitor 会读取剩余输出并执行最后一次回调，然后自动结束。

4. **时间戳解析**：保持与原 LogMonitor 相同的逻辑，确保日志行格式匹配 `time_stamp_range` 和 `time_format`。

5. **没有时间戳的日志行**：
   - 在 `if_log_start=False` 阶段会被忽略
   - 在 `if_log_start=True` 之后会被正常收集

