# app/task/MSS — MSS 是 MaaFW 的特调类型，不是专项

进这个目录之前先读 `app/task/MaaFW/AGENTS.md`：MSS（MaaStellaSora / 星塔旅人）的运行、更新、内嵌副本、
通知、失败截图、周期任务、代理次数……全部是 MaaFW 引擎的既有语义，这里一行都没有重写。本目录只有
`flavor.py`：`FLAVOR` 对象（满足 `app/task/MaaFW/tools/embedded/flavor.py` 的 `MaaFWFlavor` 协议）。
它做的事穷举如下，多一件都没有：

1. `matches_project(interface)`：`mirrorchyan_rid == SSAH` / `github` 指向 `MaaStellaSora/MaaStellaSora` /
   `name == MaaStellaSora`，任一命中即认领——导入完成后引擎据此把脚本类型定成 `MSSConfig`。
2. `decorate_selection(...)`，按这个顺序：
   - 用户 `Info.PlanMode` 引用了 MSS 计划表时，按当天槽位改写 entry `战斗_入口`（悬赏试炼快速战斗）的
     `悬赏试炼关卡` / `悬赏试炼跳过难度选择` / `选择悬赏试炼难度` / `悬赏试炼消耗所有干劲` / `自定义快速作战次数`；
     队列里没有这个任务就补上。关卡名不在 interface 的 case 里就整条跳过。`Fixed` 时不动。
   - 队列里有 entry `活动快速战斗_入口` 时查一次 `app/tools/stella_activity.py`：有活动就挪到悬赏试炼前，
     确实没有就摘掉，取不到数据就原样跑。
   - entry `星塔_入口_agent`（新版爬塔）挪到队尾。每周一次靠 MaaFW 通用的 `Run.WeeklyOnceTasks`，这里不记周。
   按 entry 找不到就写一行用户日志跳过。**不**碰重试 / 周期 / 超时 / 更新 / 游戏启停。

配置类在 `app/models/config.py`：`MSSConfig(MaaFWConfig)` 同形，只改 `DEFAULT_SCRIPT_NAME`、
`USER_CONFIG_CLASS`、`FLAVOR`；`MSSUserConfig(MaaFWUserConfig)` 多一项 `Info.PlanMode`（计划表消费方
`mss`，`PLAN_BOOK` 的 `MSSPlanConfig`）。`_MANAGER_BOOK` 里 `MSSConfig` 单独登记到 `MaaFWEmbeddedManager`。

前端没有 MSS 专用脚本页 / 用户页：用 MaaFW 的两个页面，按 `scriptType === 'MSS'` 取 `useMaaFWFlavor`
的文案表；用户页的计划表下拉由表里的 `planConsumer` 打开。计划表页 `MSSPlanTable.vue` 是 MSS 自己的。

只适配桌面端：模拟器端的星塔旅人启动不了游戏，脚本页在控制方式一步写明原因；引擎不拦 Adb。

要给 MSS 加任何"专项行为"之前先问：这是不是所有 MaaFW 项目都该有的？是就做进引擎；不是就只能经
`FLAVOR` 钩子进入，`app/task/MaaFW/` 里不出现 MSS 逻辑。
