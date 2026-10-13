# 插件化迁移收尾交接文档

更新时间：2026-10-13  
当前分支：refactor/plugin-migration-v3  
工作区：D:\Dev\AUTO-MAS

这是一份继续迁移工作的事实交接文档。工作区含大量未提交改动，接手时不要重置、清理、覆盖、提交、推送、打包或切换分支，除非用户另行授权。

## 用户已确认的硬约束

- 先完成后端插件框架、新配置系统、TaskDispatcher、HistoryStore，再做前端逐页迁移。
- 旧 ConfigBase、旧 TaskManager、旧 EmulatorManager 仅保留源码参考，不得进入运行路径。
- JSON 到 YAML 只做一次启动升级；成功后归档旧 JSON，运行期不双读。
- 无 userId 的脚本共享配置使用运行时虚拟用户 Default，不写入真实用户列表。
- 调度 userId 是起点游标；单用户快速运行由托管/脚本管理页提供。
- 循环队列由主计时器按 next_run_at 触发；验收期间禁用定时和循环派发。
- MAA 只验框架机制，不执行真实 MAA 业务调试。
- ui.hints、ui.tables、Literal/Enum 选项由后端声明驱动；ConfigTableColumn 已纳入插件 SDK 公共导出方案。
- 前端 24 格布局只用于配置选项卡内部，页面外层保持旧页面结构和风格。
- 后端 schema 变化必须通过 OpenAPI 生成器更新前端客户端，禁止手改生成文件。

## 当前环境和事实

- 当前分支：refactor/plugin-migration-v3。
- 根目录 .env 已存在，开发后端端口为 36164。
- Vite 已有进程监听 5173，接手时先复用，不要重复启动。
- GET http://127.0.0.1:36164/api/core/health 当前返回 ready、backgroundStatus=ready、backgroundError=null。
- 测试期间已确认队列 time_enabled=false、循环项 schedule.enabled=false、运行任务为空；每次验证前都要再次确认。
- 设置接口含用户配置和密文，不要输出完整响应。

查询型配置接口使用 POST 和 {} 请求体：

- POST /api/plugin/list：当前已确认 auto_mas_core、maa_adapter、mumu_adapter 已启用，ldplayer_adapter、win_process_adapter 已禁用。
- POST /api/games/types：发现 MuMuGame。
- POST /api/scripts/types：发现 MaaScript。
- POST /api/plan/get、POST /api/queue/get：返回 order/data。
- POST /api/dispatch/get：运行任务查询；没有 /api/dispatch/running。
- POST /api/history/search、POST /api/history/data：历史查询和详情；没有 /api/history/list。
- GET /openapi.json：200，可生成 OpenAPI。

## 已完成或已有代码

### 后端

- 新插件宿主、注册表、市场配置、自有配置和声明式插件网关已接入 main.py 生命周期。
- setting、queue、game、script、plan、plugin 等已迁移领域使用新配置集合和 update/commit。
- 启动期 JSON 到 YAML 升级及 config/legacy-json 归档逻辑已加入。
- TaskDispatcher 是运行任务事实源，调度接口为 dispatch/start、stop、get。
- HistoryStore 统一历史保存、查询、详情和清理。
- MUMU 游戏管理发现、实例操作、状态回流已有实现；MAA 框架已有配置、账号展开、设备订阅和统一调度接线。
- 明日方舟 PC 工具已从主启动和主定时入口移除，源码保留。
- uv run python -m compileall -q app plugins 已通过。

### 前端

- OpenAPI 新模型和声明式 UI 基础组件已在工作区生成或新增，最终仍需按稳定 schema 重新生成客户端。
- DeclarativeControl、24 格布局、请求重试/错误提示等共享组件已有。
- Games.vue、DeclarativeControl.vue、declarativeLayout.ts 的局部格式化、oxlint、局部 vue-tsc 已通过。
- 插件中心、设置、脚本/托管、计划、调度、历史等页面都有迁移代码，但尚未逐页验收。

## 当前阻塞

### 后端

