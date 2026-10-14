# 插件化迁移收尾交接文档

更新时间：2026-10-14
工作区：D:/Dev/AUTO-MAS
分支：refactor/plugin-migration-v3
当前 HEAD：81531182（本轮改动尚未提交）

## 状态

后端准入与前端活动依赖收口已通过；本轮已补齐 i18n、插件动态表单和页面验收发现的调度/历史问题。最后的显示修正已补跑全部前端门槛并通过；本轮已确认范围的实现和收尾验收完成。结果见 .dev 内最新日志。旧记录中的 14 项收集错误、32 项后端失败和 471 个前端类型错误已解决，不能继续作为当前阻塞项。

不得重置工作区、自动提交、推送、打包或切换分支。旧专项源码保留在后端原目录及 frontend/deferred；有独立诊断入口，不能重新接入活动构建或恢复假 API。tests 下验证修改默认不提交，遵循 tests/AGENTS.md。

## 已确认边界

- 旧 ConfigBase、TaskManager、EmulatorManager 不进入实际运行链路。
- JSON → YAML 只做一次启动升级，成功后归档；运行期不双读。
- 配置接口通过新对象的部分补丁 update() 执行；隐藏凭据仅允许内部更新。
- 无用户的共享脚本配置派发运行时 Default，不写入真实用户集合。
- 队列 userId 是起点游标；脚本＋用户且无队列的请求用于单用户快速运行。
- 定时、循环和启动均进入 TaskDispatcher；循环由主计时器维护 next_run_at。
- 验收不启动自动队列、真实 MAA 业务、真实通知投递或社区签到。
- PC 工具后端继续停用，源码与前端参考保留；其他专项另立迁移任务。
- 24 格仅用于配置组，页面外层沿用旧结构。button=6、select=8、Path=12；宽度≤768px 且长宽比≤1:1 时单项占满24格。
- 布尔值用文字按钮，关闭态红边框/红文字，无固定状态图标。
- 客户端只由 OpenAPI 生成器更新；不手改 src/api，不新增自动下载外部 MAA 的流程。

## 已实现

### 后端

- 插件发现、依赖启用、失败隔离、自有配置和注册表已接入主生命周期。
- MaaFW 祖先包公共导出按需加载，不提前拉入宿主配置/调度。
- 健康 protocol/version/commit/backgroundWarnings、受监督版本判断、WS 替换4001及关闭顺序已修复。
- 通知编排读取新 Setting/UserEntry/Webhook，保留渠道和失败隔离；设置 Trigger、插件通知、测试和签到通知使用统一入口。QQ 部分凭据补丁、隐藏字段与启停已验证。
- 任务取消支持 ALL，重复取消和启动前取消有唯一收尾；异常/检查失败能写入历史，配置还原和锁释放已验证。
- 账号与全局 Webhook 复用既有 Schema 的 scriptId/userId 归属参数，实现读取、增删改和排序隔离；托管编辑页复用 WebhookManager，操作24px。测试按钮走配置 update Trigger，反馈为请求已提交；全局/临时测试接口也使用 update 提交，避免只赋值不触发。
- 运行快照以 TaskDispatcher 为事实源，前端读取真实任务树。计划删除保护真实用户引用。
- 历史搜索增加 CANCELLED，取消不再映射成失败，列表和详情均正确展示。
- 社区与活动读取、基础工具及显示器解除接口沿用新配置接线；PC 服务没有重新导入启动。

### 前端

- 活动 src 接受完整类型检查；旧专项模块保存在 frontend/deferred，并有 typecheck:deferred/test:deferred 入口。
- backendI18n Pinia store 在 Pinia 就绪后注册常驻资源，处理连接恢复、语言变更、i18n.updated。旧响应不会覆盖新语言；替换后端命名空间清除卸载插件词条；缺失 key 占位不会覆盖原译文。加载失败有重试。
- 语言选择仍保存在原前端配置；资源查询显式映射 zh-CN→zh_CN、en-US→en、ja-JP→ja，后端无该语言时使用其 fallback。静态界面保留原词表，插件和动态字段优先使用后端资源。
- 动态字段键为 plugins.<插件名>.config.<类型>.<组>.<字段>.label/tip，核心字段可用 core.config.<类型>.<组>.<字段>.label/tip；选项后缀 options.<值>。插件自有配置使用 plugins.<插件名>.config.<组>.<字段>。
- 插件中心合并运行时与注册表，展开完整属性；名称、描述、标签、状态与来源本地化。市场作为子页，返回位于右上角。
- 插件自有配置只读自有声明，复用 DeclarativeControl；Path、密码、数字、日期、select、bool 和 Trigger 共用呈现。Literal Trigger 提交实际值，保存后回读。
- 托管页面保留旧结构、紧凑用户操作和专用配置来源/覆写组件；tags 只在总览。游戏、设备和计划下拉通过声明 endpoint 查询；已补 path_kind 与单用户运行。
- 计划保留矩阵外观，ui.tables 驱动列/行，Literal 选项已可选并保存。
- 调度按查询来源区分队列/脚本，不依赖中文标签。起点用户下拉刷新时保持可打开，启动按钮仍等待选项加载完成。
- 主页、队列、设置、游戏、工具、社区及历史活动 API 已接线。旧设置分页和配置卡分组保留；密码和普通输入实测均40px。

