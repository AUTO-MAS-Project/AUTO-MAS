# `app/task/HSR` 说明

本文件只记录代码里读不出来、但改错了会出事的约束。

## API 业务归属

- `api_service.py`：`/api/scripts/hsr/*` 端点背后的全部业务（脚本 / 用户解析、体力副本选项、
  能力快照、M7A / SRA 手动更新、云·星穹铁道登录、托管配置字段、SRA 配置档案）。
  **HSR 的 API 业务一律在这里实现，`app/api/scripts.py` 只放薄端点**：取参数 → 调这里的一个
  函数 → `XxxOut(**reply.out_fields())`（`HSRApiReply`）或把异常映射成 HTTP 错误；不在 API 层
  定义 HSR 私有辅助函数、常量或锁。
- 依赖只能 `app.api` → `app.task.HSR`，反向导入 `app.api` 禁止。
- 端点 docstring 会进 OpenAPI 生成物，搬业务时留在端点上原样不动。
- 端点在函数体内惰性导入 `api_service`：`app/task/__init__.py` 按需加载各专项，宿主启动时
  不导入 HSR，别改成模块顶层导入。`api_service` 对 `tools.*` 的导入留在各函数的 `try` 里，
  导入失败与业务异常由同一个 `except` 映射成错误响应。
- 日志模块名沿用「脚本管理 API」，失败日志前缀仍是端点函数名（如 `get_hsr_capabilities_api失败`）。
