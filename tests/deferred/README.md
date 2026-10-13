# 延后迁移测试

这些测试保留为旧实现的行为参考，但依赖已废除的 `ConfigBase`、`TaskManager`、旧专项
入口或旧模拟器配置模型。新框架验收不收集本目录；对应专项完成迁移后，再逐项改写为
新配置、TaskDispatcher、插件和 MUMU 契约测试。

- `models/*`：旧配置基类、队列配置及来源校验器测试，待新配置模型迁移完成后重写。
- `task/*`：旧 ScriptAutoProxyBase、SRC 和 Whimbox 专项测试，按专项迁移计划恢复。
- `tools/test_mumu_json_parse.py`：旧 `app.utils.emulator` 解析入口，待新 MUMU 适配器稳定后按插件接口重写。

运行延后测试需显式指定目录，例如：

```powershell
uv run python -m pytest tests/deferred/task/test_whimbox_marker.py -q
```
