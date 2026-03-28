# 脚本适配结构图

## 入口关系

- `app/core/task_manager.py`：按脚本配置类型分派到 `MaaManager`、`SrcManager`、`GeneralManager`、`MaaEndManager`。
- `app/task/<类型>/manager.py`：该脚本类型的总控入口，负责校验、准备、循环执行、收尾和崩溃处理。
- `app/task/<类型>/AutoProxy.py`：自动代理主流程，对单个用户执行完整自动流程。
- `app/task/<类型>/ManualReview.py`：人工复核流程，对单个用户拉起环境并等待人工确认。并非所有类型都支持。
- `app/task/<类型>/ScriptConfig.py`：脚本配置生成或保存流程，对单个用户生成、整理并回存配置文件。
- `app/task/<类型>/tools/`：该脚本类型特有工具函数。

## manager 常见结构

### `check()`

- 校验任务模式是否合法。
- 校验 `Config.ScriptConfig[...]` 的类型是否匹配。
- 校验模拟器、可执行文件、配置文件、默认配置目录等是否齐全。
- 返回 `Pass` 或错误文本。

### `prepare()`

- 锁定脚本配置，避免并发运行。
- 加载脚本级与用户级配置。
- 初始化模拟器管理器或其他运行依赖。
- 备份原始配置到 `data/<script_id>/Temp`。
- 按任务模式构造用户列表。

### `main_task()`

- 先执行 `check()`。
- 再执行 `prepare()`。
- 逐个用户或条目创建对应子任务并 `spawn()`。

### `final_task()`

- 解锁脚本配置。
- 根据模式选择是否回写用户配置。
- 汇总成功、异常、等待用户数量。
- 推送通知。
- 恢复原始配置并删除临时目录。

### `on_crash()`

- 标记脚本状态异常。
- 记录日志。
- 通过 WebSocket 推送错误信息。

## 用户级子任务职责

### `AutoProxy`

- 负责单用户自动执行。
- 常见步骤：用户级校验、日切重置、环境启动、配置注入、脚本运行、日志监控、重试或收尾。
- 常见依赖：`ProcessManager`、`LogMonitor`、模拟器管理器、脚本类型工具函数。
- 常见副作用：更新 `ProxyTimes`、更新 `LastProxyDate`、写入日志历史记录、更新用户状态与脚本状态。

### `ManualReview`

- 负责单用户人工复核。
- 常见步骤：拉起模拟器/客户端、构造人工检查场景、通过 `Broadcast` / WebSocket 发起问题、等待前端选择、根据人工确认结果更新状态。
- 常见依赖：`Broadcast`、等待事件、交互问题消息、可见窗口控制。
- 常见副作用：等待用户输入、记录人工确认结果、保留错误或放行状态。

### `ScriptConfig`

- 负责单用户配置生成与回存。
- 常见步骤：停止旧进程、拷贝已有用户配置、写脚本配置文件、启动脚本、结束后把配置目录保存回 `data/<script_id>/<user_id>/ConfigFile`。
- 脚本配置方法：注入脚本配置文件时，可能需要靠修改关键配置项来防止启动脚本进程供用户修改配置时，脚本自动运行任务。
- 常见副作用：覆盖脚本配置目录、写入用户配置缓存、影响后续 `AutoProxy` / `ManualReview` 的运行基础。

## MAA 与 SRC 现有共性

- 都依赖模拟器配置。
- 都会备份脚本原始 `config` 目录。
- 都支持 `AutoProxy`、`ManualReview`、`ScriptConfig`。
- 都在 `final_task()` 中进行通知推送与配置回滚。

## MAA 与 SRC 现有差异

- MAA 检查 `MAA.exe` 与 `config/gui.json`、`config/gui.new.json`。
- SRC 检查 `src.exe`、`config/*.json` 与 `config/deploy.yaml`。
- MAA 的 `AutoProxy` 更重日志解析、任务编排与签到；SRC 的 `AutoProxy` 更重登录、配置写入和日志文件发现。
- MAA 与 SRC 的 `ScriptConfig` 改写的配置文件不同，因此不要直接复制字段写法。

## 设计建议

- 新脚本类型如果流程与 MAA/SRC 类似，优先复用这类 manager 结构。
- 共性逻辑够稳定时再抽公共层，不要为了“看起来优雅”过早合并。
- 只要改动影响任务类型分派，就同步检查 `TaskManager`。
- 只要改动影响用户级子任务，就同步检查 manager 的用户循环、结果汇总和回写流程。