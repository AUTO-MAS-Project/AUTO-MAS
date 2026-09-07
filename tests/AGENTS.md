# 测试脚本入口

`tests/` 是 pytest 回归测试目录。测试按被测边界归档，避免把专项适配入口堆在根目录。

## 目录归属

- `tests/api/`：HTTP/API 行为
- `tests/core/`：核心流程与生命周期
- `tests/models/`：配置模型与数据约束
- `tests/services/`：服务层行为
- `tests/platform/`：平台识别、能力声明与不支持能力错误
- `tests/task/`：任务调度和专项适配的最小回归测试
- `tests/tools/`：通用工具和外部平台交互
- `tests/` 根目录：跨模块、启动环境或无法归入单一边界的兼容测试
- `scripts/`：需要手动运行的独立诊断/冒烟脚本，不作为 pytest 入口

专项适配测试必须放在 `tests/task/`，文件名使用 `test_<script>_<behavior>.py`。不要在 `tests/` 根目录新增专项适配测试，也不要为同一入口保留副本。

## Agent 规则

- pytest 在 pyproject 的 `dev` 依赖组中，生产依赖不包含它；本地缺失时执行 `uv sync --group dev` 安装。
- 开发时照旧编写测试用例，用于本地验证与回归；本地验证结果附在 PR 正文，非必要不提交测试文件到 PR。
- 提交或提 PR 时，仅提交重要公共测试与纯逻辑测试；功能边界或 bug 边界的测试不提交。
- 修改专项适配时，先运行对应的最小测试文件；不要默认执行全量测试。
- 合并前必须通过收集门槛：`python -m pytest tests --collect-only -q` 退出码为 0，防止失效测试在合并时静默累积。

示例：

```powershell
python -m pytest tests/models/test_config_base.py -q
```
