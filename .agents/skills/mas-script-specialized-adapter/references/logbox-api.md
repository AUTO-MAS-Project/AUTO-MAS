# 文本处理与调用方采集边界

## 公共能力

- `from app.utils import log_box`：纯文本规则处理及结果类型。
- `from app.utils.common.log import sources`：独立增量文件读取，不读配置或环境变量。
- `from app.utils import i18n`：既有 `PoTranslator`，由调用方选择词表并管理资源。
- `from app.core.notify import report`：逐条、汇总和用户报告的纯文本排版。

不再提供 `LogCollect`、`LogBox`、`LogSpec`、`EntrySpec`、`LogBinding`、
`TranslationSpec`、`SessionResult` 或用户托管会话。旧 `app.log_box` 路径已删除，
没有兼容转发。结构化来源直接由专项转换、校验和交付，不经过文本处理器。

## 文本内核

```python
from app.utils import log_box

pipeline = log_box.LogPipeline()
pipeline.add_rule(r"完成:", r'"节点: " + $((?:完成: )(.+))', "普通")
pipeline.feed("完成: 邮件", timestamp=recorded_at)
entries = pipeline.finish()
```

规则按顺序匹配，单行返回第一个命中结果。空表达式保留处理后的原行。
`preprocessors` 接收文本并返回文本或 None；`postprocessors` 接收、返回
`(log_type, text, timestamp)` 三元组列表。专项状态归并仍由专项自己的处理器实现。
多行规则可通过 `scope_rules` 使用既有 `MultiLineAggregator`。

时间戳由调用方传入；省略为 None，内核不调用时钟。多行窗口收尾保留最后输入的时间戳。
结果 `LogEntry` 只保存类型、文本和时间，不解释成功失败标记。`finish()` 重复调用返回
同一批不可变结果的列表副本，不重复执行后处理；完成后不能继续 `feed()`。
非法规则、处理器错误和结果形状错误向调用方抛出，不写兜底文案、用户状态或通知。

## 文件来源和翻译

```python
from app.utils.common.log import sources

source = sources.LogSource(path, start_from_end=True, rotated_name=rotation_template)
source.open()
# 此后由专项按自己的生命周期读取。
for line in source.read_new():
    pipeline.feed(line, timestamp=recorded_at)
```

在脚本开始写日志之前记录偏移。轮转、截断、完整行解码由文件工具负责；文件路径、
起点、轮转模板、读取频率、采集开关均由调用方决定。工具不读取 `MAS_SCRIPT_LOG_PATH`。

词表由专项显式加载，将 `translator.translate` 加入 `pipeline.preprocessors`。
如放到工作线程，调用方必须先等待线程和交付完成，再清理词表，不能因取消提前清理。

## 专项职责

调用方固定用户/账号快照，选择读取和处理的线程，在宿主事件循环写入结果。
同一次运行收尾必须幂等，重复或并发收尾不能重复交付；取消时先等待已启动的后台处理
及交付结束，再传播取消。异常是否影响专项、是否追加旧兜底文案，均由专项决定。
不能把这套策略重新放进公共的“采集会话”。

当前 OK-WW/OK-NTE/BAAH 在各自 AutoProxy 中实现读取和收尾；ZZZ-OD 在收尾开始时复制
当前目录和账号映射，并保留账号模式过滤与无归属回退；MaaEnd 自行回扫阶段日志并管理
临时目录；BetterGI 直接转换已有分步表并交付，不模拟日志来源。
通用脚本的 `@@LOGBOX@@` 编解码与 stdout 回传位于它自己的 `log_protocol.py`。

## 报告

业务层选择关闭/逐条/汇总，按任务状态筛选失败类型，计算完成数并选择通知目标。
`report.render_scatter_push_log()` 和
`render_aggregate_push_log()` 只排版传入条目；`render_user_result_text()` 只接收
`models.notification.report.UserReportText` 中已经确定的用户名、结果和详情行。
节点状态标记模型 `Node` 位于报告模型中，不能再通过通用 `LogEntry.node` 解释业务状态。
调度台日志更新由持有脚本对象的 manager 直接完成；任务完成页统计由 core/task_manager 负责。

## 最小回归

```text
uv run --no-sync python -m pytest tests/utils/test_log_box_pipeline.py tests/utils/test_log_box_sources.py tests/core/test_notification_reports.py tests/task/test_general_report_policy.py tests/models/test_notification_report.py tests/utils/test_log_box_results.py tests/task/test_log_capture_lifecycle.py tests/task/test_log_box_adapter_sessions.py tests/task/test_zzzod_log_box_session.py tests/task/test_oknte_log_box_session.py tests/task/test_bettergi_log_box_session.py tests/task/test_node_report_policy.py tests/task/test_maafw_core.py -q
```

旧会话、EntrySpec 和 SessionResult 测试随接口移除；处理错误传播由纯内核测试覆盖，
线程/交付/取消/异常策略由真实专项调用方测试覆盖，账号路由和输出格式继续保留回归。
没有真实脚本、账号或通知渠道时，不将自动测试声明为实机验证。
