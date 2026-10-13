# 后端迁移差异与依赖清单

更新时间：2026-10-10
分支：`refactor/plugin-migration-v3`
基线：`origin/dev`（已执行 fetch）

本文记录当前只读核验结果。它用于区分已迁移、仍依赖旧入口、保留源码和需要用户判定的范围，不把未验证的草案标记为完成。

## 当前运行核验

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| 后端健康 | 通过 | `GET /api/core/health` 返回 `ready`，`backgroundError=null`。 |
| 插件运行时 | 部分通过 | `auto_mas_core`、`maa_adapter`、`mumu_adapter` 已启用；`ldplayer_adapter`、`win_process_adapter` 已发现但禁用。 |
| 游戏配置 | 已有数据 | `/api/games/get` 返回 1 个 `MuMuGame` 配置，设备列表当前为空。 |
| 脚本配置 | 已有数据 | `/api/scripts/get` 返回 1 个 `MaaScript`，其 `path` 为空、`game_id` 为 `-`，尚未形成可执行的用户配置闭环。 |
| 游戏类型 | API 可用 | `/api/games/types` 可返回 `MuMuGame`。 |
| 历史查询 | API 可用但请求字段严格 | `/api/history/search` 使用 `start_date`、`end_date`、`mode`；使用前端旧的 camelCase 会收到 422。 |
| OpenAPI | 可生成 | 当前后端 OpenAPI 可被生成器读取；前端全量类型检查仍受其他旧页面契约阻塞。 |
| 调度非法脚本 | 已修复并验证 | 显式指定不存在的脚本 UID 会在建任务前返回 `code=400`，不会进入运行表；本地测试与 36164 开发服务均已验证。 |
| 旧框架运行边界 | 已收口 | `app.models` 不再导出 `ConfigBase`，`app.core` 不再导出 `TaskManager`/`EmulatorManager`，旧模拟器路由未挂载；旧专项源码仍保留作迁移参考。 |

## 模块差异

### 配置与持久化

- 已迁移：`setting.yaml`、`tools.yaml`、`queues.yaml`、`games.yaml`、`scripts.yaml`、`plans.yaml`、插件注册表和插件目录均由新 `ConfigEntry` / `ConfigCollection` 管理。
- 已确认：JSON 只在启动升级阶段一次性转换为 YAML，成功后归档到 `config/legacy-json/`；运行期不做 JSON/YAML 双读。
- 保留参考：`app/models/ConfigBase.py`、`app/models/config/legacy.py` 仅作迁移信息来源，不参与新配置运行。
- 仍需核对：`app/core/config.py` 内旧版本数据库升级代码仍会处理旧 JSON 路径；需要确认它与一次性 JSON→YAML 升级的执行顺序和重复启动行为不会互相覆盖。

### 插件宿主

- 已迁移：插件发现、元数据、注册表、市场、插件自有配置、生命周期 Trigger、HTTP 网关和服务注册。
- 已验证：MAA 与 MUMU 插件可被发现并加载；MAA 上游接口可访问。
- 仍需核对：插件配置声明的 `ui.hints` 当前在部分 API 响应中表现为字符串化 TypedDict，前端动态表单不能依赖未确认的序列化形态；需要在后端响应模型层确认并修正。

### 游戏管理与 MUMU

- 已迁移草案：`GameEntry`、`GameDeviceEntry`、`GameManager`、MUMU 控制器和 `/api/games/*`。
- 已验证：`/api/games/search` 可发现 MuMu 实例；`/api/games/instances/get` 可返回设备及官方状态/ADB 地址；通过新配置 `Trigger=True` 刷新可同步设备集合；实例 0 的 `open` 可经历离线→启动中→在线，`close` 可回到离线，Trigger 会自动复位。
- 运行约束：已有调度任务持有游戏配置锁时，游戏更新接口按设计拒绝配置更新；经统一调度停止任务并等待收尾后，刷新和实例控制正常。
- 当前限制：本机实例 0 的 ADB 在 MuMu 重启后可能短暂 `offline`，这是设备运行状态，不代表游戏管理框架失效；MAA 任务业务日志仍需人工排查。
- 旧入口仍存在：`app/api/emulator.py`、`app/utils/emulator/*`、`app/utils/emulator2/*` 及旧模拟器 schema 仍在源码中；需要确认哪些仅保留兼容源码，哪些仍被运行路径调用。
- 迁移顺序：先完成 MUMU 的统一游戏管理后端闭环，再处理 LDPlayer / win-process 等其他适配器，不因旧页面报错恢复旧模拟器 API。

### 脚本管理与 MAA

