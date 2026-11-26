# SRC 专项插件化设计

基于 AUTO-MAS `upstream/dev@e0380ba92`。建议把 SRC 后端做成独立发行的脚本适配插件。已有用户升级后，从原来的托管或队列启动 SRC，沿用同一个账号、模拟器绑定、备份和执行历史。新用户从插件中心启用 SRC，再建立托管。首版沿用现有桌面编辑页。

## 插件边界

| 所有者 | 负责的内容 |
| --- | --- |
| `AUTO-MAS-SRC-Adapter`（拟建） | `SrcConfig`、`SrcUserConfig`、运行条件、三种任务模式、SRC 进程和安装事务、配置会话、备份池定义、历史与通知的 SRC 内容、专项接口 |
| AUTO-MAS 后端与 `auto_mas_core` | 插件发现和生命周期、通用托管及账号 CRUD、配置持久化、任务树与锁、游戏及设备租用、历史存储、通知投递、安装备份与更新恢复框架 |
| AUTO-MAS 桌面端 | SRC 托管和账号页、原生会话入口、恢复面板。用静态插件入口 `frontend/src/views/src/entry.ts` 汇入现有注册表，沿用现有路由后缀 `src` |
| StarRailCopilot | 原生 WebUI、游戏内任务及其运行结果、原生安装器和配置语义 |

选择独立插件，理由是 SRC 修正启动、日志识别或安装器适配之后，用户可以单独更新适配器。另一种做法是把旧 `SrcManager` 包一层，wheel 只负责注册。这样初次搬迁较小，但运行仍依赖宿主私有模块，旧 manager 还会再次取得调度层已持有的锁。整套 Vue 页面随 wheel 加载也需要新增动态前端机制，目前 MAA 和 Whimbox 都由桌面端编译页面。沿用这两者的静态页面机制，已足以独立更新 SRC 后端。[现有交付约定](plugin-development.md) · [静态页面注册](../frontend/src/plugins/scriptAdapters.ts)

## 声明与调用

发行名建议用 `auto-mas-src-adapter`，导入名和插件 ID 用 `src_adapter`。对外专项键继续使用 `SRC`，持久化类型名继续使用 `SrcConfig` 和 `SrcUserConfig`。以下是拟用的现有 SDK 接口。

```python
class Plugin(ScriptAdapterPlugin):
    script_type_key = "SRC"
    api_router = router
    decl = ScriptTypeDecl(
        script_type=SrcConfig,
        user_type=SrcUserConfig,
        expander_class=SrcExpander,
        supported_modes=(
            TaskMode.AUTO_PROXY,
            TaskMode.SCRIPT_CONFIG,
            TaskMode.SCRIPT_VIEW,
        ),
        game_kinds=("emulator",),
        activity_game="starrail",
    )
```

SRC 没有专项计划表。声明沿用当前设备范围和程序更新时机。设备要求、ModAVD 专属支持、后台预下载均须有对应实现才声明。游戏与设备由已有适配器提供，无须再装一个 SRC 游戏管理插件。[SDK 声明](../app/plugin/base/script.py) · [SRC 当前注册](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/registration.py)

公共调用仍是“创建 SRC 托管 → 添加账号 → 提交任务要求树”。运行、编辑、查看分别提交 `AutoProxy`、`ScriptConfig`、`ScriptView`。调用者给出托管或账号 UUID，用返回的运行任务 ID 停止会话并等待收尾。托管级操作传托管 UUID，磁盘目录名 `Default` 只在插件内部解析。托管和账号读写继续走现有 CRUD。备份的 list、ensure、preview、file、restore 由插件 router 在 `/api/plugin/src_adapter/backup/*` 提供，复用现有 DTO、恢复服务和前端面板。按启用插件导出 OpenAPI 并重新生成客户端。生成前须同时启用所有会被调用的插件，否则未启用插件的契约模型会被 `frontend/scripts/postprocess-openapi.mjs` 当作过期文件清掉；这类检查不要用整仓 `yarn openapi` 跨插件同步。[任务入口](../frontend/src/composables/useTaskApi.ts) · [动态 OpenAPI](../app/plugin/openapi.py) · [现有备份操作](../app/api/scripts/backup.py)

## 一次托管怎样执行

