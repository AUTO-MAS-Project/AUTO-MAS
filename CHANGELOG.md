# 更新日志

本项目所有值得注意的变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/spec/v2.0.0.html)。

<!--
  本文件由 scripts/changelog.py 在发版时从 changelog.d/ 里的碎片编译生成，平时不要手改，
  也不要手改 res/version.json 等生成物。

  - 要登记一条更新日志，在 changelog.d/ 下新建一个碎片文件，见 changelog.d/README.md，
    或运行 `python scripts/changelog.py add <分类> <项目键> "<一句话>"`。一条 PR 只放一个碎片。
  - 文件顶部第一个 `## [vX.Y.Z]` 标题就是仓库当前的版本号。发版 PR 由「准备发版」工作流
    创建，是唯一会改动本文件与各处版本号的地方。
  - 条目写成一行 `(项目) 做了什么 (#PR 号) by @作者`：项目、PR 号与署名都在发版时由脚本
    按碎片与其提交自动补，不要手写；本体的条目没有 `(项目)` 前缀，同一分类内排在最后。

  分类含义（中间五类来自 Keep a Changelog）：

  - 破坏性变更：需要用户动手确认或会改变既有行为的改动，在更新提示里最醒目地展示。
  - 本次亮点：这一版最值得一看的几条。维护者给碎片加一行 `highlight: true`，编译时这条
    就进这里而不是原分类。
  - 新增：新添加的功能。
  - 变更：对现有功能的变更，含优化与调整。
  - 移除：已经移除或不再建议使用、即将移除的功能。
  - 修复：对 bug 的修复。
  - 安全：对安全性的改进。
  - 开发流程：只影响贡献者、用户看不见的改动，不进公告。
-->

## [v5.5.0-beta.6] - 2026-09-16

### 破坏性变更

- 绝区零一条龙升级后，旧版本保存在脚本目录下的「一条龙原生配置」备份不再显示在配置恢复列表中（数据未删除，确需找回请手动迁移） by @AthenaHibou

### 新增

- OK-NTE 专项接入「配置恢复」：可浏览历史备份、预览配置摘要并一键恢复（进入编辑页即自动备份 ok-nte 原生配置，各留最近 10 份） by @AthenaHibou
- BetterGI专项 一条龙配置区文案统一为「配置组」并新增「录制」标签页，队列里的配置组可自定义显示名称与备注，录制（键鼠脚本）可作为独立队列项加入；同时修复添加配置组弹窗误带已有项目、清空脚本产生空组等问题 by @TCddddd
- 首页 八张游戏活动卡合并为 banner 轮播，横幅兼作游戏切换器、下方只展示当前游戏的活动卡，可在「自定义首页」里单独开关每个游戏或整个轮播 by @qiyinxi
- 所有专项脚本现在统一支持脚本、用户、直控三种配置来源，并可独立启用快速配置。 by @1w1w11w1
- BAAH专项 首页新增碧蓝档案活动卡片：可切换日服 / 国际服 / 国服查看进行中的活动与剩余时间，服务器顺序支持拖动调整 by @beichen24a1
- 支持通过免费的中国移动 5G 短信接收任务通知（仅限中国移动手机号）。 by @ClozyA
- ok-ww、MAA、MaaEnd、M9A、通用脚本、BAAH、SRC、BetterGI、MaaFW、HSR、OK-NTE、一条龙专项接入「配置恢复」：可浏览历史备份、预览配置摘要并一键恢复，备份内文件可点开查看原始内容，进入编辑页或运行前自动备份原生与 MAS 配置，各留最近 10 份，恢复不再产生重复的备份条目 by @AthenaHibou
- 首页 每日一句旁新增「换一句」按钮，点一下文字碎开再重新拼成新的一句 by @beichen24a1
- MAA 用户配置新增干员养成目标：指定干员与精英化目标后，自动代理按材料缺口自动刷取，识别到目标达成后自动移除并随统计报告通知 by @jinghero
- MAA 养成计划支持绑定森空岛：可为干员设置精英化/专精/模组目标，按当天可刷取的材料缺口自动刷取、达成后自动移除；库存保持的库存列改为展示当前用户自己的识别档案并显示识别时间 by @jinghero
- 计划管理页的计划表支持拖拽调整顺序，并可在计划表标签上直接重命名 by @beichen24a1
- 调度队列的每个脚本任务可单独限定运行周几，不在当天运行的任务会被跳过 by @qiyinxi
- BetterGI专项 新增「队伍配置」：可为自动秘境、自动地脉花、自动首领讨伐分别指定使用的队伍与战斗策略，战斗任务会按当前场景自动选用对应队伍 by @TCddddd
- 绝区零一条龙用户设置新增折叠的启动参数配置（含 DX12 独立开关），与一条龙原生游戏设置同源读写 by @AthenaHibou
- 初始化失败时始终保留查看日志入口，日志页支持打包日志。 by @Craun718

### 变更

- 模拟器 2.0 的「大雷主人模式」补齐宿主层：雷电启动加载页的轮播与开机全屏页不再出现，MuMu 多开器的桌面弹窗在只用雷电时也会一并处理，关闭时按原样还回 by @qiyinxi
- 建脚本时「MFW」从专项适配挪到通用脚本一栏，与通用脚本并列一行，说明改为「运行任何带 interface.json 的 MaaFramework 项目」 by @qiyinxi
- 「脚本」配置来源在绝区零一条龙、BetterGI、通用脚本、星穹铁道与 BAAH 的用户页置灰并悬停说明原因，避免选择实际不生效的配置来源 by @AthenaHibou
- MFW 脚本的用户页去掉「配置来源」三态选择和「快速配置」开关：MFW 没有可退回的原生配置，两者对它没有意义，任务队列始终显示 by @qiyinxi
- 首页 优化活动区游戏切换与终末地、明日方舟的图文布局，自动轮播默认关闭，修正碧蓝档案活动名称与封面对应关系，服务器改用胶囊条切换并记住上次选择，移除拖动排序与重复横幅，加载时仍可切换服务器 by @HarcoChen
- MaaEnd 改用内置切号与游戏启动设置，统一快速配置入口，支持结束关闭游戏时恢复预设或自定义分辨率，并修复退出后阶段卡住的问题。 by @HarcoChen
- 重新整理 MaaEnd 用户页面，分离基本信息与配置来源、为每日执行限制增加分隔，简化任务分类并收起低频设置。 by @HarcoChen

