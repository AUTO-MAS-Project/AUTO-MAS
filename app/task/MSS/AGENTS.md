# app/task/MSS — MSS 是 MaaFW 的特调类型，不是专项

进这个目录之前先读 `app/task/MaaFW/AGENTS.md`：MSS（MaaStellaSora / 星塔旅人）的运行、更新、内嵌副本、
通知、失败截图、周期任务、代理次数……全部是 MaaFW 引擎的既有语义，这里一行都没有重写。本目录的核心是
`flavor.py`（`FLAVOR` 对象，满足 `app/task/MaaFW/tools/embedded/flavor.py` 的 `MaaFWFlavor`
协议，外加 `app/task/MSS/__init__.py` 的包说明与接入声明 `registration.py`，见下文「配置类」一段）。`flavor.py` 做的事穷举如下，多一件都没有：

1. `matches_project(interface)`：`mirrorchyan_rid == SSAH` / `github` 仓库名命中 /
   `name` 命中，任一即认领；后两条**同一口径**——等于 `MaaStellaSora` 或以 `MaaStellaSora-` 开头
   （`MaaStellaSoraX` 这种只是同前缀的不算，`https://github.com/MaaStellaSora` 这种组织主页也取不到仓库名）\
   ——官方版与个人版等
   衍生版（如 `beichen24a1/MaaStellaSora-Personal`）都认。**托管类型在新建时就定了，导入什么项目都不换**：
   MSS 托管导入、重新导入或克隆不认领的项目时，引擎在动副本之前直接拒绝（「这不是 MSS 项目。要用别的项目，
   请新建通用 MFW 托管。」）；通用 MFW 托管导入 MSS 项目仍是通用托管、按通用项目跑。**认领只用来拒收**；
   更新谱系仍按 `mirrorchyan_rid` / `github` / `name` 各自分开。
2. `decorate_selection(...)`，按这个顺序：
   - 账号 `Info.PlanMode` 引用了 MSS 计划表时，按当天槽位改写 entry `战斗_入口`（悬赏试炼快速战斗）的
     `悬赏试炼关卡` / `悬赏试炼跳过难度选择` / `选择悬赏试炼难度` / `悬赏试炼消耗所有干劲` / `自定义快速作战次数`；
     队列里没有这个任务就补上。关卡名不在 interface 的 case 里就整条跳过。`Fixed` 时不动。
   - 队列里有 entry `活动快速战斗_入口` 时查一次 `app/tools/common/game_calendar/stella.py`（只认会开活动关的「版本活动」）：
     有活动就挪到悬赏试炼前，确实没有就摘掉，取不到数据就原样跑。
   - entry `星塔_入口_agent`（新版爬塔）挪到队尾。每周一次靠 MaaFW 通用的 `Run.WeeklyOnceTasks`，这里不记周。
   按 entry 找不到就写一行账号日志跳过。**不重写**重试 / 周期 / 超时 / 更新 / 游戏启停。
   自动加入（悬赏试炼、活动）不补回引擎判定本轮不跑的实例（红灯、今天不在运行日），这份集合取
   `context.excluded_task_ids`，不自己解析快照；核心建计划时还会按红灯再滤一遍。
   钩子抛异常就是该账号本次建计划失败（记「异常」、不跑、不重试），取不到数据一律按「说不准」处理。
3. `skip_on_retry_entries`：按公开 task entry 声明已确认的日常与挑战任务，复用 MaaFW 的
   「前面的尝试已完成」过滤。本次运行成功过的任务不再补跑，失败、超时和未执行的任务保留；
   登录不在声明内，每次尝试仍执行。同名重复任务沿用引擎的保守重跑策略，不额外推断完成的是哪份。

`flavor.py` 只是一层外壳（第 10 步的前置件，MSS 以后自己的流程直接用下面两个模块）：

- `rules.py`：三个 entry、`MSS_SKIP_ON_RETRY`（上面第 3 条的名单就是它）、`TYPE_KEY`、`PLAN_MODE_FIXED`、
  `is_mss_project` / `github_repo_name`，全包只有这一份；只依赖解析一侧。
- `arrange.py`：排队列拆成活动探测前后两段，只吃 interface、队列与调用方取好的值（计划表当天那一格、
  `Info.IfActivityFirst` 原值、排除的实例），不读配置。`mss_arrange_head` 套计划表并算出要不要查活动排期
  （`probe_needed`：活动不在队列里、没被排除、开着活动优先 = `want_add`；活动在队列里 = `want_judge`；
  两者互斥），`mss_arrange_tail` 按查到的结果补上 / 挪动 / 摘掉活动，再把爬塔挪到队尾。
  `flavor.decorate_selection` = 取计划表那一格（`_current_plan_key`，日志在这一步写）→ head →
  只在 `probe_needed` 时调一次探测 → tail。**判断条件在原来的位置算出来，最多探一次，日志先后与原来一次
  排完时一字不差**；改这两段时守住这三条（本地对拍 S1–S18 与探测次数矩阵 S16 守着）。

配置类在 `app/models/config/script.py`（计划表类在 `app/models/config/plan.py`）：`MSSConfig(MaaFWConfig)` 同形，只改 `DEFAULT_SCRIPT_NAME`、
`USER_CONFIG_CLASS`、`FLAVOR`；`MSSUserConfig(MaaFWUserConfig)` 多一项 `Info.PlanMode`（计划表消费方
`mss`，`PLAN_BOOK` 的 `MSSPlanConfig`）与 `Info.IfActivityFirst`（活动优先）。
本目录的 `registration.py` 按确切类型 `MSSConfig` 登记运行（仍是 `MaaFWEmbeddedManager`）、配置回调与恢复池（与通用
MFW 同一套）以及托管属主 `mss_adapter`（见 `app/task/MaaFW/AGENTS.md`「托管属主登记」）；宿主按确切类型查，不靠继承。

前端托管页 / 账号页是 MSS 的专属页面（`frontend/src/views/mss/`：`MSSScriptEdit.vue`、`MSSUserEdit.vue`，
用 MaaFW 的 pageKit 分节与编排层拼），由同目录的 `entry.ts` 登记（适配条目上的 `maafw` 家族标记，计划表也在这里登记）；
托管页控制方式一步顶部「只支持桌面端」的提示、
账号页的计划表下拉与活动优先开关都是同目录下的组件。计划表页 `MSSPlanTable.vue` 是 MSS 自己的。

只适配桌面端：模拟器端的星塔旅人启动不了游戏，托管页在控制方式一步写明原因；引擎不拦 Adb。

要给 MSS 加任何"专项行为"之前先问：这是不是所有 MaaFW 项目都该有的？是就做进引擎；不是就只能经
`FLAVOR` 钩子进入，`app/task/MaaFW/` 里不出现 MSS 逻辑。
