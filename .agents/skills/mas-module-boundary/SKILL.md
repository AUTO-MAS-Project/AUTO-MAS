---
name: mas-module-boundary
description: Define and enforce backend module boundaries for Python services. Use when adding or refactoring backend code under app/, reviewing dependency direction, deciding layer ownership, or preventing logic leakage across schema/api/core/services/task/utils modules.
---

# MAS Module Boundary

先按用途定层，再按复杂度决定单文件或文件夹（不能因单文件而放到 `app/` 顶层）。修改归属时同步迁移调用点，不保留兼容壳。

## 后端分层与依赖红线

| 目录 | 职责 | 依赖与组织红线 |
| --- | --- | --- |
| `app/api/` | 拆解校验输入、调业务、装响应与错误 | 薄路由；端点 `*In`/`*Out` 放文件顶部，跨模块契约放 `app/models/schema.py`；不承载业务/文件/脚本逻辑 |
| `app/core/` | 全局单例核心组件（`from app.core import Config, Notify, MainTimer`） | 简单组件单文件放 `core/`；复杂组件用 `core/<name>/`；仅当应用扩展极复杂时才建 `app/<基础层>/`（如 `app/config/` 与 `app/core/config/`）；路径统一用 `Config.<xxx>_path / ...`；`core/__init__.py` 保持懒加载 |
| `app/models/` | 共享数据结构、契约、配置领域声明（`models/config/`） | 不依赖 `api`/`core`/`services`/`task`；**唯一例外**：任务运行模型的状态/日志推送直接在模型后声明 Config 类订阅（导入不得初始化宿主） |
| `app/services/` | 跨平台业务服务 | 允许调用 `core` 等公开能力；服务自身实现须集中在本服务文件/包内，不反向依赖 `app/api/` 处理器 |
| `app/utils/` | 无业务上下文的通用工具 | **严禁导入 `core`/`models`/`services`/`tools`/`task`/`api`/`config` 等任何其他 `app` 源码**（含 `TYPE_CHECKING` 与函数内延迟导入）；只收参数、返结果 |
| `app/tools/` | 业务独立的工具功能（如社区签到） | **每项功能必须独立文件夹**（即使单文件）；只允许导入本文件夹与 `app/utils/`，专用模型留内部，不反向调宿主 |
| `app/task/` | 任务执行与旧专项（随插件化逐步移除） | 调度骨架与锁遵循 `mas-task-scheduler`，旧 manager 仅在 L2 分叉 |
| `app/mystery/` | 高级功能占位 | 仅限该用途，不收纳无关代码 |

## 跨平台与契约

- `utils`/`services`/`tools` 对外暴露统一接口，平台差异留在内部。静态类型提示必须引用契约（或无差异时的 `common` 实现），禁止按开发机平台直接导入具体实现。
- 平台契约校验位于 `tests/platform/typing_contracts.py`，用 `mypy-platform.ini` 分别检查 `win32`/`linux`/`darwin`。
- 检查导入边界时同步排查顶层导入、`TYPE_CHECKING`、函数内延迟导入与动态模块路径。