### 移除

- 移除通用脚本的「快速配置」开关，直控模式下直接使用脚本自身配置运行。 by @1w1w11w1

### 修复

- BAAH 专项 修复配置页多出一个「结束后关闭模拟器」开关的问题：其他专项都没有这个选项，BAAH 一并按「任务结束后关闭模拟器」执行 by @1w1w11w1
- 修复模拟器关闭动作缺少超时、关闭失败时仍可能让任务收尾长时间卡住的问题 by @1w1w11w1
- 修复脚本配置目录被脚本进程占用或含只读文件时，任务收尾复原配置失败、配置目录停留在半删状态的问题 by @1w1w11w1
- 开发流程：收敛各专项重复的日志推送与启动参数拆分实现，避免同类逻辑在多处各存一份 by @1w1w11w1
- 开发流程：恢复 tzdata 依赖——Windows 上没有系统时区数据库，移除后会导致时区查询失败 by @1w1w11w1
- 修复首页活动卡片在数据源不可用时无法显示的问题 by @1w1w11w1
- 修复开发环境前端无法启动的问题 by @1w1w11w1
- MaaFW 专项 修复雷电模拟器上打不进中文文本的问题（如 M9A 的中文兑换码：输入框始终为空、节点反复重试直到运行超时）：雷电上的文本输入改走雷电自己的 ldconsole 命令，触控改用 minitouch by @qiyinxi
- 模拟器 2.0 设备表进页面与脚本页实例下拉的加载提速数倍，点击启动 / 关闭立即显示「启动中 / 关闭中」且启动中可直接关闭，表格随窗口高度滚动不再被裁掉，「隐藏窗口」按钮真正隐藏窗口并新增「显示窗口」，实例下拉显示「#设备号 名称」不再先显示设备号再跳成名称 by @qiyinxi
- 修复 BetterGI 自动秘境未刷够配置的轮次就提前结束、以及开启「刷取至树脂耗尽」仍被当作限定次数执行的问题 by @TCddddd
- 修复 BAAH 任务一启动就报错、完全无法运行的问题 by @beichen24a1
- 合并 BetterGI 相关 9 个 PR：通知统一走 AUTO-MAS 通知编排、掉落统计强制打开首领讨伐奖励识别、执行层单次启动并按左栏队列顺序执行且留下运行记录、修复未选择首领时自动首领讨伐被静默跳过、地脉花策略生效、直控来源与原生配置写入分离（含 Plan 到原生键反向映射单测）、修复战斗组开关关闭后仍运行、修复自定义分组脚本配置下拉框无法展开、修复旧 BetterGI 进程杀不掉导致任务静默卡死并提示手动关闭或以管理员身份运行 MAS、修复 BGI 自提权重启换 PID 被误判为「在完成任务前退出」导致重试全废、修复进程刚被结束就被判定为「杀不掉」（按进程名轮询复核）、修复执行层对「不使用冒险之证」的多余取反导致地脉花失败、执行层有步骤失败时状态改为「部分失败」并在通知里给出分步执行表、补回合并 9 个 PR 时丢失的掉落统计接线（此前开了开关也没有掉落表）、「添加配置组」候选不再混入脚本/录制副本与 MAS 自建组、路径类引用的读/存不再因名字含分隔符报「配置组名非法」 by @TCddddd
- 修复复制脚本或任务运行结束后，对该脚本用户配置的修改只在当前会话生效、重启后回退的问题 by @qiyinxi
- 修复未接入快速配置的脚本专项设置页仍显示「是否启用快速配置」开关的问题 by @AthenaHibou
- MAA专项 修复剿灭周完成与绿票商店月完成状态在界面跨周/跨月开启后不刷新、需重启软件才恢复的问题 by @jinghero
- HSR专项 修复在 MAS 中修改 M7A 配置后 config.yaml 里 4:00 这类时间被改成整数、导致 M7A 无法启动的问题 by @ColinHouse
- MAA 专项 修复每周剿灭因理智不足空跑时反复重启重试的问题：现在理智不足会跳过本次剿灭，留待下次调度继续。 by @1w1w11w1
- 修复库存保持任务刷到的材料未计入掉落统计的问题 by @jinghero
- MFW脚本 修复项目自带的资源热更新（如 M9A 的活动数据）会让运行前项目更新永远失败、每次都白下全量包的问题；本地改过的受管文件改为覆盖前留档，不再阻断更新 by @qiyinxi
- MFW专项 修复内置运行结束后代理次数、剩余天数与周期任务记录不保存、用户卡片始终显示「未代理」的问题；运行期间脚本与用户配置改为锁定不可编辑（与其他专项一致），上次运行失败时卡片标签标红 by @qiyinxi
- 修复任务异常中断后脚本原有配置丢失、再次打开变成旧配置或空白的问题 by @1w1w11w1
- HSR专项 修复配置检查未通过或提前停止时，任务结果被错误地显示成「恢复星铁分辨率注册表失败」的问题 by @Taimer0721
- MaaEnd专项 修复脚本设置在 MaaEnd 配置目录缺失时额外报一条「配置换入的源目录不存在」的问题 by @Taimer0721
- 星铁专项：SRA 更新到 2.22.0 后，「日常与奖励」不再让整个用户的任务在启动前报错中止；兑换码开关按新版配置生效 by @Taimer0721
- 虚拟显示器 修复任务运行期间打开显示器后虚拟屏迟迟不拆、所有窗口都留在看不见的那块屏上的问题，现在真实显示器一回来就拆除并在日志里记下是哪块显示器回来的 by @qiyinxi
- 虚拟显示器 任务运行期间真实显示器接回来时不再立即拆除虚拟屏（拆屏会把窗口挪走、打掉正在跑的 PC 端游戏任务），改为在接回的显示器右下角弹窗询问是否拆除，未选择则等本轮任务结束后自动拆除；设置页新增「立即拆除」按钮 by @qiyinxi
- 修复新建 MAA 或 SRC 脚本后从调度中心执行必报 object has no attribute 'user_config' 错误、任务无法开始的问题 by @1w1w11w1
- 修复 MAA 自定义基建排班无法手动选择班次、以及排班表换班始终执行同一班的问题；现在带时间段的排班表按时间段自动换班，不带时间段的按顺序轮换 by @jinghero
- 修复点击 MaaEnd 用户设置页右侧目录时白屏的问题。 by @HarcoChen
- 修复 MaaEnd 指定理智关卡可能不生效的问题，并按安装版本动态显示和执行自动采集路线。 by @HarcoChen
- MaaEnd 用户页仅在普通模拟器模式显示游戏资源选择，桌面与云终末地模式隐藏该选项。 by @HarcoChen
- 修复 MaaEnd 在游戏退出后再次启动时可能误报失败并浪费一次重试的问题。 by @HarcoChen
- 修复 MaaEnd 重试时带入失效任务及无可执行任务时等待超时的问题。 by @HarcoChen
- MaaEnd 用户页扩大表单可用宽度，并重新排列用户名、剩余天数和启用状态等基本信息。 by @HarcoChen
- MFW专项 修复 interface.json 里 agent 写作 python（如 MAA_Punish）的项目一启动就报「Agent 进程已退出」的问题 by @qiyinxi
- MFW专项 修复分平台发布的项目（如 MAA_Punish）运行前检查更新时报「对应架构和系统下的资源不存在」的问题 by @qiyinxi
- 修复快速配置开关无法可靠保存、关闭后仍影响任务的问题，并移除不支持快速配置的无效入口。 by @1w1w11w1
- 初始化遇到仓库异常时会直接说明需要删除的文件和重新下载方法。 by @ClozyA
- 绝区零一条龙 修复代理任务已完成（含仅个别节点失败、次日自动重试）仍被历史记录标记为失败的问题 by @AthenaHibou

