# 专项适配模板

这是一套从 `General` 能力线整理出的专项适配骨架。它不是独立运行的脚本，也不依赖专用模板生成器；复制后按注册清单接入 AUTO-MAS 即可。接入新 schema 后，仍按项目流程生成 OpenAPI client。

## 占位符

- `Xxx`：Python/Vue 的 PascalCase 专项名，例如 `MaaDemo`。
- `xxx`：路径、测试和路由使用的 kebab-case 或 snake_case 名，例如 `maa_demo`。
- `专项显示名称`：用户界面和日志中的中文名称。

全局替换时请同时检查大小写和中文显示名。`Xxx` 不是最终的 `ScriptType`，最终类型名必须与注册表、路由、schema 和任务调度完全一致。

## 目录说明

```text
templates/specialized/
├─ README.md
├─ backend/
│  ├─ task/Xxx/
│  │  ├─ __init__.py
│  │  ├─ AutoProxy.py
│  │  ├─ manager.py
│  │  └─ ScriptConfig.py
│  ├─ config.py.template
│  ├─ schema.py.template
│  └─ registration-checklist.md
├─ frontend/
│  ├─ XxxScriptEdit.vue
│  ├─ XxxUserEdit.vue
│  └─ XxxUserEdit/
│     ├─ BasicInfoSection.vue
│     └─ NotifyConfigSection.vue
└─ tests/
   └─ test_xxx_autoproxy.py
```

后端任务文件保留了 General 的启动、进程追踪、配置交换、游戏/模拟器启动、重试/超时、前后置脚本、日志判态、用户统计、历史记录、通知和 `final_task` / `on_crash` 生命周期。专项差异集中在 `TODO(specialized)` 处；不要把 TODO 留在可运行路径上。

## 五步使用流程

1. 复制 `backend/task/Xxx` 到 `app/task/新专项名`，并全局替换 `Xxx`、`xxx` 和显示名称。
2. 复制 `backend/config.py.template`、`backend/schema.py.template` 的片段，填写真实专项字段和验证器。
3. 复制两个前端编辑页及 `XxxUserEdit/`，保留基本信息、通知和通用配置会话，加入专项表单。
4. 按 `backend/registration-checklist.md` 补齐 `ScriptType`、`BOOK`、API/core/task 调度、路由、Hub 和前端类型分支。
5. 将 `tests/test_xxx_autoproxy.py` 移入 `tests/task/test_xxx_autoproxy.py`，替换夹具并运行最小专项测试。

前端通常放置为：`XxxScriptEdit.vue` → `frontend/src/views/EditView/Script/`，`XxxUserEdit.vue` → `frontend/src/views/EditView/User/`，`XxxUserEdit/` → `frontend/src/views/XxxUserEdit/`；页面中的相对 import 已按该目录关系书写。

## 设计边界

- `schema.py` 只描述 API 数据；文件、进程、日志和配置交换留在 task/core。
- `config.py` 中的所有 `ConfigItem` 必须在 `super().__init__()` 前声明，并配有注释。
- 用户配置来源默认沿用 General 的“用户独立 / 脚本直控”两态。若上游真实存在脚本共享或其他 owner，先在专项设计中确认，再同步 config、UI、AutoProxy 和 ScriptConfig；不要为了界面统一臆造第三种模式。
- 运行前备份脚本直控配置，运行中按用户配置原子替换，成功、失败、取消、超时和异常均恢复原配置。需要把运行结果写回用户配置时，必须先更新用户副本，再恢复直控配置。
- 日志监控使用 `LogMonitor(time_stamp_range, time_format, check_log)` 三参构造；每一轮创建 `LogRecord`，只写 `log_record.status`，不要给 `UserItem.result` 赋值。
- 生成的 OpenAPI 文件不得手改。schema 接入后由开发者从 `frontend/` 运行 `yarn openapi`。

## 必填专项决策

复制前先写下四个答案：

1. 脚本根目录、主程序和目标进程的真实哨兵文件是什么？自动发现和手动选择必须复用同一组哨兵。
2. 自动任务的启动参数如何构造？没有稳定 CLI 时，改为写入上游约定的运行配置，不要猜参数。
3. 哪些配置由上游脚本拥有，哪些由 MAS 用户副本拥有？配置会话、AutoProxy 和恢复逻辑必须一致。
4. 哪些日志明确代表成功、失败、运行中和提前退出？把失败/回退路径写入测试。

## 验证

```powershell
# 后端：在替换占位符并完成注册后
python -m pytest tests/task/test_xxx_autoproxy.py -q

# 前端：接入 schema 后由开发者执行生成器，再检查类型和 lint
yarn openapi
yarn lint
```

模板本身只提供最小纯逻辑回归测试；未完成上游契约、注册和夹具替换前，不要把模板测试当作专项已适配的证明。
