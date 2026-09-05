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

直接打开electron窗口

```bash
yarn dev
```

### 构建

```bash
yarn build
```

## 技术栈

- **前端框架**: Vue 3 + TypeScript
- **UI 组件库**: Ant Design Vue 4.x
- **图标**: @ant-design/icons-vue
- **路由**: Vue Router 4
- **构建工具**: Vite
- **桌面端**: Electron
- **包管理**: Yarn

oxlint + oxfmt 代码规范相关

```bash
yarn lint          # 查看问题
yarn lint:fix      # 自动修复
yarn format        # 仅 oxfmt 全量改格式（非必须）
yarn typecheck     # 检查 Vue renderer 类型
```