### 开发流程

- 开发环境未通过 yarn dev 启动时直接报错退出，不再静默加载陈旧的构建产物 by @1w1w11w1
- 补上 MaaFW 引擎的 AGENTS.md，并修正专项适配 skill 里把 MaaFW 当专项、声称三态的两处说明 by @qiyinxi
- 更新日志改为每个 PR 在 changelog.d/ 放一个碎片，由「准备发版」工作流统一编译进 CHANGELOG.md 并推进版本号；普通 PR 不再改 CHANGELOG.md 与版本号，合并后补署名的机器人随之移除 by @qiyinxi

## [v5.5.0-beta.5] - 2026-09-12

### 新增

- BAAH专项 新增碧蓝档案爱丽丝助手脚本支持，可集中管理多个账号的配置并自动完成每日任务 by @audiencegeg-glitch
- MAA专项 日常调度新增「更换主题」开关，勾选后计划运行时执行 MAA 里配好的界面主题更换（多个主题随机切换，需 MAA v6.17.3 及以上）；库存保持的关卡下拉只显示真正掉落该材料的关卡、按「刷一件要多少理智」从省到贵排序，并新增库存列显示当前仓库数量 by @jinghero
- MFW专项 同一个任务可以重复加入任务队列，每一份各自配置选项与排序；设了「每日/每周/每月仅一次」的任务仍按任务计、一轮只跑一次 by @qiyinxi
- 模拟器 2.0 支持由原有全局开关控制的「大雷主人模式」，并新增「打开游戏中心」按钮 by @qiyinxi
- 初始化 下载前先对各下载源测速并按最快的顺序使用，安装 Python 与依赖时显示当前文件、进度、速度与来源 by @qiyinxi
- 星铁专项 可以自动更新三月七助手与 SRA 了：默认关闭，开启后在任务全部跑完时检查并安装新版，配置页也能随时手动检查或立即更新；三月七助手走 GitHub 或 Mirror 酱，SRA 还多一个免 CDK 的 AUTO-MAS 下载站。更新可回滚，中途失败会还原到原版本，你自己的配置文件和另存的自定义策略不会被动到；脚本正开着窗口时跳过本轮 by @qiyinxi

### 变更

- 性能与清理 编辑页连续改动不再丢失，配置文件损坏时保留副本而不是静默清空；日志页、模拟器页、签到页与工具页不再高频轮询，任务日志改为增量推送，MAA 起步不再卡顿一秒，运行日志不再被访问记录撑大；并移除前端从不使用的 9 个接口（MCP 同名工具一并消失）与约两万行无用代码 by @qiyinxi

### 修复

