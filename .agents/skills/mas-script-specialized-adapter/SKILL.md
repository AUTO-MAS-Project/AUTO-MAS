---
name: mas-script-specialized-adapter
description: >-
  Review, add, or refactor AUTO-MAS specialized script adapters by upstream
  architecture, including MAA, SRC, MaaEnd/MXU, M9A/MFAA, General, and
  ok-script adapters such as Okww. Use for ScriptType registration, task
  lifecycle, config ownership, ScriptConfig sessions, Electron integration,
  frontend edit surfaces, and adapter verification.
---

# 专项适配

## 开工顺序

1. 获取上游仓库或发行版信息，确认 CLI、进程、日志、配置目录和配置 UI。
2. 对照 [脚本前端架构](references/script-frontend-architectures.md) 归类，并让用户确认架构线与展示文案。
3. 读取 [专项适配代码规范](references/adapter-code-norms.md) 和对应案例：
   - SRC：[examples-src.md](references/examples-src.md)
   - MaaEnd / MXU：[examples-maaend.md](references/examples-maaend.md)
   - M9A / MFAA：[examples-m9a.md](references/examples-m9a.md)
   - Okww / ok-script：[examples-okww.md](references/examples-okww.md)
4. 检查相邻实现与所有注册调用者，再决定最小改动。不要从旧 Skill 文案推断当前行为。

前端任务同时加载 `mas-frontend-standards`；涉及 UI、表单、遮罩或反馈时再加载 `mas-frontend-ui`。

## 完整落点

新增或维护 `ScriptType` 时，按实际需要核对以下切面：

- 配置与 schema：`app/models/config.py`、`app/models/schema.py`
- 注册与 API：`app/core/config.py`、`app/api/scripts.py`、`app/core/task_manager.py`、`app/utils/constants.py`
- 任务模块：`app/task/Xxx/` 的 `manager`、`AutoProxy`，按架构需要增加 `ScriptConfig`
- 前端入口：`Scripts.vue`、`ScriptTable.vue`、router、`types/script.ts`、相关 composable、脚本/用户编辑页
- Electron 能力：仅当需要注册表、文件系统或进程发现时增加 `electron/services`、IPC、preload 与类型声明
- 生成代码：后端 schema 变更后运行生成器，禁止手改 `frontend/src/api/**`

不要机械要求所有类型拥有相同文件。先确认架构契约，再补齐真实调用链。

## 审查方法

1. 从 `ScriptType`、任务注册和 UI 入口反查全部调用者。
2. 对照运行时读取的字段检查 config、schema、生成类型和表单；schema 中存在但运行时未消费的字段不代表有效功能。
3. 对照自动发现、手动选择和后端 `check()` 的路径判定；同一资源必须使用同一组哨兵文件。
4. 对照配置会话的启动、WebSocket 状态、停止、超时、卸载和异常路径；确保任务结束、进程退出、锁释放、配置写回。
5. 对照 `final_task` / `on_crash` 的原子配置恢复、用户状态落盘和独立进程清理。
6. 运行最小专项测试；测试缺口写进对应案例的检查清单，不编造验证结果。

## Okww 当前基线

Okww 已落地为 `ok-script` 专项，当前不是表单化 JSON 编辑器方案：

- 自动代理使用 `ok-ww.exe -t N -e`，MAS 只开放任务 `1` 和 `7`，并覆盖 DailyTask 的少量高频字段。
- 配置使用 `ScriptConfig.py` 无参数启动本体 GUI，通过 WebSocket 遮罩会话保存。
- 用户配置支持简洁/详细：简洁归 `Default/ConfigFile`，详细归 `{userId}/ConfigFile`。
- `Game.Enabled` 是当前 UI/运行时的游戏启停总开关；不要从兼容字段推断独立启动或关闭行为。
- ok-ww 根目录必须同时存在 `ok-ww.exe` 与 `data/apps/ok-ww/app.json`。
- Electron 一键导入与手动选择必须使用相同哨兵；鸣潮保存启动器路径，后端再解析实际客户端路径。
- 成功判定使用内置窗口关闭日志；进程在成功标记前退出视为异常。

完整实现与审查点见 [examples-okww.md](references/examples-okww.md)。

## 验证

按改动范围选择最小命令：

```powershell
python -m pytest tests/test_okww_game_launch.py tests/test_okww_launcher_config.py tests/test_okww_user_config_init.py -q
cd frontend
yarn test okwwPathDiscoveryService.test.ts
yarn lint
yarn typecheck
```

文档修改至少运行 Skill 校验，并用 `rg` 确认不存在相互冲突的旧规则。
