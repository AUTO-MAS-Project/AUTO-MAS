# AUTO-MAS Frontend

基于 Vue 3 + TypeScript + Ant Design Vue + Electron 的桌面端应用。

## 技术栈

- **框架**：Vue 3 + TypeScript + Vue Router 4
- **UI 组件**：Ant Design Vue 4.x、`@ant-design/icons-vue`
- **工具链**：Vite+（Vite、Vitest、Oxlint、Oxfmt）、Yarn 4
- **桌面端**：Electron

## 目录结构

```text
src/
├── api/            # OpenAPI 自动生成的后端客户端（勿手改）
├── components/     # 公共组件与开发工作台
├── composables/    # 组合式函数（主题、API、任务运行态等）
├── i18n/           # 启动期词表与国际化封装
├── plugins/        # 静态脚本插件入口注册
├── router/         # 路由配置
├── services/       # WebSocket、快照与前端服务
├── styles/         # 全局样式与外观变量
├── views/          # 业务页面（home / scripts / plan / queue / scheduler / history / setting / taskboard / games / gamesign / plugins 等）
└── main.ts         # 渲染进程入口
```

## 安装依赖

```powershell
yarn install
```

如果 Electron 二进制下载缓慢或失败，可使用 npmmirror 镜像安装：

```powershell
yarn cross-env ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/" yarn install
```

## 开发调试

按需要选择以下三种方式之一。所有方式默认均以**开发环境**运行；需要验证生产行为时，显式设置 `AUTO_MAS_ENV=production`。

### 1. 完整桌面端（Electron + Runtime，推荐）

源码 Electron 默认通过 Runtime 的 `development` 模式监督当前检出（安装版默认使用 `managed` 模式，开发排障可用 `AUTO_MAS_RUNTIME_MODE` 覆盖）。Runtime 不会自动创建或同步 `.venv`，需先在仓库根目录准备 Python 环境：

```powershell
# 仓库根目录
uv sync --locked --group dev

# 进入 frontend/ 启动桌面端
Set-Location frontend
$env:AUTO_MAS_RUNTIME_EXE = '<path/to/auto-mas-runtime.exe>'
yarn dev
```

- Runtime 可使用官方发行版，或按 [本地打包说明](../scripts/README.md) 本地构建；缺失 Runtime 时会显示启动失败。
- `yarn dev`（与 `yarn dev:fullstack` 相同）使用 Rolldown 编译主进程并并行启动 Vite 与 Electron，后台持续运行 Electron 类型检查。
- 渲染层支持 Vite HMR；修改 Electron 主进程代码后需重启 Electron 生效。
- 默认通过 `AUTO_MAS_HTTP_PORT` 指定端口（1024–65535）；退出 Electron 时会经 Runtime 一并关闭后端进程树。

### 2. 独立后端 + 浏览器预览（无需 Runtime）

适合快速调试共享的 Vue 页面与 HTTP/WebSocket 交互（不启动 Electron，不覆盖 preload、原生窗口或 Runtime 监督）：

```powershell
# 终端一（frontend/ 目录）：启动独立后端，默认端口 36164
yarn backend

# 终端二（frontend/ 目录）：启动浏览器预览
yarn web
```

如需使用 80 等低端口，在两个终端手动指定端口启动：

```powershell
# 终端一（仓库根目录）
$env:AUTO_MAS_HTTP_PORT = '80'
uv run --locked python main.py

# 终端二（frontend/ 目录）
$env:AUTO_MAS_HTTP_PORT = '80'
yarn web
```

关闭浏览器标签页不会停止独立后端，由终端自行管理。

### 3. 独立后端 + 桌面端（仅调试前端）

希望前端重启不影响正在运行的后端时，在两个终端分别运行：

```powershell
# 终端一（frontend/ 目录）
yarn backend

# 终端二（frontend/ 目录）：只启动 Electron、Vite 与主进程编译
yarn dev:frontend
```

若 Vite 已启动，可用 `yarn electron-dev:frontend` 单独拉起 Electron。该入口传入 `--connect-existing-backend`（默认连接 36164，可用 `AUTO_MAS_HTTP_PORT` 覆盖），退出时只断开连接，保留后端及其运行中的任务。

## 常用命令

```powershell
yarn build         # 构建桌面端产物
yarn lint          # Oxlint 静态检查
yarn lint:fix      # 自动修复 lint 问题
yarn format        # Oxfmt 格式化
yarn typecheck     # Vue 渲染层类型检查
yarn test          # 运行 Vitest 单元测试
```
