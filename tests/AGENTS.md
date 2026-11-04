# 测试脚本入口

`tests/` 是 pytest 回归测试目录。测试按被测边界归档，避免把专项适配入口堆在根目录。

选择验证方式或设计、新增、修改、审查测试前，必须先加载 [mas-testing Skill](../.agents/skills/mas-testing/SKILL.md)。验证选择、测试撰写、自动化复用与去重按该 Skill 执行；目录、运行及隔离方式见下文。

## 目录归属

- `tests/api/`：HTTP/API 行为
- `tests/core/`：核心流程与生命周期
- `tests/models/`：配置模型与数据约束
- `tests/services/`：服务层行为
- `tests/platform/`：平台识别、能力声明与不支持能力错误
- `tests/task/`：任务调度和专项适配的最小回归测试
- `tests/utils/`：无应用上下文的通用工具、文件处理、日志文本内核及结果值
- `tests/tools/`：独立业务工具和外部平台交互
- `tests/scripts/`：仓库维护脚本，例如版本与更新日志生成
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
- 改 `tools/core/` 时先跑它：`uv run --no-sync python -m pytest tests/task/test_maafw_core.py -q`。
  它红了先看是不是改坏了核心；确实要改边界（比如 worker 导入闭包放进新的包），在测试里显式
  改白名单并在 PR 里说明，不要删测试。

## Agent 规则

- 长期测试必须能说清一个独立的产品或逻辑假设，以及假设失效后用户会遇到的错误。例如：修改一项设置不能清空其他设置、重试不能再次执行已完成任务、取消安装不能破坏原来的文件。仅仅“这个函数按当前实现返回了这些值”不是保留依据。
- 保留真正辅助打包、安装和发布的检查，包括隔离运行依赖、跨进程协议、资源交付、版本与公告生成。编译器检查实际消费处；人工构造错误类型来测试检查器、固定内部注册表/模块位置/调用次数的用例不长期保留。
- 测试提交、维护和 PR 验证以[开发文档站规范](https://doc.auto-mas.top/developer/development-specifications.html#测试提交与维护规范)为准。确定、可重复并守护用户行为或公共契约的测试随实现进入同一 PR；不要把测试仓拆成 submodule。
- 测试应隔离外部状态并断言用户可观察行为或公共契约。不要依赖真实账号、游戏、模拟器或未隔离的网络；真实流程按 `docs/testing/e2e.md` 在作者环境运行。
- Bug 有稳定复现时，回归测试应在修复前失败、修复后通过，并随 PR 长期保留。没有新增自动化测试时，在 PR 中说明原因和替代验证。
- PR 验证记录应包含命令、结果、测试的 commit SHA、运行环境和未覆盖范围。凭据、账号数据和未经检查的完整报告不得放入 PR。
- 删除没有独立假设、只复述实现、重复覆盖、行为已移除或无法可靠维护的测试；PR 说明依据。仅约束实现的测试无需补一个同义替代。有效行为被其他场景覆盖时指出替代场景。Flaky 测试需关联问题、负责人和复查日期，临时隔离后应修复、替换或删除，不得靠自动重试掩盖失败或无限期隔离。
- pytest 位于 `pyproject.toml` 的 `dev` 依赖组；本地缺失时执行 `uv sync --locked --group dev`。
- 使用锁定环境运行测试：`uv run --no-sync python -m pytest <路径> -q`。修改专项适配时先运行对应的最小测试文件；完整回归命令为 `uv run --no-sync python -m pytest tests -q`，PR CI 在 Windows 与 Ubuntu 执行完整套件。

## 测试隔离

- 业务调用 core 的全局实例；单元测试可直接导入所属模块的实现类。补丁指向当前调用方查找的符号，不使用已删除的扁平路径。
- `tests/config_support.py` 的 `activate_config` 激活真实配置节点；自动夹具 `isolated_config_roots` 隔离配置持久化根。
- 依赖应用目录的测试显式使用 `isolated_app_paths`，将 Config 的工作、配置、数据等路径指向 tmp_path，源码与资源目录保留原位置；仅 chdir 不会改变已创建的 Config 路径。

示例：

```powershell
uv run --no-sync python -m pytest tests/api/test_config_roundtrip.py -q
```
