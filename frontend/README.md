# AUTO-MAS Frontend

基于 Vue 3 + TypeScript + Ant Design Vue + Electron 的桌面应用程序。

## 功能特性

- 🎨 使用 Ant Design Vue 组件库
- 🌙 支持深色模式（跟随系统/深色/浅色）
- 🎨 支持多种主题色切换
- 📱 响应式侧边栏布局
- 🔧 内置开发者工具
- ⚡ 基于 Vite 的快速开发体验

## 项目结构

```
frontend/
├── src/
│   ├── api/            # OpenAPI 生成的类型与客户端
│   ├── components/     # 跨模块组件，ui/ 为共享界面基础
│   ├── composables/    # 业务 API、请求和可复用能力
│   ├── views/          # 路由页面与模块内部组件、流程
│   │   ├── setting/    # 设置
│   │   ├── plan/       # 计划
│   │   ├── queue/      # 调度队列
│   │   ├── scheduler/  # 调度中心
│   │   ├── history/    # 历史记录
│   │   └── EditView/   # 专项编辑
│   ├── router/         # 路由装配与导航
│   ├── services/       # 共享服务，如 QueryClient
│   ├── stores/         # Pinia 客户端共享状态
│   ├── styles/         # 全局布局与共享表面样式
│   ├── types/          # 手写领域类型
│   ├── i18n/           # 词表与语言加载
│   └── main.ts         # 主渲染入口
├── electron/           # 主进程、preload、IPC 与桌面服务
├── e2e/                # 隔离启动器与用户流程
└── scripts/            # 开发和审计命令
```

## 开发入口