1. L2 取得托管锁并派发 `SrcExpander(UserExpander)`。L3 使用传入的配置，按物理安装根取得现有 `installation_access`。在普通完整性检查之前，先辨认上次进程、快照和安装身份，沿原流程清理并恢复。这样即便上次替换配置时中断、当前目录暂时不完整，也能进入恢复。只在取得对应资源后执行其收尾。
2. 托管级处理未确认的安装记录。自动代理按原 `Update.TakeoverEnabled` 设置调用 SRC 的 Git/CDN 准备和官方安装器，复用宿主安装备份、确认与回滚。配置和查看会话只走启动安全检查。脚本更新与账号运行前的游戏 APK 检查有各自的开关和失败结果。
3. SDK 逐账号取锁，解析账号设备覆盖或托管继承，L4 使用当前绑定设备。自动代理保留禁用、剩余天数、队列当日次数上限与手动单跑的区别。插件账号的公共 `info.enabled` 只表达启用开关，SRC 的 `RemainedDay == 0` 仍须在自动代理资格判断处生效。运行重试受原单账号总时限约束，前置及后置脚本按账号执行。
4. `AutoProxyWorker` 启动 SRC，用原生日志报告结果。当前用结构化日志中的 `Close game during wait` 判为本轮完成，接管请求、提前退出和停滞各自有结果。保留原口径并用样本验证。账号计数、历史和统计报告各写一次，沿用宿主投递与任务结果遥测。
5. `ScriptConfigWorker` 和 `ScriptViewWorker` 共享启动 WebUI、确认进程退出和恢复安装现场的代码，但各自决定写回。L4 交还账号前完成保存。若进程退出未确认，L3 在 `await super().spawn(child)` 后检查清理结果，终止本次托管，保留恢复记录。这里需要显式检查，因为 `TaskBase.run()` 会接住普通子任务异常。L3 最后释放安装占用，L2 在收尾后归还资源与托管锁。[旧执行顺序](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/manager.py) · [账号展开](../app/task/user_expander.py) · [子任务生命周期](../app/task/lifecycle.py) · [日志判定](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/AutoProxy.py)

插件内按职责放置 `config`、`tasks`、`native`、`updates` 和 `api` 模块。`native` 持有安装身份、进程、快照、目录交换及 SRC 的备份适配。公共配置恢复、进程管理和通知继续通过 SDK 调用。只有在发行版 SDK 缺少所用的公共操作时，才在配套宿主版本导出该操作。

## 配置归属与崩溃恢复

| 操作 | 正常保存位置 | 结束后的 SRC 安装目录 |
| --- | --- | --- |
| 编辑托管共享配置，或编辑共享来源账号 | `data/{scriptId}/Default/ConfigFile` | 恢复任务前现场 |
| 编辑独立来源账号 | `data/{scriptId}/{userId}/ConfigFile` | 恢复任务前现场 |
| 编辑原生来源账号 | SRC 自己保存到安装目录的 `config/` | 保留成功编辑的结果 |
| 查看历史备份 | 无写回目标 | 恢复任务前现场。托管级查看跳过下发，账号级按备份来源准备视图 |

旧编辑会话正常保存时调用 `_mas_owner()`。写中断标记时却记录当前账号 ID，重启后的 `_save_pending_config_session()` 直接用该 ID 拼写回目录。因此，共享账号在中断前后可能写入不同位置，原生账号也可能被当成有 MAS 副本的账号。这两个路径在当前源码中可以核对。[会话标记与正常保存](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/ScriptConfig.py) · [中断恢复](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/manager.py)

新会话在下发时确定写回目标。进程记录与 `Temp.ready` 同时保存可识别版本的会话意图和目标，恢复时核对托管 ID、安装身份和两份记录。共享目标为 `Default`，独立目标为账号 UUID，查看及原生编辑没有 MAS 写回目标。原生编辑正常完成与异常中断的安装目录处理仍分别执行。旧记录继续可读，按原记录和可核实的来源判定目标。无法证明旧账号会话应写入哪个目录时，先保全编辑现场和原始快照，向用户给出恢复位置，不覆盖候选目录。宿主加载配置时不清理这些文件，由首个 SRC 任务接手。

MAS 备份继续按账号放在 `data/{scriptId}/SrcBackups/mas/{userId}`。原生备份继续按安装配置根指纹放在 `data/SrcBackups/native/{key}`，供引用同一安装的托管共享。有待恢复的 `Temp.ready` 时，原生恢复操作先拒绝覆盖。归档和迁移保留已有侧车，预览能读旧备份，`Base` 不从侧车静默回填。[备份目录与恢复守卫](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/tools/backup_archive.py)

## 旧用户升级与插件启停

- 宿主在激活脚本配置集合前，按 `ScriptConfig.json` 或 `scripts.yaml` 的类型索引识别 `SrcConfig`，通过现有安装、加载、启用流程补齐插件。覆盖已处于数据版本 v2.2 的用户。没有 SRC 托管时不触发迁移安装。插件安装失败时保留旧配置并报告具体包名，下一次启动可重试。[升级入口](../app/core/config/plugin_upgrade.py) · [启动顺序](../app/core/config/manager.py)
- `SrcConfig(ScriptEntry)` 的 `users` 收窄为 `collection(SrcUserConfig)`。`SrcUserConfig(UserEntry)` 保留现有业务字段。加载旧 YAML 的 `UserData` 和旧 JSON 的 `SubConfigsInfo.UserData` 时转到同一个 `users` 集合，保留顺序与全部 UID。公共 `info.name/enabled` 从原 `Info.Name/Status` 投影。保留密文字段声明、通知 webhook 集合、设备绑定、每日代理状态、队列引用和旧 `Info.Mode` 转换。升级按存量来源取值，常规新建账号仍给 `native + IfQuickConfig=False`。[旧模型](../app/models/config/script.py) · [配置转换入口](../app/core/config/upgrade.py)
- 切换时同时移除 SRC 的内置注册、静态配置联合与重复 OpenAPI 枚举，更新新建账号默认值分支、首页活动映射、前端专项入口及类型生成。保留已有 `/edit/src` 链接、列表展示、会话遮罩和恢复面板。创建入口与直达路由根据服务端实际能力开放。插件重载按已有机制保留 UID，普通禁用或卸载按插件中心现有影响确认处理，运行中的锁定实例适用现有预检。**普通禁用会级联删除该类型的托管及账号**，升级失败恢复不得通过“先禁用再启用”处理。[插件启停语义](../app/core/plugin/adapters.py)

