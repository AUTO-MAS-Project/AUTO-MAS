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

## 核心最小回归

`tests/task/test_maafw_core.py` 是 MaaFW 通用引擎（`app/task/MaaFW/tools/core/`）的最小回归集。
M9A 等 MFW 特调和直接导入的各个 `interface.json` 项目都跑在这套核心上，它属于根 `AGENTS.md`「分支与 PR」所说的
跨功能通用测试，**进仓库、长期保留**，清理测试时不要删它。

- 范围只到核心，不覆盖专项；只收缺一条就要命的：守的东西一改坏，MFW 运行就成片失败
  （worker / agent 起不来、宿主与 worker 之间的数据传不过去、agent 与 runner 版本对不上之类）。
  单个功能的行为、文案、日志不收。
- 每条都要便宜稳定：秒级以内、不联网、不要模拟器或真实安装包、不建真 venv、不 skip、
  不读源码文本做字符串断言、不断言中文文案。
- 新增一条时在 PR 正文写明：守的是什么、破了怎么炸，以及把被守代码改坏后这条确实会红。
- 改 `tools/core/` 时先跑它：`python -m pytest tests/task/test_maafw_core.py -q`。
  它红了先看是不是改坏了核心；确实要改边界（比如 worker 导入闭包放进新的包），在测试里显式
  改白名单并在 PR 里说明，不要删测试。

## Agent 规则

- pytest 在 pyproject 的 `dev` 依赖组中，生产依赖不包含它；本地缺失时执行 `uv sync --group dev` 安装。
- 开发时照旧编写测试用例并本地运行，把验证命令与结论附在 PR 正文；测试文件能否进 PR 见根目录 `AGENTS.md`「分支与 PR」（默认不提交）。
- 修改专项适配时，先运行对应的最小测试文件；不要默认执行全量测试。
- 合并前必须通过收集门槛：`python -m pytest tests --collect-only -q` 退出码为 0，防止失效测试在合并时静默累积。

示例：

```powershell
python -m pytest tests/models/test_config_base.py -q
```