- 绝区零一条龙 修复「快速导入配置」没有带入所选实例的按键配置（键盘/手柄按键、后台模式、输入方式等），导入后按键仍是默认值的问题 by @AthenaHibou
- 模拟器 2.0 修复雷电 VBox 服务卡住时（窗口开了、虚拟机起不来、MAA 报 ADB 连接异常且反复重试）的启动问题：会自动关掉空窗口并重启该服务再试一次，但只要还有实例在运行或正在启动就不碰、改为提示先关闭它们；启动前还会检查 VBox 运行时是否被修复工具修残（缺 GPU 库导致虚拟机启动几十秒后崩溃），缺了就从雷电安装目录补回，补不回时明确报错；MuMu 实例启动失败或超时时报错附上 MuMu 自己给出的错误码、错误信息和实例状态 by @qiyinxi
- 修复社区通知重复发送、标题重复及同名 Webhook 漏发签到摘要的问题；修复库街区签到失败及凭据兼容问题，分别显示游戏与库洛币的签到结果、奖励和失败原因
- MAA专项 修复 MAA 内配置方案与新版配置文件不一致时脚本设置、自动代理与 MAA 更新任务直接报错中断，理智不足时剿灭被误记为本周已完成、当周剩余剿灭不再执行，以及本周剿灭已完成时仍被判定为部分任务执行失败并反复重跑的问题 by @1w1w11w1
- MAA专项 修复活动关优先失败但后续理智作战完成时整轮仍被判失败的问题
- 调度中心 修复任务完成后没有执行设定的关机、重启等电源操作、倒计时结束后只有软件退出，以及任务运行期间日志被大量「订阅已存在，跳过重复订阅」记录刷屏的问题 by @1w1w11w1
- 修复绝区零一条龙运行记录被写坏时整个任务直接异常、无法继续运行的问题 by @1w1w11w1
- HSR专项 修复三月七助手的输出在日志与通知里全是 `\uXXXX` 乱码、失败原因只截到一条 WARNING，以及识屏超时自己关掉游戏却被报成「若是用户主动关闭游戏」的问题；通知 Webhook 被钉钉/企微/飞书/OneBot 拒收时不再记成推送成功，会在任务页提示失败原因 by @qiyinxi
- MFW专项 修复运行环境准备时 Agent 依赖不走镜像、直连 PyPI 导致「隔离 venv 依赖安装失败」（现按镜像依次重试并提示失败原因）；beta.4 下脚本完全无法运行、一开跑就报「MaaFW runner worker exited without result」并提示缺少 loguru；agent 运行环境装到与项目自带 MaaFramework 不匹配的 maafw 版本导致每次都卡在「AgentClient 连接超时」（已装错的环境会自动重建一次）；首次更新自行解压的项目时不清理旧版残留文件导致资源加载失败；以及运行环境准备与脚本运行被电脑上的全局 uv 配置文件和 PYTHON 系环境变量带偏的问题，依赖解析只按 MAS 选定的下载源进行，脚本与 Agent 不再继承宿主的 Python 环境变量 by @qiyinxi
- 修复应用启动过程中后台弹出无意义的 Network Error 提示、且启动后首页卫星动画不显示的问题 by @1w1w11w1
- MaaEnd专项 修复脚本更新移除旧任务后，自动代理重试反复报「没有启用的任务」并卡住的问题；现在会自动跳过这些任务并提示重做「MaaEnd 配置」 by @1w1w11w1
- 修复脚本配置目录含只读文件（如脚本自带的 `.git` 版本库）时，任务收尾复原配置失败、整单被记为异常的问题 by @1w1w11w1
- OK-WW专项 修复脚本配置页点「检查更新」后任务立即报错、鸣潮客户端手动更新无法开始的问题 by @1w1w11w1

## [v5.5.0-beta.4] - 2026-09-10

### 新增

- MAA 专项 日常调度新增「更换主题」开关：勾选后 MAS 计划运行时会执行 MAA 里配好的界面主题更换（多个主题随机切换），主题名称仍在 MAA 中配置，需要 MAA v6.17.3 及以上版本 by @jinghero by @HarcoChen
- 绝区零一条龙专项 用户卡片新增「用户模式/直控模式」来源、区服、账号尾号与一条龙任务数标签，并修复 MaaFW 专项用户卡片不显示任何标签的问题 by @AthenaHibou
- MFW专项 使用模拟器时可顺带把游戏一起打开（包名自动识别或手动填写），任务前后自定义脚本改为每用户各跑一次、不再随重试重复 by @HarcoChen
- MFW专项 同一个任务可以重复加入任务队列，每一份各自配置选项与排序；设了「每日/每周/每月仅一次」的任务仍按任务计，一轮只跑一次 by @qiyinxi by @HarcoChen
- 模拟器 2.0 支持由原有全局开关控制的「大雷主人模式」，并新增「打开游戏中心」按钮 by @qiyinxi by @HarcoChen
- 初始化 下载前先对各下载源测速并按最快的顺序使用，安装 Python 与依赖时显示当前文件、进度、速度与来源 by @qiyinxi by @HarcoChen
- 星铁专项 可以自动更新三月七助手与 SRA 了：默认关闭，开启后在任务全部跑完时检查并安装新版，配置页也能随时手动检查或立即更新；三月七助手走 GitHub 或 Mirror 酱，SRA 还多一个免 CDK 的 AUTO-MAS 下载站。更新采用可回滚的事务方式，中途失败会还原到原版本，你自己的配置文件和另存的自定义策略不会被动到（与上游同名的模板文件会随更新覆盖）；脚本正开着窗口时会跳过本轮而不是强行关掉它 by @qiyinxi by @HarcoChen

### 变更

