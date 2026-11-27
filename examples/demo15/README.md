# Demo15 声明式编辑器示例

将本目录复制到 AUTO-MAS 的 `plugins/demo15/`，启动宿主，在插件中心启用 `demo15`。三个编辑器共用插件的配置翻译前缀 `plugins.demo15.config`。

| 对象 | 创建请求 | 详情和保存 |
| --- | --- | --- |
| 托管 | `POST /api/scripts/add`，提交 `{"type":"Demo15"}` | `/api/scripts/get`、`/api/scripts/update` 使用返回的 `scriptId` |
| 账号 | `POST /api/scripts/user/add`，提交 `scriptId` | `/api/scripts/user/get`、`/api/scripts/user/update` 使用 `scriptId` 和 `userId` |
| 计划 | `POST /api/plan/add`，提交 `{"type":"Demo15PlanConfig"}` | `/api/plan/get`、`/api/plan/update` 使用返回的 `planId` |

详情返回顶层 `ui` 和按 ID 索引的 `data`。保存时提交相同的 ID，把改动的分组字段放入 `data`。例如 `{"First":{"Count":3}}` 修改第一个任务的执行次数。计划通过两个同型的 `ConfigTableColumn` 分组声明表格，`_table_transpose = True` 让每个任务占一行。

托管的重试次数最小为 0，执行方式提供两个选项。关闭账号的「使用密码」会隐藏密码字段。密钥和密码使用宿主的掩码与加密存储，原样回传掩码会保留原值。

在宿主仓库根目录运行 `uv run --no-sync pytest -q tests/api/test_generic_declarative_editors.py`。

## OpenAPI 同步

- 示例配置模型为 `Demo15Config`、`Demo15UserConfig`、`Demo15PlanConfig`，启用插件时同步生成各自的输入投影。
- 新增共享模型 `DeclarativeConfigUi`、`DeclarativeConfigGetOut`（Python 响应基类）、`ConfigUpdateOut`。
- 更新详情响应 `ScriptGetOut`、`UserGetOut`、`PlanGetOut`。
- 更新请求 `ScriptUpdateIn`、`UserUpdateIn`、`PlanUpdateIn`，保留计划输入联合 `PlanConfigDataInput`。
- 插件设置更新响应 `PluginConfigUpdateOut` 继承 `ConfigUpdateOut`，保留原 OpenAPI 模型名。