分支、提交和 PR 按[开发文档站](https://doc.auto-mas.top/developer/)执行。
工程规则以[前端规范](../.agents/skills/mas-frontend-standards/SKILL.md)和
[UI 规范](../.agents/skills/mas-frontend-ui/SKILL.md)为准；本文提供工作顺序和代码入口。

1. 写清用户操作、成功条件和受影响范围；交互改动列出加载、失败、禁用及保存后的表现。
2. 沿调用链找到已有实现，明确组件职责、状态所有者、HTTP/IPC 契约、保存时机和错误反馈归属。
3. 复用对应入口完成一个可运行的改动。组件局部草稿、Pinia 客户端共享状态和后端查询缓存分别管理；生成 API 通过生成器更新。
4. 按[测试规范](TESTING.md)复用能证明目标行为的检查，并完成下方静态检查。组件尺寸和候选审计见[AUDITING.md](AUDITING.md)。
5. 自查差异并提供验收证据；评审同时确认行为、职责和复用边界。UI 改动检查相关状态，样式改动检查应用的深浅主题。

开始前可按场景查找以下真实实现：

| 场景 | 参考入口 | 关注的职责 |
| --- | --- | --- |
| 普通设置字段保存 | [useSettingPersistence.ts](src/views/setting/useSettingPersistence.ts) | 字段补丁、指定字段回读、Electron 同步及保存结果 |
| 设置区域与控件 | [TabFunction.vue](src/views/setting/TabFunction.vue)、[UpdateSettingsSection.vue](src/views/setting/UpdateSettingsSection.vue) | 复用 SectionCard/SettingRow，组织业务选项和事件 |
| 独立桌面偏好区域 | [PressSoundSettings.vue](src/views/setting/components/PressSoundSettings.vue) | 直接复用既有 store，在区域内处理保存、导入和反馈，避免页面逐层转发 |
| 脚本通用运行限制 | [ScriptRunLimitsSection.vue](src/views/EditView/Script/components/ScriptRunLimitsSection.vue) | 组合四字段并发送保存字段键；父页读取自己的最新草稿，保留保存入口和专项提示 |
| 用户字段补丁构造 | [fieldPatch.ts](src/utils/fieldPatch.ts) | 从字段路径构造最小补丁；别名、序列化、队列和回读仍由调用方拥有 |
| 共享后端选项 | [useEmulatorOptions.ts](src/composables/useEmulatorOptions.ts) | 查询键、缓存、加载状态与失效；页面保留自己的选项显示 |
| 脚本字段即时保存 | [useScriptSaveMutation.ts](src/composables/useScriptSaveMutation.ts) | 按脚本串行、待执行同字段合并、保存后回读及聚合保存状态 |

设置的静态字段使用 [SettingChangeHandler](src/views/setting/settingTypes.ts)，组、字段和值从生成 API 类型派生；
通知描述表使用独立动态入口，并复用同一保存链路。选项由实际使用它们的区域维护，避免经过页面逐层转发。

保存入口按业务语义选择。备份恢复、用户编辑和其他显式提交流程沿用各自契约；
接入前核对初始化、并发、失败恢复及离开页面的行为，保留原有输入和反馈责任。

## 开发

### 安装依赖

```bash
yarn install
```

如果 Electron 二进制下载缓慢或失败，可以使用 npmmirror 镜像执行一次性安装：

```bash
yarn cross-env ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" yarn install
```

### 开发模式

源码 Electron 使用 Runtime 的 `development` 模式监督当前检出，安装版默认使用 `managed`。
启动模式不再由设置页保存，存量选择不再生效；开发排障仍可通过 `AUTO_MAS_RUNTIME_MODE` 显式覆盖。
安装与恢复中的测速和换源由 Runtime 自动完成，桌面端不再读取旧镜像配置或提供手动选源。
已初始化的安装版若丢失 Runtime，失败页的重试会先补装并完整准备环境，再继续启动后端。
旧的 `off` 值按构建默认值处理，不再直接启动 Python。应用环境仍独立判断，源码默认为开发环境。

在仓库根目录准备虚拟环境，再从 `frontend/` 启动。Runtime 开发模式不会创建或同步项目 `.venv`：

```powershell
uv sync --locked --group dev
Set-Location frontend
$env:AUTO_MAS_RUNTIME_EXE = 'D:/Github/AUTO-MAS-Runtime/bin/auto-mas-runtime.exe'
yarn dev
```

Runtime 可使用官方发行版，或按 [本地构建说明](../scripts/README.md) 构建。首次启动会准备 Runtime
自身所需的 uv；Runtime 的状态目录位于开发版 userData 下，源码和配置仍使用当前检出。
`yarn dev` 使用 Rolldown 转译 Electron，随后并行启动 Electron 与 Vite；页面会等本次 Vite
就绪后再加载。Electron 类型检查在后台持续运行，不阻塞启动，也不输出编译产物。
修改主进程后会重新编译，需重启 Electron 才会执行新代码；renderer 继续使用 Vite HMR。
`yarn dev:fullstack` 与 `yarn dev` 使用同一入口，不会再额外启动一个独立后端。
开发时可用 `AUTO_MAS_HTTP_PORT` 指定 1024–65535 范围内的端口，Electron 会将它传给 Runtime。
低端口调试继续使用独立后端与 `yarn web`。
Electron 退出会经 Runtime 关闭后端及其进程树；缺少 Runtime 时显示启动失败，不回退旧链路。

独立后端与浏览器调试继续保留，不需要 Runtime。在两个终端分别运行：

```powershell
# 终端一，frontend/ 目录；独立后端默认使用开发环境与 36164 端口。
yarn backend

# 终端二，frontend/ 目录。
yarn web
```

`yarn backend` 固定使用 36164。需要 80 等低端口时，不使用该快捷命令，在两个终端分别执行：

```powershell
# 终端一：仓库根目录，直接启动独立后端。
$env:AUTO_MAS_HTTP_PORT = '80'
uv run --locked python main.py

# 终端二：frontend/ 目录，让浏览器开发服务器连接同一端口。
$env:AUTO_MAS_HTTP_PORT = '80'
yarn web
```

此方式在浏览器里调试共用的 Vue 页面与 HTTP/WebSocket，不启动 Electron，也不验证 preload、
原生窗口或 Runtime 监督；这些能力继续使用 1024–65535 端口的 `yarn dev` 验证。

浏览器只连接独立后端，关闭预览不会停止它；后端由开发者在终端中管理。
独立验证生产行为时需显式设置 `AUTO_MAS_ENV=production`。

需要单独调试桌面前端时，在两个终端分别运行：

```powershell
# 终端一，frontend/ 目录。
yarn backend

# 终端二，frontend/ 目录，只启动 Electron、Vite 与主进程持续编译。
yarn dev:frontend
```

已有 Vite 服务时可用 `yarn electron-dev:frontend` 只启动 Electron。
该入口显式传入 `--connect-existing-backend`，默认连接 36164，可通过
`AUTO_MAS_HTTP_PORT` 指定端口。它不需要 Runtime，不安装、更新或重启后端；退出只断开连接，
保留后端及其任务，断线和系统唤醒后只重连。普通 `yarn dev` 仍负责后端的启动与退出。

### 构建

```bash
yarn build
```

## 技术栈

- **前端框架**: Vue 3 + TypeScript
- **UI 组件库**: Ant Design Vue 4.x
- **图标**: @ant-design/icons-vue
- **路由**: Vue Router 4
- **前端工具链**: Vite+（Vite、Vitest、Oxlint、Oxfmt）
- **桌面端**: Electron
- **包管理**: Yarn

检查命令均在 `frontend/` 执行；格式化修复只针对本次改动文件，检查使用全量入口。

```bash
yarn lint          # Oxlint 代码检查
yarn typecheck     # Vue renderer 类型检查
yarn format:check  # Oxfmt 格式检查
yarn audit:i18n    # 词表审计
yarn test          # Vitest 单元测试；也可按受影响文件选择
```

修改 Electron main/preload 时另执行 `node node_modules/typescript/bin/tsc -p tsconfig.electron.json --noEmit`。
浏览器 E2E、真实运行和证据范围按 [TESTING.md](TESTING.md) 选择；构建、类型、行为与视觉验证各自覆盖不同问题。
