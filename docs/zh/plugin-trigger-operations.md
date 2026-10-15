# Trigger 操作生命周期

用户批准独立完成宿主异步操作管理，基于插件迁移分支，关联 #1387。

- 配置框架通过 `TriggerDispatcher` 协议消费宿主注入的操作分发器，不自行创建业务任务。应用在引导配置前绑定宿主实现。
- 普通字段验证、提交成功后才受理同一 `update()` 的 Trigger；显式外层事务中的命令延至提交后受理，回滚丢弃。Init 嵌套也按所在事务成功与否合并或丢弃。
- 普通 `await entry.update(patch)` 返回本次受理的操作 ID 列表；在显式外层事务内尚未受理时返回空列表。现有 HTTP 配置更新接口保持原响应，旧消费者可按配置 ID 查询操作；新消费者可以直接调用 `/api/operations/start` 取得操作快照及 ID。
- 操作状态为 queued/running/cancelling/succeeded/failed/cancelled。复用 `TaskBase` 取消及完整收尾，不把 Task 已结束当作收尾通知已经完成。失败记录异常类型作为 errorCode，不暴露堆栈、参数或异常中的私有内容。
- 同一配置、同一 Trigger 的相同在途请求返回已有 ID，不重复启动；不同 Literal 命令冲突时拒绝。开始执行前再次确认配置身份，旧实例失效后不能执行。
- `@trigger_field(path, cancellable=False)` 声明只能等待完成的命令。插件安装/启停与设备操作目前没有通用取消安全保证，宿主内置入口显式使用此声明；其他异步插件命令需在 finally 中完成清理。
- 插件禁用/重载/卸载前，宿主暂停售理本插件及下游插件命令，取消可取消命令并等待其他命令完成，然后获取插件管理锁；避免操作收尾与管理锁互相等待。
- 进程退出先密封命令入口并等待所有操作收尾，再释放其他宿主服务和插件。终态记录只保留最近 200 条，运行中记录不会被清理；进程重启不恢复命令、不持久化请求参数。

新增接口：

| 接口 | 行为 |
| --- | --- |
| `POST /api/operations/start` | 根据 configUid/group/field/value 触发已声明命令，返回含 operationId 的快照 |
| `POST /api/operations/list` | 查询全部保留操作或指定 configUid 的记录 |
| `POST /api/operations/get` | 按 operationId 查询快照 |
| `POST /api/operations/cancel` | 对可取消操作发出取消并等待收尾，返回最终状态；不可取消操作明确拒绝 |

操作终态通过现有 WebSocket 通道通知前端，并以中、英、日文提示成功、失败或取消；断线期间不会重放通知，可用查询接口读取保留记录。

本项不新增物理设备锁、抢占策略、游戏更新器或操作管理页面，也不改变现有按钮布局。提交后配置事件由另一个独立 PR 提供。