- 全局设置 虚拟显示器改为常驻监测：运行期间检测不到真实显示输出自动挂上，恢复后自动拆掉（任务运行中等结束再拆）；说明里可直接点开 Parsec 驱动下载页 by @qiyinxi
- 日志清理 MFW 项目的 MaaFramework 原生日志备份改为按保留天数一并清理，不再无限堆积
- 性能与清理 编辑页连续改动不再丢失，配置文件损坏时保留副本而不是静默清空；日志页、模拟器页、签到页与工具页不再高频轮询，任务日志改为增量推送，MAA 起步不再卡顿一秒，运行日志不再被访问记录撑大；并移除前端从不使用的 9 个接口（MCP 同名工具一并消失）与约两万行无用代码 by @qiyinxi by @HarcoChen

### 修复

- 模拟器 2.0 修复雷电实例在关机或启动中时被误判为「别家模拟器」、上线后 ADB 地址被清空、MAA 直接报 ADB 连接异常的问题（beta.5 首日生产实测） by @qiyinxi
- 模拟器 2.0 雷电的 VBox 服务卡住时（窗口开了、虚拟机起不来、MAA 报 ADB 连接异常且反复重试），启动会自动关掉空窗口并重启该服务再试一次；只在所有实例都异常时才动手，只要还有任何一台实例在运行或正在启动就不碰，改为明确提示先关闭它们或运行雷电修复工具 by @qiyinxi by @HarcoChen
- 模拟器 2.0 的 MuMu 实例启动失败或超时时，报错里附上 MuMu 自己给出的启动错误码、错误信息和实例状态，不再只有一句「启动超时」 by @qiyinxi by @HarcoChen
- 修复社区通知重复发送、标题重复及同名 Webhook 漏发签到摘要的问题。 by @HarcoChen
- MAA专项 修复 MAA 内配置方案与新版配置文件不一致时，脚本设置、自动代理与 MAA 更新任务直接报错中断的问题 by @1w1w11w1 by @HarcoChen
- 修复库街区签到失败及凭据兼容问题，分别显示游戏与库洛币的签到结果、奖励和失败原因。 by @HarcoChen
- MAA专项 修复理智不足时剿灭被误记为本周已完成、当周剩余剿灭不再执行的问题 by @1w1w11w1 by @HarcoChen
- MAA专项 修复本周剿灭已完成时仍被判定为部分任务执行失败并反复重跑的问题 by @1w1w11w1 by @HarcoChen
- MAA专项 修复活动关优先失败但后续理智作战完成时整轮仍被判失败的问题 by @HarcoChen
- 调度队列 修复任务完成后没有执行设定的关机、重启等电源操作，倒计时结束后只有软件退出的问题 by @1w1w11w1 by @HarcoChen
- 修复绝区零一条龙由 MAS 启动时报「运行环境同步失败」，且自动模式失败后不切换启动器的问题
- MaaEnd 专项 适配 MaaEnd 2.28：基质刷取可按模式（随机/地区/目标）选择地点与目标武器，应急理智加强剂并入理智任务设置，任务不再因「没有启用的任务」或已被上游移除的旧任务而反复失败 by @HarcoChen
- 修复绝区零一条龙运行记录被写坏时整个任务直接异常、无法继续运行的问题 by @1w1w11w1 by @HarcoChen
- 修复配了网络代理的用户初始化下载仍直连、卡在「程序文件」一步的问题 by @qiyinxi by @HarcoChen
- HSR专项 修复系统区域非中文时三月七助手每个模块被判失败、整轮重复运行的问题 by @HarcoChen
- HSR专项 修复系统区域非中文时三月七助手的输出在日志与通知里全是 `\uXXXX` 乱码、失败原因只截到一条 WARNING、三月七助手识屏超时自己关掉游戏却被报成「若是用户主动关闭游戏」的问题；通知 Webhook 被钉钉/企微/飞书/OneBot 拒收（关键词、签名、群不存在等）时不再记成推送成功，会在任务页提示失败原因 by @qiyinxi by @HarcoChen
- 修复 MFW、M9A、HSR 与主页的一批问题：多项设置从未生效、MFW 更新不上、HSR 周常与历战余响提前翻页、重返未来 1999 倒计时偏移、国内下载源缺分支导致初始化失败
- 修复后端就绪前退出时只能反复重试的问题，现同时提供「重建运行环境」入口 by @qiyinxi by @HarcoChen
- MAA专项 修复未返回分服关卡数据时用户配置页打不开的问题 by @qiyinxi
- 模拟器管理 修复部分 MuMu 因命令输出混有日志而无法读取信息的问题 by @qiyinxi
- MFW专项 修复运行环境准备时 Agent 依赖不走镜像、直连 PyPI 导致「隔离 venv 依赖安装失败」的问题，现按镜像依次重试；失败原因也会写进日志并显示在提示条上，不再只有一句准备失败 by @qiyinxi by @HarcoChen
- MFW专项 修复 beta.4 下 MFW 脚本完全无法运行、一开跑就报「MaaFW runner worker exited without result」并提示缺少 loguru 的问题 by @HarcoChen
- MFW专项 修复 agent 运行环境装到与项目自带 MaaFramework 不匹配的 maafw 版本，导致每次运行都卡在「AgentClient 连接超时」的问题；已经装错的环境会自动重建一次 by @HarcoChen
- MFW专项 修复首次更新「自己解压好、再指给 MAS」的项目时不清理资源目录里的旧版残留文件，新版挪走或删掉的文件留在原地导致资源加载失败、项目彻底跑不起来的问题 by @qiyinxi by @HarcoChen
- 修复应用启动过程中后台弹出无意义的 Network Error 提示、且启动后首页卫星动画不显示的问题 by @1w1w11w1 by @HarcoChen
- MFW专项 修复运行环境准备与脚本运行会被电脑上的全局 uv 配置文件和 PYTHON 系环境变量带偏的问题：依赖解析只按 MAS 自己选定的下载源进行，脚本与 Agent 不再继承宿主的 PYTHONPATH、PYTHONWARNINGS 等变量 by @qiyinxi by @HarcoChen
- MaaEnd专项 修复脚本更新移除旧任务后，自动代理重试反复报「没有启用的任务」并卡住的问题；现在会自动跳过这些任务并提示重做「MaaEnd 配置」 by @1w1w11w1 by @HarcoChen
- 修复脚本配置目录含只读文件（如脚本自带的 `.git` 版本库）时，任务收尾复原配置失败、整单被记为异常的问题 by @1w1w11w1 by @HarcoChen
- OK-WW专项 修复脚本配置页点「检查更新」后任务立即报错、鸣潮客户端手动更新无法开始的问题 by @1w1w11w1 by @HarcoChen
- 调度台 修复任务运行期间日志被大量「订阅已存在，跳过重复订阅」记录刷屏的问题 by @1w1w11w1 by @HarcoChen
- MAA专项 修复在配置检查通过后、任务正式开始前停止任务时被报成「MAA任务出现异常」的问题 by @1w1w11w1 by @HarcoChen
- 修复日志文件在运行过程中被重建或删除时，日志监控会静默失效、该趟任务再也不会被正常判定（卡到超时或误报异常）的问题 by @1w1w11w1 by @HarcoChen