- 已迁移草案：`ScriptEntry`、用户集合、`MaaScript` 插件及 `/api/scripts/*` 新配置接口。
- 已验证：MAA 由 `MaaScript` 声明注册；目标脚本的路径、游戏 UID、设备 UID 与账号集合可从新配置系统读取；`/api/scripts/types` 返回 MAA 类型；指定账号任务已进入 `TaskDispatcher`，正确绑定 MuMu 游戏/设备并经统一历史入口落盘。
- 业务限制：MAA 原生配置恢复与日志监控仍会导致任务在业务层失败，按当前范围交由人工排查；这不改变插件声明、脚本展开、设备订阅、调度收尾和历史入口的框架验收结论。
- 旧任务模块仍大量引用 `Config.ScriptConfig`、旧任务类型和旧配置字段；需要逐条确认是否由 MAA 插件的新任务入口替代，不能整体恢复旧任务分支。
- 黑箱边界：游戏内操作、任务执行与成败判断继续通过 MAA 上游入口；MAS 只负责配置、账号、调度、模拟器和跨脚本编排。

### 调度与循环队列

- 已迁移草案：`TaskDispatcher`、脚本/用户展开、循环队列下次运行时间、主计时器和桌面守护接线。
- 已验证：专项调度测试通过；手动 API 可创建和停止运行任务。
- 仍需核对：所有启动、定时、循环、手动和取消路径是否都只进入 `TaskDispatcher`；旧任务入口和旧模式 worker 是否仍被其他服务间接调用。

### 历史记录

- 已迁移草案：`HistoryStore` 的保存、查询、详情和清理入口。
- 已验证：历史模块专项测试通过，路径访问限制存在。
- 仍需核对：MAA、其他旧任务模块和异常/取消收尾是否统一写入 `history_store`，以及旧历史文件的读取和聚合语义是否保持。

### 通用服务与 API/WS

- 已迁移或可用：核心、调度、历史、设置、工具、更新、队列、计划、脚本、游戏和插件路由均已挂载。
- 运行风险：以下源码仍使用废除的旧访问方式，当前部分路径因未被触发而未暴露错误：
  - `app/core/community_sign.py`：`Config.ToolsConfig`。
  - `app/utils/websocket.py`：`Config.get("Notify", ...)`。
  - `app/services/openclaw_qq.py`：`Config.get("Notify", ...)`。
  - `app/utils/emulator/*`、`app/utils/emulator2/*`：`Config.get("Function", ...)`。
  - 多个旧任务模块：`Config.get(...)`、`Config.EmulatorConfig`、`Config.ToolsConfig` 和旧脚本字段。
- 当前结论：这些引用不能通过恢复旧配置基类解决。下一步应按实际运行入口逐项迁移到 `Config.setting`、`Config.tools`、`Config.GameConfig` 及插件服务；若要扩大到未确认专项，先提交范围和实现方案。

### 框架迁移准入结论

- 已完成：新配置系统、插件宿主、统一任务调度、循环/定时触发、历史统一入口、MUMU 游戏管理和 MAA 框架接线的聚焦验证；旧 `ConfigBase`、旧 `TaskManager`、旧 `EmulatorManager` 不参与主程序运行。
- 已保留：`app/models/ConfigBase.py`、`app/models/config/legacy.py`、旧任务目录、`app/utils/emulator*` 和旧管理器/API 文件，作为专项迁移资料；它们未被新主启动路径导入。
- 未完成的后端整体验收项：旧专项测试收集有 14 项导入失败；`app/services/openclaw_qq.py` 仍访问已废除的 `Config.get("Notify", ...)`，虽当前登录路由未挂载，仍需在前端迁移前处理或明确暂缓范围。
- 前端准入：在上述剩余项有明确结论且 OpenAPI 稳定后，才生成新客户端并按插件中心、游戏管理、脚本/托管、计划、调度中心及其他页面顺序迁移。

## 本轮验收记录（2026-10-10）

- `uv run pytest tests/core/test_task_dispatcher.py tests/core/test_config_yaml_upgrade.py tests/core/test_timer_cycle_migration.py tests/core/test_history_store.py -q`：12 passed。
- `uv run pytest app/plugin/tests/test_mumu_subscribe_lifecycle.py app/plugin/tests/test_game_adapter_plugin.py -q -k "not test_games_types_and_add_are_siblings"`：34 passed；完整插件目录为 86 passed、4 failed，其中失败项属于旧断言或未标记异步测试。
- `uv run python -m compileall -q app plugins`：通过；`uv run ruff check app/core/task_dispatcher.py`：通过。
- 开发服务重启后 `GET /api/core/health` 返回 `ready`；设置、工具、插件注册表/市场、脚本/计划/游戏下拉项、历史概览和更新状态接口均可达。
- 旧测试收集仍有 14 项导入失败，来源是已废除的 `EmulatorConfig`、Whimbox 等专项旧模型；它们不作为恢复旧配置基类的依据，待专项迁移范围确认后分别处理。

## 下一步实施边界

1. 先修正或确认 `ui.hints` 的后端序列化契约，因为它是后端声明 UI 的基础。
2. 完成 MUMU 游戏管理的后端闭环验证，优先处理刷新、设备发现、启动/关闭和失败状态恢复。
3. 只迁移实际可达的通用服务旧配置引用；对未确认专项先保留源码并记录，不整批替换。
4. 再完成 MAA 配置绑定、任务分发和历史收尾闭环。
5. 通过整体后端验收后，才继续前端逐页迁移。
