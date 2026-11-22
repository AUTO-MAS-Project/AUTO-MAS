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

MFW 通用引擎（两块库与三块积木）和 MFW、M9A、MSS 三个专项已改由插件包提供，源码在
[AUTO-MAS-MaaFW](https://github.com/AUTO-MAS-Project/AUTO-MAS-MaaFW) 与三个专项仓库，原先的
`tests/task/test_maafw_core.py` 核心最小回归随实现一起交给积木仓库维护，宿主不再放 MFW 引擎的测试。

宿主这边只守升级链路：识别旧的 MFW 族托管与计划表类型、首次接手前的专属备份、插件装不上时托管旁挂保留，
用例在 `tests/core/test_plugin_config_upgrade.py`。

## Agent 规则

- 测试提交、维护和 PR 验证以[开发文档站规范](https://doc.auto-mas.top/developer/development-specifications.html#测试提交与维护规范)为准。先按 [mas-testing](../.agents/skills/mas-testing/SKILL.md#先判断是否值得长期保留)判断长期收益，通过该判断的确定、可重复行为或契约测试随实现进入同一 PR；不要把测试仓拆成 submodule。
- 测试应隔离外部状态并断言用户可观察行为或公共契约。不要依赖真实账号、游戏、模拟器或未隔离的网络；真实流程按 `docs/testing/e2e.md` 在作者环境运行。
- 值得长期守护的 Bug 有稳定复现时，回归测试应在修复前失败、修复后通过，并随 PR 长期保留。一次性验证不自动转为长期测试。仅在新增测试时，在 PR 中列出测试路径，并说明它能发现哪个现有测试会漏掉的真实问题。
- PR 验证记录应包含命令、结果、测试的 commit SHA、运行环境和未覆盖范围。凭据、账号数据和未经检查的完整报告不得放入 PR。
- 存量清理按 [mas-testing 的保留举证规则](../.agents/skills/mas-testing/SKILL.md#存量与交付)，先从实际交互选择故障与最小保留集；没有具体场景或持续收益的检查可退出，不要求逐条迁移。PR 说明退出依据、实际留下的覆盖和缺口；高损失保证须有等效或更强证据，明确受保护用例继续保留。Flaky 测试需关联问题、负责人和复查日期，临时隔离后应修复、替换或删除，不得靠自动重试掩盖失败或无限期隔离。
- pytest 位于 `pyproject.toml` 的 `dev` 依赖组；本地缺失时执行 `uv sync --locked --group dev`。
- 首次运行主仓专项集成测试前，执行 `uv run --no-sync python scripts/prepare_test_plugins.py`，按 `tests/requirements-plugins.txt` 的版本与摘要准备隔离发行包。插件开发及 Runtime 目录边界见 [插件开发说明](../docs/plugin-development.md)。
- 使用锁定环境运行测试：`uv run --no-sync python -m pytest <路径> -q`。修改专项适配时先运行对应的最小测试文件；完整回归命令为 `uv run --no-sync python -m pytest tests -q`，PR CI 在 Windows 与 Ubuntu 执行完整套件。

## 测试隔离

- 业务调用 core 的全局实例；单元测试可直接导入所属模块的实现类。补丁指向当前调用方查找的符号，不使用已删除的扁平路径。
- `tests/config_support.py` 的 `activate_config` 激活真实配置节点；自动夹具 `isolated_config_roots` 隔离配置持久化根。
- 依赖应用目录的测试显式使用 `isolated_app_paths`，将 Config 的工作、配置、数据等路径指向 tmp_path，源码与资源目录保留原位置；仅 chdir 不会改变已创建的 Config 路径。
- 默认使用 pytest 的临时目录；手动指定 `--basetemp` 时使用仓库外的独立目录。放在仓库内会使路径字段把临时安装或脚本路径判为应用目录的子路径并清空，不要通过关闭路径校验消除这类失败。
- 激活含 `ref` 的配置前，夹具应先登记并激活对应的引用集合，结束后恢复登记；不要依赖其他测试导入应用全局实例时的初始化副作用。

示例：

```powershell
uv run --no-sync python -m pytest tests/models/test_queue_config.py -q
```