### 开发流程

- 首页卫星图标改从全局图标表取，新增专项时不再漏掉主页卫星

## [v5.5.0-beta.3] - 2026-09-09

### 破坏性变更

- 森空岛获取凭据改为扫码登录，完善社区签到、云游戏时长与日常便笺 by @Lance0174 by @HarcoChen
- MFW 项目新增自动更新时机设置，**已有脚本默认「运行前更新」**，不需要可改为「不更新」；可选下载源（Mirror 酱 / GitHub）与更新通道（稳定版 / 测试版） by @qiyinxi by @TCddddd by @HarcoChen
- HSR 脚本页「游戏启动参数」已移除，**旧配置下次保存时自动清除**；窗口大小改由「1920×1080 窗口模式」开关控制 by @qiyinxi by @HarcoChen
- MAA 代理接管时**强制开启账号切换开关**以确保按配置切号；未填账号时不切号 by @1w1w11w1 by @HarcoChen
- MAA、SRC、MaaEnd 与 OK-NTE 用户页配置模式**由「简洁/详细」更名为「脚本/用户」**，含义不变，自动迁移 by @1w1w11w1 by @HarcoChen
- MAA 计划表不再强制关闭「库存保持」；此前开启过的升级后自动生效，**库存保持先于理智作战执行** by @jinghero by @HarcoChen

### 本次亮点

- 新增绝区零一条龙（ZZZ-OD）专项，支持独立模式与直控模式 by @HarcoChen
- 模拟器管理新增「Emulator 2.0」：一条配置纳管多个雷电 14 / MuMu 6 实例 by @HarcoChen
- 调度队列新增循环队列，任务可按固定时间或间隔持续运行 by @HarcoChen
- 启动速度大幅优化，启动与初始化等待画面重做 by @HarcoChen
- 通知系统支持微信 Claw 与 QQ 官方机器人接收任务通知 by @HarcoChen

### 新增

- 模拟器管理 新增「Emulator 2.0」：一条配置纳管多个雷电 14 / MuMu 6 实例，支持新建删除、分辨率/CPU/内存/帧率批量设置与「配置守卫」自动还原 by @qiyinxi by @TCddddd by @HarcoChen
- MaaEnd专项 新增脚本直控模式与每日仅执行一次，抢委托送货与自动采集独立为可单独配置的阶段 by @HarcoChen by @TCddddd
- 绝区零一条龙（ZZZ-OD）专项适配：支持用户独立模式与直控模式 by @AthenaHibou by @TCddddd by @HarcoChen
- 调度队列 新增循环队列（固定时间或间隔重复运行）；选中脚本后可指定单用户单独运行；完成后操作支持自定义延时 by @qiyinxi by @TCddddd by @HarcoChen
- OK-NTE专项 支持按手机号后 4 位切换登录账号，支持经启动器拉起异环游戏，新增问题包一键导出 by @AthenaHibou by @TCddddd by @HarcoChen
- 通知系统 支持扫码绑定微信 Claw 和 QQ 官方机器人并接收任务通知 by @HarcoChen by @TCddddd
- HSR专项 用户配置页新增「额外脚本」，可在任务前后各执行一个自定义脚本 by @qiyinxi by @TCddddd by @HarcoChen
- MAA专项 新增绿票商店开关；托管结束后保存 MAA 每日状态，同一天多次托管不再重复执行 by @qiyinxi by @1w1w11w1 by @TCddddd by @HarcoChen
- 首页 快速启动支持多选并记住上次选择 by @Craun718 by @TCddddd by @HarcoChen
- 全局设置 新增虚拟显示器：无真实显示输出时临时挂 1920×1080 虚拟屏，任务结束即拆除；更新提示改为按版本分区块展示，可在设置页随时查看更新日志 by @qiyinxi by @TCddddd by @HarcoChen
- BetterGI专项 用户编辑页一条龙配置改为可视化拖拽队列，战斗四项各支持多个独立实例 by @TCddddd by @HarcoChen

### 变更

