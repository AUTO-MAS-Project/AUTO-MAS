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
src/
├── components/          # 组件
│   └── AppLayout.vue   # 主布局组件
├── views/              # 页面
│   ├── Home.vue        # 主页
│   ├── Scripts.vue     # 脚本管理
│   ├── Plans.vue       # 计划管理
│   ├── Queue.vue       # 调度队列
│   ├── Scheduler.vue   # 调度中心
│   ├── History.vue     # 历史记录
│   └── Settings.vue    # 设置页面
├── router/             # 路由配置
├── composables/        # 组合式函数
│   └── useTheme.ts     # 主题管理
└── main.ts            # 应用入口
```

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

Vite+ 检查与测试命令

```bash
yarn lint          # 查看问题
yarn lint:fix      # 自动修复
yarn format        # Oxfmt 全量格式化（非必须）
yarn typecheck     # 检查 Vue renderer 类型
yarn test          # 运行 Vitest 测试
```