## 验证事实

- uv run python -m compileall -q app plugins：通过。
- uv run python -m pytest tests app/plugin/tests -q：399 passed、4 skipped、23 subtests passed；最近日志 .dev/backend-full-regression-final.log。四项跳过不算通过。
- MaaFW 通用核心：12 passed；资源/声明定向：7 passed。
- .dev/backend_migration_acceptance.py：模拟 MAA/MUMU 绑定、Default、设备订阅、取消、异常历史、锁/配置还原及重启查询通过；计划创建/更新/排序/引用保护/删除通过。
- .dev/webhook_scope_acceptance.py：全局/账号隔离、CRUD/排序、非法归属、Trigger 提交复位和模拟通知通过；浏览器账号 Webhook 保存已核对持久化，仅写入隔离账号集合。
- .dev/config_contract_acceptance.py、notification_acceptance.py、task_cancel_acceptance.py：通过，均为隔离验证产物。
- 最近整轮前端：74 files / 999 tests passed；typecheck、lint --max-warnings 1、format:check、vite build 通过。i18n 新测试覆盖资源替换、旧语言响应竞态与失败重试。最后显示修正已重跑并通过：typecheck、999项测试、lint、format:check、Vite build。
- CSS 变量审计：NO_UNDEFINED_VARS；未发现 useTheme 外的 prefers-color-scheme。
- API 冒烟：健康 ready，配置/插件/游戏/脚本/计划/工具/调度/i18n/OpenAPI 可读，任务0、定时脚本0。查询配置时禁止打印完整 settings/tools 响应。
- 浏览器验证：真实设置保存并恢复、设备刷新；隔离托管配置来源保存与提示；密码/普通输入40px、编辑页tags=0；计划药量/连战次数保存；队列脚本/用户起点可选；取消历史与日志详情；插件展开/市场返回；主页、队列、游戏、设置、工具、社区读取。暗色及600×900单列通过，语言切换后已恢复简体中文与跟随系统。
- 截图：.dev/previews/history-cancelled.png、settings-portrait-dark.png、user-webhook.png。全部为本地证据，不提交。

## 开发预览与调试注意

正常预览为 http://127.0.0.1:5173/，后端36164。启动前先检查监听进程，避免重复实例；保持一个主 WS 连接，4001 表示被新连接替换。

本次后端使用 .dev/run_development_backend.py 入口：读取真实配置，开发环境，暂停当前调试进程的无人值守社区签到；没有修改用户签到开关。每次重启前确认 time_enabled=false、start_up_mode=Never、循环项 schedule.enabled=false 且任务为空。普通 main.py 会按真实配置启动服务，不能把调试打桩当成产品行为。

隔离验收使用36165/.dev/run_ui_acceptance_backend.py及5174预览，结束时停止。真实配置当前脚本/计划为空，已与原快照核对，不能写入验收假账号作为补救。.dev/ui-acceptance 有指向真实 res/plugins 的目录联接，禁止递归删除！本地快照、日志和临时测试保持忽略，不提交。

## 外部 MAA 来源

MAA 在 plugins/maa_adapter，作为已忽略的本地外部插件保留，版本0.0.1；不纳入主仓库。

pyproject.toml 与 src 下全部 .py/.json，按相对路径排序，将路径（斜杠分隔）及文件字节依次送入 SHA256，当前校验为：

b83782f589a79632c2d912b6ee630bc41643649f720531028f8e2474a1b55269

只验证框架，不保证真实 MAA 配置界面、游戏任务或上游业务结果。原生路径对话框、真实设备启停、QQ/通知投递及系统热键依赖实际环境，自动验收使用模拟器和发送器。

## 交付前最后检查

最终前端门槛通过，预览恢复5173→36164，36165/5174隔离服务已停止。后端新增历史取消状态及最终资源定向回归8项通过，完整399项通过。普通按钮 Trigger 提交True，Literal下拉按钮先展开动作菜单，仅提交所选实际值。保留一个 changelog.d/refactor-plugin-migration-v3.change.md；不改 CHANGELOG、版本或版本资源。本轮没有提交授权。
