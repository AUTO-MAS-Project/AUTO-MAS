# 测试目录与运行说明

`tests/` 为 pytest 回归测试目录，按被测边界分目录归档。新增、修改或审查测试前须先加载 [mas-testing Skill](../.agents/skills/mas-testing/SKILL.md)，测试提交与维护以[开发文档站规范](https://doc.auto-mas.top/developer/development-specifications.html#测试提交与维护规范)为准。

## 目录归属

- `tests/api/`：HTTP / API 行为
- `tests/core/`：核心流程与生命周期
- `tests/models/`：配置模型与数据约束
- `tests/services/`：服务层行为
- `tests/platform/`：平台识别与能力声明
- `tests/task/`：任务调度与专项适配最小回归（命名 `test_<script>_<behavior>.py`，勿放根目录）
- `tests/utils/`：无应用上下文的通用工具、文件处理与日志内核
- `tests/tools/`：独立业务工具与外部平台交互
- `tests/scripts/`：仓库维护脚本（版本与更新日志生成等）
- `tests/` 根目录：跨模块或启动环境兼容测试
- `scripts/`：需手动运行的诊断/冒烟脚本，不作为 pytest 入口

## 运行命令

```powershell
# 安装开发依赖（首次或锁文件变更后）
uv sync --locked --group dev

# 首次运行专项集成测试前准备锁定插件 wheel
uv run --no-sync python scripts/prepare_test_plugins.py

# 运行单个测试文件或完整套件
uv run --no-sync python -m pytest tests/models/test_queue_config.py -q
uv run --no-sync python -m pytest tests -q
```

## 核心最小回归（MFW 族）

MFW 通用引擎（两块库与三块积木）和 MFW、M9A、MSS 三个专项已改由插件包提供，源码在 [AUTO-MAS-MaaFW](https://github.com/AUTO-MAS-Project/AUTO-MAS-MaaFW) 与三个专项仓库；原先的 `tests/task/test_maafw_core.py` 核心最小回归随实现一起交给积木仓库维护，宿主不再放 MFW 引擎的测试。

- 宿主只守升级链路：识别旧的 MFW 族托管与计划表类型、首次接手前的专属备份、插件装不上时托管旁挂保留，用例在 `tests/core/test_plugin_config_upgrade.py`。

## 编写与隔离规范

- **隔离外部状态**：断言用户可观察行为或公共契约，不依赖真实账号、游戏、模拟器或外网（真实流程按 `docs/testing/e2e.md` 在本机运行）。
- **常用测试夹具**：
  - `activate_config`（`tests/config_support.py`）与自动夹具 `isolated_config_roots`：激活并隔离配置持久化根。
  - `isolated_app_paths`：将工作、配置、数据目录重定向至 `tmp_path`（仅 `chdir` 不会改变已创建的 Config 路径）。
  - 激活含 `ref` 的配置前须显式登记并激活目标引用集合，结束后恢复。
- **临时目录位置**：使用默认 pytest 临时目录；手动传 `--basetemp` 时须指向仓库外路径，避免路径校验将临时目录误判为应用子路径而清空。
- **维护与清理**：可稳定复现的高价值 Bug 须配“修复前红、修复后绿”的回归测试；Flaky 测试须关联问题与负责人，不可靠自动重试或无限期 skip 掩盖。PR 验证记录须包含命令、结果、commit SHA、环境与未覆盖范围，严禁包含凭据或未脱敏报告。