1. tests/task/test_maafw_core.py 当前 19 项通过、2 项失败。AST 导入闭包读取到 app/core/ws/dialogs.py 和 dispatcher.py 的 UTF-8 BOM，ast.parse 报 U+FEFF。应修源码编码或修正运行器导入边界，不要放宽测试、不恢复旧配置基类。
2. 修复 BOM 后仍需检查 worker 是否触达允许根 app.task.MaaFW.tools.core.* 之外的宿主模块；越界应修活动导入，不要机械放宽规则。
3. 全量测试此前约 14 个旧框架导入错误，主要来自旧 ConfigBase、旧任务/模拟器和旧模型。暂缓专项应移到 tests/deferred 或明确延后入口；核心测试改验新配置、插件、调度、历史，不恢复废弃模型。
4. app/services/openclaw_qq.py 已读 Config.setting.notify 并通过新配置提交，但 main.py 当前未恢复 QQ manager 的 start/stop 生命周期。接手者先判定是否为迁移缺口；若接回，只能使用新配置。
5. 继续审查签到、通知、桌面守护、更新、WebSocket、脚本入口的活动调用链。app/task 下大量旧专项源码属于暂缓源码，不能凭 grep 结果整体替换。
6. 仍需隔离验证 MUMU/MAA 闭环、取消、历史收尾、重启恢复和插件异常隔离；禁止真实 MAA 任务。

### 前端

1. yarn typecheck 仍被未迁移专项旧 API/模型阻塞。保留源码但从活动构建入口解耦，不恢复虚假 API。
2. Plugins.vue 当前读取 plugin_registry 配置，应该以 POST /api/plugin/list 运行时列表为主，再合并注册表详情。
3. 游戏管理页局部检查已通过，还需真实 API 验收桌面宽度、窄窗口单列、暗色主题、Path 样式和设备操作。
4. 脚本/托管仍缺脚本设置按钮、共享/独立/原生配置来源、覆写常规配置组件、endpoint 下拉框、紧凑用户按钮和 tags 位置。
5. 计划页需确认 ui.tables 驱动表头/行顺序，series_numb 等 Literal/Enum 选项来自声明，并验证增删改、排序和引用限制。
6. 设置、调度、历史、工具、主页和队列仍需逐页切换最终客户端并验证真实保存、取消、错误和空态。

## 推荐接手顺序

### 后端准入

1. 检查 git status、.env、36164、5173 和队列禁用状态。
2. 修复 MaaFW BOM/导入闭包并运行：
   uv run python -m pytest tests/task/test_maafw_core.py -q
3. 收口旧测试归属，运行 pytest --collect-only，确认不再被旧框架导入阻断。
4. 审查 OpenClaw QQ 等活动服务的旧配置访问和生命周期。
5. 运行：
   uv run python -m compileall -q app plugins
   uv run python -m pytest tests/core tests/api tests/task/test_maafw_core.py -q
6. 用 HTTP 冒烟插件、游戏、脚本、计划、设置、调度、历史；查询使用 POST {} 或最小请求体。禁止真实 MAA 和自动队列。

### 前端契约

1. 后端 schema 稳定后在 frontend 运行 yarn openapi，禁止手改 frontend/src/api 生成文件。
2. 解耦 Scripts、计划类型注册、历史/工具页面中的旧专项构建依赖，保留源码。
3. 修正 Plugins.vue 使用运行时插件列表，统一请求/重试/错误/空态。

### 逐页验收

顺序：插件中心/市场 → 游戏管理 → 脚本/托管 → 计划 → 调度/历史 → 设置/工具/主页/队列。每页先用真实 API 验证，再进入下一页。24 格只在配置选项卡内部。

最终前端命令：
   cd frontend
   yarn typecheck
   yarn test --run
   yarn lint --max-warnings 1
   yarn format:check
   yarn vite build

当前命令尚不能整体通过，不能以 Vite 200 代替验收；不执行 Electron 打包。

## 禁止的处理方式

- 不恢复 ConfigBase、旧 TaskManager、旧 EmulatorManager 或旧前端 API 来“修绿”。
- 不删除暂缓专项源码，不以隐藏错误假装完成。
- 不运行期双读 JSON/YAML。
- 不开启定时或循环队列。
- 不执行真实 MAA 业务。
- 不手改 OpenAPI 生成文件，不用硬编码 fetch/axios 绕过生成客户端。
- 不提交、推送、打包或切换分支。

## 完成判据

只有后端健康 ready、核心和新框架测试可独立收集、插件/MUMU/MAA 框架闭环通过、活动路径不依赖旧框架、OpenAPI 与生成客户端一致、所有活动页面通过真实 API 和桌面/窄屏/暗色/错误态检查，且前端 typecheck、test、lint、format、build 全部通过，才能宣布迁移完成。

当前结论：后端服务已恢复，核心迁移代码已在工作区，但后端准入尚未通过；前端仍是部分迁移状态。