- 启动界面 等待画面重做，出错给出一句话原因和主要操作，取消自动重试；大幅优化前端加载与启动速度 by @qiyinxi by @1w1w11w1 by @HarcoChen
- HSR专项 脚本直控不再要求先导入快照，新增 SRA 配置档案下拉，管控任务配置项补齐中文名；用户页文案接入多语言词表 by @qiyinxi by @HarcoChen
- 后端更新 自动在后台下载并于下次启动生效；Runtime 接入后由 auto-mas-runtime.exe 统一完成初始化与监督 by @ClozyA by @qiyinxi by @HarcoChen
- 首页 弱网下活动数据异常不再拖累所有请求；快速启动后自动跳转调度中心 by @1w1w11w1 by @Craun718 by @HarcoChen
- MFW专项 进入项目配置页不再每次等运行环境确认；通用脚本未填配置路径时任务前直接提示 by @qiyinxi by @HarcoChen
- 帮助入口 计划管理、模拟器管理等页面增加直达文档入口；自动清理 OCR 图片 by @1w1w11w1 by @HarcoChen
- 代码清理 统一导入排序、合并重复逻辑、清理死代码与无用组件；前端类型治理清理 any；OK-WW 清理无效选项；BetterGI 编辑页接入 i18n 词表 by @1w1w11w1 by @HarcoChen by @qiyinxi

### 移除

- 移除米游币获取任务，保留米游社各游戏签到 by @Lance0174

### 修复

- BetterGI专项 修复一条龙配置级联退化与保存报错、跨零点日志误判、重试报告重复、GUI 残留配置、切号误删仓库与设置事件接收等问题 by @TCddddd by @1w1w11w1 by @Craun718 by @qiyinxi by @HarcoChen
- Emulator 2.0 修复模拟器已运行时不打开游戏、雷电与 MuMu 同时运行时操作打到另一台的问题 by @qiyinxi by @TCddddd by @HarcoChen
- HSR专项 修复任务配置文本项输入被清空、开启培养目标后历战余响不刷、三月七自行关游戏导致误判失败、脚本升级后覆盖配置让表单消失等问题 by @qiyinxi by @TCddddd by @HarcoChen
- MAA专项 修复日常任务误用剿灭队列、剿灭体力耗尽误判完成、v6.14 后不切号等问题 by @1w1w11w1 by @qiyinxi by @TCddddd by @HarcoChen
- MaaFW专项 修复 Python 运行时损坏延迟报错、受限网络无镜像、环境不可用反复重启模拟器、建项向导跳过环境检查等问题 by @qiyinxi by @TCddddd by @HarcoChen
- OK-WW与OK-NTE专项 修复多用户切号窗口定位与退出残留、体力报告误显与任务推送失败等问题 by @AthenaHibou by @TCddddd by @HarcoChen
- 修复启动界面日志窗口空白、深色模式标题栏变暗、双窗口抢连接、渲染崩溃黑屏等 UI 问题 by @qiyinxi by @ClozyA by @TCddddd by @HarcoChen
- 修复后端断连立即弹窗阻塞（改为非阻塞提示）与更新后端时误报失去连接的问题 by @qiyinxi by @TCddddd by @HarcoChen
- 日志与签到 修复日志跨零点后运行历史丢失、社区签到重复推送与首页日期格式异常黑屏等问题 by @AthenaHibou by @Lance0174 by @1w1w11w1 by @TCddddd by @HarcoChen
- MaaEnd专项 修复更新后已完成任务被误判失败并重试的问题 by @HarcoChen by @TCddddd
- 通用脚本 修复直控配置模式下文件占用时配置目录被部分删除且不还原的问题；修复明日方舟 PC 工具连接失败后每秒重试 by @qiyinxi by @HarcoChen

### 开发流程

- 新增 GitHub Issue 模板；清理未达规范的测试文件并重新生成前端接口代码；禁止 AI 助手协助 force push by @qiyinxi by @1w1w11w1 by @Craun718

## [v5.5.0-beta.2] - 2026-08-31

### 新增

- 前端i18n 新增日本語与英文界面选项，首次启动跟随系统语言；主要页面界面文案与状态标签接入词表 by @qiyinxi by @HarcoChen
- 日志处理 新增日志处理钩子层（成功/失败标志正则匹配），日志采集 API 落地为通用 log_box 组件；OK-WW 首个接入运行日志节点推送 by @qiyinxi by @AthenaHibou by @TCddddd by @HarcoChen
- OK-WW专项 支持启动前按手机号后 4 位切换登录账号并新增问题包导出；自行接管鸣潮游戏更新（多 CDN 断点续传、增量补丁优先、校验后原子替换） by @1w1w11w1 by @AthenaHibou by @TCddddd by @qiyinxi by @HarcoChen
- OK-NTE专项 运行日志关键节点注入任务报告；OK-WW 与 OK-NTE 任务报告详情可选关闭/逐条/汇总三种模式 by @AthenaHibou by @qiyinxi by @HarcoChen
- MaaFW专项 新增 MaaFW 脚本类型，可直接托管 MaaFramework 项目（ADB 模拟器与 Win32 两条链路）；自定义 Webhook 新增 {gamedate} 变量 by @qiyinxi by @HarcoChen
- 调度队列 新增每日首次启动运行队列；托盘图标右键菜单支持自定义；BetterGI 专项新增原神脚本适配与一条龙自动代理 by @luo-luo-o by @1w1w11w1 by @TCddddd by @qiyinxi by @HarcoChen

### 变更

- 架构优化 新增 utils/services 平台层；接入主进程与渲染进程错误上报，抑制无异常日志并遮蔽本机用户名 by @HarcoChen by @ClozyA by @qiyinxi
- MaaFW项目 interface 解析接上闲置缓存（用户页进入耗时 5.5s→0.12s）；单独运行脚本不再受单日代理次数上限约束；任务成败判定改用协议中的机器可读字段 by @qiyinxi by @HarcoChen
- 通知系统 各类通知统一走同一渠道分发层；MaaFW 运行日志记录实际加载版本与来源，版本不一致或架构不匹配时给出提示 by @1w1w11w1 by @qiyinxi by @HarcoChen
- 清理无用前端资源、依赖及后端冗余代码 by @1w1w11w1 by @qiyinxi by @HarcoChen

