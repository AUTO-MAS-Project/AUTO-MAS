# MAS 插件 ctx 补全与 pyi 生成指南

> 版本：v1.0  
> 生效日期：2026-03-27  
> 适用范围：AUTO-MAS 插件开发阶段（后端 + VS Code/Pylance）

## 1. 目标

本文档用于说明：

- 如何生成插件开发用的 `.pyi` 类型提示文件；
- 修改输出目录后，如何重新生成；
- 插件代码里如何标注 `ctx` 才能获得补全与签名提示；
- 常见“没有补全”的排查方式。

## 2. 当前实现概览

当前后端已内置生成器：

- 代码位置：`app/core/plugins/dev_stub_generator.py`
- 生成函数：`generate_plugin_context_stubs()`
- 开发模式开关：`AUTO_MAS_DEV`

当前默认输出目录（已调整）：

- `plugins/_generated/`

生成文件包括：

- `plugins/_generated/__init__.pyi`
- `plugins/_generated/context.pyi`
- `plugins/_generated/runtime_api.pyi`
- `plugins/_generated/cache_store.pyi`

## 3. 如何重新生成 pyi

### 3.1 命令行手动生成（推荐）

在项目根目录执行：

```powershell
d:/Dev/AUTO-MAS/.venv/Scripts/python.exe -c "from app.core.plugins.dev_stub_generator import generate_plugin_context_stubs; print(generate_plugin_context_stubs())"
```

成功后会输出：

- `output_dir`：生成目录
- `changed_files`：本次有变更的文件
- `unchanged_files`：本次无变更的文件

### 3.2 启动后端时自动生成

设置环境变量后启动后端：

```powershell
$env:AUTO_MAS_DEV = "1"
d:/Dev/AUTO-MAS/.venv/Scripts/python.exe main.py
```

当 `AUTO_MAS_DEV` 为 `1/true/yes/on`（不区分大小写）时，后端启动流程会自动执行一次生成。

### 3.3 使用后端接口手动重建

接口：

- `POST /api/plugins/dev/rebuild_ctx_stub`

说明：

- 开发模式下可直接调用；
- 非开发模式可传 `force=true` 强制触发。

## 4. 插件中如何拿到补全

推荐在插件中为 `ctx` 显式标注类型（开发期类型导入）：

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.plugins.context import PluginContext


async def setup(ctx: "PluginContext") -> None:
    cache = ctx.cache.register(
        cache_name="test_cache",
        backend="json",
        limit=10,
        limit_mode="count",
    )
    cache.set("test_cache", {"1": "2"})
    ctx.logger.info(f"缓存写入成功: {cache.get('test_cache')}")
```

这样可以获得：

- `ctx.runtime` / `ctx.runtime_api` 的方法签名提示；
- `ctx.cache.register(...)` 参数提示；
- 相关方法 docstring 提示。

## 5. 常见问题排查

### 5.1 我改了后端代码，但提示没更新

按顺序处理：

1. 重新执行一次 `generate_plugin_context_stubs()`；
2. 确认 `plugins/_generated/*.pyi` 的修改时间已更新；
3. 在 VS Code 执行 `Python: Restart Language Server`。

### 5.2 有类型标注但还是没补全

检查项：

1. 插件文件是否写了 `ctx: "PluginContext"`；
2. `TYPE_CHECKING` 下导入路径是否可解析；
3. 当前工作区解释器是否是项目 `.venv`；
4. 是否误在其他同名工作区打开了插件文件。

### 5.3 生成失败会影响主流程吗

不会。当前设计是：

- 自动生成失败仅记录日志 warning；
- 不阻断后端服务启动与插件加载。

## 6. 维护建议

- 仅在开发环境启用自动生成；
- 接口侧保留手动重建能力，便于快速刷新；
- 当 `PluginContext/RuntimeAPI/Cache` 对外方法变更后，执行一次重建并确认 IDE 提示是否同步。


如果你是手动直接跑 main.py（不是由 Electron 拉起），那不会自动注入变量。此时请先设置环境变量再启动：
PowerShell: $env:AUTO_MAS_DEV="1" 后再运行后端。