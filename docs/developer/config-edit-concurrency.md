# 配置并发编辑与运行快照

## 运行模型

AUTO-MAS 支持多个 Windows 用户各自运行一个独立前后端实例，并共享同一个配置目录。每个实例拥有自己的进程、内存缓存和前端草稿，但配置文件落在同一组物理 JSON 文件里，因此写入必须按文件资源协调。

本设计只协调 MAS 自有配置文件。DPAPI 仍只负责密码、Token 等敏感字段加密，不参与版本指纹。

## 编辑租约

编辑锁保存在现有 `data/data.db` 的 `config_edit_lease` 表中，启动时幂等初始化。锁服务用 SQLite `BEGIN IMMEDIATE` 事务完成抢锁、续租、释放和过期清理，保证不同后端进程之间只有一个持锁者。

租约字段包含资源键、随机令牌、持有者、创建时间、更新时间和过期时间。租约有效期为 30 秒；前端每 10 秒续租。释放和续租必须携带当前令牌，旧实例不能释放或续租新实例拿到的锁。崩溃、强制结束或断电时不会主动释放锁，由下一次抢锁、续租或查询时清理过期租约。

前端抢锁失败时显示：`有其他用户正在编辑该配置`。

## 锁粒度

锁粒度按物理文件或文件集合，不按页面：

| 资源键 | 文件 |
| --- | --- |
| `Config` | `config/Config.json` |
| `EmulatorConfig` | `config/EmulatorConfig.json` |
| `PlanConfig` | `config/PlanConfig.json` |
| `ScriptConfig` | `config/ScriptConfig.json` |
| `QueueConfig` | `config/QueueConfig.json` |
| `ToolsConfig` | `config/ToolsConfig.json`、`config/GameSignAccounts.json` |

脚本编辑页和用户编辑页都写 `ScriptConfig.json`，因此共享 `ScriptConfig` 锁。游戏社区账号组和工具设置共享 `ToolsConfig` 锁。

## 文件指纹

`app/utils/io.py` 提供通用 SHA-256 指纹能力：

- 单文件内容指纹。
- 多文件集合指纹。
- 文件不存在时参与稳定指纹计算。
- 原子写入后的新版本计算。

指纹只由文件路径和内容确定，不绑定配置类型。JSON、YAML、文本配置都可以复用。

## 保存冲突

进入编辑时，前端拿到编辑令牌和基础指纹。保存请求必须携带这两个值。后端保存前检查：

1. 租约仍存在。
2. 租约令牌匹配。
3. 当前文件集合指纹等于基础指纹。

任一条件不满足时拒绝保存并返回统一业务错误。文件内容已被外部修改时提示用户配置已变更，不覆盖其他用户内容。保存成功后，前端续租并把最新指纹作为下一次保存的基础指纹。

## 前端会话策略

前端统一使用配置编辑会话服务：

- 第一次保存前抢锁，已有会话时复用。
- 续租失败或指纹变化后冻结保存，并保留当前草稿。
- 窗口重新获得焦点时只续租和检查版本，不刷新表单正文。
- 离开页面或关闭窗口时尽力释放锁；异常退出依赖租约过期回收。

编辑页不能在重新获焦时用后端数据覆盖用户草稿。列表页和只读页首次进入、窗口重新获焦和低频定时刷新时可以重新读取配置。

## 后端缓存同步

后端读取共享配置前根据资源指纹检查文件是否变化。变化时重新加载对应缓存，避免另一个实例保存后本实例仍使用旧内存数据。

写入成功后，配置管理器记录对应资源的新指纹，作为本进程缓存版本。

## 任务运行快照

创建任务前先同步后端缓存到共享文件最新版本。任务创建成功后，脚本配置、用户配置和队列配置使用创建时的不可变快照；运行过程中修改配置不会影响已创建任务。

下一次循环的调度时间、停止状态、删除状态等运行控制信息仍可动态读取。专项已有的原生配置快照机制继续复用，不重复实现。

## API

配置编辑 API：

- `POST /api/config-edit/acquire`：获取租约并返回令牌、基础指纹和过期时间。
- `POST /api/config-edit/renew`：续租并返回当前文件指纹。
- `POST /api/config-edit/release`：按令牌释放租约。
- `POST /api/config-edit/status`：查询锁状态，不返回持锁令牌。

配置保存 API 增加 `editLeaseToken` 和 `baseVersion`。后端 schema 变更后必须运行前端 OpenAPI 生成器，不手改生成文件。

## 验收方式

建议最小验收：

- 两个后端进程同时进入同一配置，只有一个抢锁成功。
- 第二个用户收到 `有其他用户正在编辑该配置`。
- 续租、正常释放、租约过期后重新抢锁均正常。
- 同一文件指纹稳定，内容变化后指纹变化。
- 外部修改后保存被拒绝，不覆盖其他用户内容。
- 编辑页重新获焦不覆盖草稿。
- 离开编辑页不额外保存草稿，并尽力释放锁。
- 列表页重新获焦能看到其他用户保存的配置。
- 创建任务后修改配置，已创建任务仍使用创建时快照。

推荐检查命令：

```powershell
.\.venv\Scripts\python.exe -m py_compile app/utils/io.py app/core/config_edit.py app/core/config.py app/api/config_edit.py app/api/scripts.py app/api/queue.py app/api/plan.py app/api/setting.py app/api/tools.py app/api/emulator.py app/models/schema.py app/core/task_manager.py
cd frontend
yarn openapi
yarn typecheck
yarn lint --max-warnings 1
yarn test
```