### 修复

- 前端i18n 修复含「|」的说明文案被 vue-i18n 截断的问题；修复接入词表后 MaaEnd 与 HSR 编辑页无法加载、HSR 只填三月七路径时任务被分配给 SRA、未配 SRA 路径时多用户静默跑同一账号的问题 by @qiyinxi by @HarcoChen
- 修复 Mirror 酱一次性下载地址被版本检查缓存复用导致更新失败、系统通知标题过长推送失败、自定义 Webhook 推送本地目标绕过代理的问题 by @qiyinxi by @ArmedHelicopter by @HarcoChen
- MAA专项 修复任务生成覆盖用户原生高级配置、HSR 托管开关报错、剿灭队列与库存保持并修复移除生息演算的问题 by @1w1w11w1 by @qiyinxi by @HarcoChen
- 修复 M9A 任务跨午夜后日志监控读取前一天文件、队列「每日首次」跨日前十秒冷启动漏跑或重跑、日志文件被替换后监控读不到新内容、系统时钟跳变导致任务误判超时与历史偏移的问题 by @qiyinxi by @HarcoChen
- MaaFW专项 修复 Win32 窗口定位超时类型不符失败、MXU 项目识别不出家族导致更新包选不出、内置运行未加载项目自带 MaaFramework、Python 绑定版本不符、运行期间界面日志停更与停止无响应、旧环境永久占用磁盘、中止后 Agent 残留、单任务失败不即时提示、游戏启动失败后空转到超时、用户级通知配置无效、调试日志轮转只保存后半段的问题 by @qiyinxi by @HarcoChen

### 开发流程

- 开发环境改用独立端口与 userData，可与正式版同时运行；前端检查与格式化迁移至 oxlint/oxfmt；添加 pyproject 和 ruff 配置 by @qiyinxi by @Craun718 by @HarcoChen

## [v5.5.0-beta.1] - 2026-08-28

### 新增

- MAA专项 支持启动前检查并更新明日方舟客户端 by @1w1w11w1 by @qiyinxi by @HarcoChen
- OK-WW专项 支持启动前自动更新鸣潮客户端 by @1w1w11w1 by @qiyinxi by @HarcoChen
- 日志采集 支持将运行节点推送至任务报告 by @AthenaHibou by @qiyinxi by @HarcoChen
- 调度队列 支持每日首次启动时运行队列 by @luo-luo-o by @qiyinxi by @HarcoChen
- 界面设置 支持自定义托盘菜单及任务控制命令；支持一键备份数据 by @1w1w11w1 by @qiyinxi by @HarcoChen

### 变更

- MAA专项 重构用户配置页面 by @1w1w11w1 by @qiyinxi by @HarcoChen
- 专项任务移除人工排查模式并统一签到入口 by @1w1w11w1 by @qiyinxi by @HarcoChen
- 前端界面 统一编辑页样式并优化状态管理 by @ClozyA by @qiyinxi by @HarcoChen

### 修复

- SRC专项 修复任务结束后的进程与配置清理问题 by @Craun718 by @qiyinxi by @HarcoChen
- MaaEnd专项 修复脚本退出后任务持续等待问题 by @HarcoChen by @qiyinxi
- HSR专项 修复 M7A 切换界面失败未重启任务问题 by @1w1w11w1 by @qiyinxi by @HarcoChen
- 修复开机自启动后台任务异常未记录、通知服务延迟加载导致错误的问题 by @1w1w11w1 by @AthenaHibou by @qiyinxi by @HarcoChen
- 日志采集 修复多用户节点详情被合并推送的问题；统一推送配置区样式，修复新增/删除规则时过早弹出缺字段提示的问题 by @AthenaHibou by @qiyinxi by @HarcoChen

### 开发流程

- 修复前端类型与 lint 检查问题 by @1w1w11w1

## [v5.4.0] - 2026-08-26

### 变更

- MaaEnd专项 增强账号切换 by @qiyinxi

### 修复

- OK-WW专项 修复任务在日志产生前手动终止时历史记录误显示未捕获到日志的问题 by @qiyinxi by @HarcoChen
- OK-NTE专项 修复任务结束后异环启动器进程残留并持续占用内存的问题 by @qiyinxi by @HarcoChen
- MAA专项 修复开启活动关优先后普通理智作战的理智药额度被静默清零的问题，两个作战任务各自使用独立理智药额度 by @qiyinxi by @HarcoChen

[v5.5.0-beta.6]: https://github.com/AUTO-MAS-Project/AUTO-MAS/compare/v5.5.0-beta.5...v5.5.0-beta.6
[v5.5.0-beta.5]: https://github.com/AUTO-MAS-Project/AUTO-MAS/compare/v5.5.0-beta.4...v5.5.0-beta.5
[v5.5.0-beta.4]: https://github.com/AUTO-MAS-Project/AUTO-MAS/compare/v5.5.0-beta.3...v5.5.0-beta.4
[v5.5.0-beta.3]: https://github.com/AUTO-MAS-Project/AUTO-MAS/compare/v5.5.0-beta.2...v5.5.0-beta.3
[v5.5.0-beta.2]: https://github.com/AUTO-MAS-Project/AUTO-MAS/compare/v5.5.0-beta.1...v5.5.0-beta.2
[v5.5.0-beta.1]: https://github.com/AUTO-MAS-Project/AUTO-MAS/compare/v5.4.0...v5.5.0-beta.1
[v5.4.0]: https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/tag/v5.4.0
