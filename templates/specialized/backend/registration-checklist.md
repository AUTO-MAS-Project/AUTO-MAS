# 专项注册清单

复制模板后逐项勾选。没有真实消费者的字段、按钮或模式不要注册。

## 1. 配置与 schema

- [ ] 将 `XxxConfig`、`XxxUserConfig` 复制进 `app/models/config.py`，所有 `ConfigItem` 位于 `super().__init__()` 前。
- [ ] 将 `Xxx*` schema 复制进 `app/models/schema.py`，补齐真实专项字段、`Literal` 和描述。
- [ ] `Config.ScriptConfig` / `GlobalConfig` / 相关 `MultipleConfig` 允许新类型。
- [ ] `app/models/config.py` 的类映射、序列化和默认配置分支包含新类型。
- [ ] `app/utils/constants.py` 的 `TYPE_BOOK["XxxConfig"]` 有用户可见文案。

## 2. API 与核心调度

- [ ] `app/api/scripts.py` 的 `SCRIPT_BOOK` 增加 `XxxConfig`。
- [ ] `app/api/scripts.py` 的 `USER_BOOK` 增加 `XxxConfig: XxxUserConfig`。
- [ ] 任何专项 API 只做请求校验/响应整形；文件交换、任务循环和日志判态留在 core/task。
- [ ] `app/core/config.py` 的加载、创建、删除、用户增删和类型 union 分支包含新类型。
- [ ] `app/core/task_manager.py` 导入 `XxxManager`，在脚本类型 dispatch 中注册。
- [ ] 若接入计划表/任务队列，单独补 `PLAN_BOOK`、consumer、队列类型和对应前端表面；不要复制无关专项能力。

## 3. 任务模块

- [ ] 将 `task/Xxx/` 复制到 `app/task/Xxx/`，并全局替换类名、导入和 logger。
- [ ] `manager.py` 的 `METHOD_BOOK` 至少包含 `AutoProxy` 与 `ScriptConfig`，并核对任务模式是否真实支持。
- [ ] `AutoProxy.py` 的 `check()` 使用用户可操作的失败提示。
- [ ] `AutoProxy.py` 的 `LogMonitor` 使用时间范围、时间格式、回调三参构造。
- [ ] 每轮从 `log_record[start_time] = LogRecord()` 开始，只写 `log_record.status`。
- [ ] `final_task` 与 `on_crash` 都停止监控、停止/清理进程、恢复配置、释放锁，并在需要时写历史记录。
- [ ] 进程追踪至少有一个非空 `ProcessInfo` 字段；不要把空追踪条件交给运行时猜测。
- [ ] 配置目录/文件复制使用临时路径后替换；逐步清理失败分别记录日志。
- [ ] 多用户任务中单个用户检查失败只标记当前用户并继续后续用户。

## 4. 前端 Hub、路由和类型

- [ ] `frontend/src/types/script.ts` 增加 `ScriptType`、脚本/用户结构和默认值。
- [ ] `frontend/src/composables/useScriptApi.ts` 增加脚本类型映射、默认配置和 `XxxUserConfig -> users[]` 分支。
- [ ] `frontend/src/router/index.ts` 增加脚本编辑、用户新增、用户编辑路由；路径使用 lowercase kebab-case。
- [ ] `frontend/src/views/Scripts.vue` 的编辑、添加用户、编辑用户、创建/复制脚本分支全部补齐。
- [ ] `frontend/src/components/ScriptTable.vue` 增加图标、类型文案和专项操作（若确有专项动作）。
- [ ] `frontend/src/views/EditView/Script/XxxScriptEdit.vue` 与 `EditView/User/XxxUserEdit.vue` 接入真实 API。
- [ ] 新增用户流程先 `addUser`，再 `router.replace` 到带 `userId` 的编辑路由。
- [ ] 若使用 ScriptConfig 遮罩，启动、完成、错误、取消、超时、卸载都停止任务并清理 WebSocket 订阅。
- [ ] 自动发现与手动选择复用同一组哨兵文件；保存失败恢复旧值并显示原因。

## 5. 生成代码与验证

- [ ] 后端 schema 接入并重启后，确认 `openapi.json` 文本包含 `XxxConfig` / `XxxUserConfig`。
- [ ] 在 `frontend/` 运行 `yarn openapi`；禁止手改 `frontend/src/api/**`。
- [ ] 将测试移动到 `tests/task/test_xxx_autoproxy.py`，替换占位夹具，先运行该最小文件。
- [ ] 前端改动至少运行 `yarn lint`；路由/类型/构建改动再运行相关 build/type 命令。
- [ ] 版本记录在 `res/version.json` 下一个未发布版本中，说明新增专项模板或用户可见能力。
