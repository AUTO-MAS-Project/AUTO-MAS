# MAA 脚本适配

贡献脚本类型 `maa`（明日方舟 MAA）。依赖 `auto_mas_core>=6,<7`。

源码逻辑迁自非插件版 `app/task/MAA`：自动代理、原生 GUI 配置会话、养成/库存、更新与备份。任务分层下插件只实现 `UserExpander.check/prepare` 与 `ModeWorker`；脚本锁、用户 X 锁与模拟器订阅由宿主完成。