## 两处需要对照上游的存量能力

- 旧版用 MaaFramework 的 `StarRailEmulator` 管线切换官服和 B 服账号，图片和管线在主仓，宿主加载公共资源目录。上游已有启动、登录确认和进入主界面的逻辑。普通登录优先走 SRC 自己的入口，指定账号、账号列表选取与 B 服凭据切换要分别核实。上游覆盖即替换；确有缺口则先评估上游贡献，受阻时才保留有退出条件的兼容实现。若必须保留，SRC 专属管线与图片随插件 wheel 交付，验证干净安装能加载，MaaFramework 引擎仍复用公共能力。发布前须能证明给指定账号派发时进的是该账号。[当前调用](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/tools/login.py) · [宿主资源加载](../app/core/maa_manager.py) · [上游登录实现](https://github.com/LmeSzinc/StarRailCopilot/blob/master/tasks/login/login.py)
- 旧版覆写 `src.json`、`deploy.yaml` 并从备份解析关卡值。保留用户已有设置与恢复能力，先核实所支持的 SRC 发行版能否从公开配置或启动入口表达同一行为。能替代的调用移交上游，遗留兼容只集中在插件的原生配置模块，连同适用版本和移除条件记录。关卡表、上游私有字段和游戏流程不进入宿主 SDK。[现有覆写](https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/e0380ba92/app/task/SRC/AutoProxy.py) · [上游程序入口](https://github.com/LmeSzinc/StarRailCopilot/blob/master/src.py)

## 交付顺序与验收

1. 独立仓开发插件，配套宿主在隔离环境移除内置 SRC 后，用本地 wheel 联调。以真实 SDK 发行包确定最低兼容版本，阻止仍内置同名类型的旧宿主启用插件。先发布并验证 wheel 可安装与市场可发现，再交付会自动安装它的宿主及静态页面版本。主仓集成环境按现有机制固定 wheel 版本及 SHA256。[发布流程](plugin-development.md) · [集成依赖](../tests/requirements-plugins.txt)
2. 用隔离旧配置做两次冷启动。覆盖带 SRC 的旧 JSON、当前 YAML、无 SRC 和首次安装 wheel 失败后重试。核对托管及账号 UID、顺序、加密字段可用性、设备覆盖、队列引用、三种配置来源与备份目录。再从公共 CRUD 改一个关卡字段，重启后核对其余配置仍在。[可扩展的现有升级测试](../tests/core/test_plugin_config_upgrade.py)
3. 从桌面编辑页实际打开一次共享编辑和一次只读查看，分别正常关闭与中断恢复。检查应改动的目录、应保留的文件内容，以及 `Temp.ready` 存在时恢复不会覆盖现场。两个托管指向同一安装时，验证后来的任务无法覆盖前一任务的快照，清理未确认时下一个账号不启动。
4. 使用配套发行 wheel 验证插件启停与托管创建入口、老路由、备份 API、托管及账号级设备绑定。真机验收从 MAS 公共调度进入，实际观察选定账号、游戏更新条件、SRC 日志结果、正常与取消收尾、历史和通知。旧安装有未确认更新标记时，验证先恢复再启动。适配器安装成功、任务入队和浏览器页面可打开分别只能证明对应步骤。[账号编辑浏览器场景](../frontend/e2e/account-editors.pw.ts) · [游戏绑定场景](../frontend/e2e/games.pw.ts)

发布验证要包含三种组合：旧宿主与新 wheel、配套宿主与新 wheel、配套宿主与暂时不可下载的 wheel。第一种应在修改类型表前拒绝启用。若开发版和旧版共用 SDK 版本号，单靠版本下限无法区分，可在插件启用前检查宿主是否仍登记了内置 SRC。第三种应保留升级前文件，重新取得发行包后用原 UID 完成加载。回退已写入 `users` 新结构的环境时，旧宿主配套恢复升级前的持久化配置；只回退代码可能使旧模型读不到账号。升级前的备份须覆盖当前 YAML，包括已经是 v2.2 的安装。
