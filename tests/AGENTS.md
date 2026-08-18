# 测试脚本入口

`tests/` 是 pytest 回归测试目录。测试按被测边界归档，避免把专项适配入口堆在根目录。

## 目录归属

- `tests/api/`：HTTP/API 行为
- `tests/core/`：核心流程与生命周期
- `tests/models/`：配置模型与数据约束
- `tests/services/`：服务层行为
- `tests/task/`：任务调度和专项适配的最小回归测试
- `tests/tools/`：通用工具和外部平台交互
- `tests/` 根目录：跨模块、启动环境或无法归入单一边界的兼容测试
- `scripts/`：需要手动运行的独立诊断/冒烟脚本，不作为 pytest 入口

专项适配测试必须放在 `tests/task/`，文件名使用 `test_<script>_<behavior>.py`。不要在 `tests/` 根目录新增专项适配测试，也不要为同一入口保留副本。

## Agent 规则

- 非必要不新增或提交测试脚本。只有用户明确要求，或修复需要固定可复现回归时才补最小测试。
- 修改专项适配时，先运行对应的最小测试文件；不要默认执行全量测试。
- 最小测试应覆盖被改动的适配边界。没有对应测试时，运行受影响的已有测试并在结果中说明缺口，不为了填目录而补测试。

示例：

```powershell
python -m pytest tests/task/test_maa_depot_maintain.py -q
```
