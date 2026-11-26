# 插件开发、联调与交付

本文说明 AUTO-MAS 插件的目录边界、本地联调、回归环境与市场发布流程。

## 目录归属

主程序仓库只跟踪核心 SDK（`plugins/auto_mas_core`）；其余适配器插件在独立仓库维护，发行包通过插件中心安装。

**源码开发环境**：

```text
AUTO-MAS/
├── app/
├── frontend/src/views/
│   ├── maa/               # 暂时保留的 MAA 静态页面
│   ├── whimbox/           # 暂时保留的奇想盒静态页面
│   └── src/               # SRC 静态编辑页
└── plugins/
    ├── auto_mas_core/     # 主程序跟踪的 SDK
    ├── maa_adapter/       # 开发者克隆的独立仓库（主仓 .gitignore 忽略）
    ├── whimbox_adapter/   # 奇想盒独立仓库
    └── src_adapter/       # SRC 独立仓库
```

**Runtime 安装目录**：

```text
安装根目录/
├── plugins/
│   ├── <source_plugin>/   # 用户自行放入的源码插件
│   └── pypi/site-packages/# 插件中心安装的发行包与依赖
└── repo/
    ├── app/
    └── plugins/auto_mas_core/  # 随当前后端同步的 SDK
```

Runtime 更新与源码切换会保留安装根目录的 `plugins/`，而 SDK 随 `repo/` 更新。

## 本地开发与联调

在主程序根目录克隆对应插件仓库到 `plugins/` 下：

```powershell
git clone https://github.com/AUTO-MAS-Project/AUTO-MAS-MAA-Adapter.git plugins/maa_adapter
```

其他常用适配器仓库：
- 奇想盒：`AUTO-MAS-Project/AUTO-MAS-Whimbox-Adapter` → `plugins/whimbox_adapter`
- BetterGI：[AUTO-MAS-BetterGI-Adapter](https://github.com/AUTO-MAS-Project/AUTO-MAS-BetterGI-Adapter) → `plugins/bettergi_adapter`
- SRC：[AUTO-MAS-SRC-Adapter](https://github.com/AUTO-MAS-Project/AUTO-MAS-SRC-Adapter) → `plugins/src_adapter`

开发约定：
- 启动主程序后在插件中心手动启用源码插件；插件的提交、发版均在各自独立仓库完成。
- **源码覆盖语义**：本地源码会覆盖同 ID 的已安装发行包。验证市场安装时，先停掉后端并将源码目录移出 `plugins/`，再从插件中心安装。
- **旧配置自动补装**：已有托管的配置升级需要对应插件时，主程序会在激活领域配置前自动通过发行包入口补装（有效的本地源码覆盖仍优先）。
- **版本约束**：正式发布前按实际配套 SDK 发行版本收紧最低版本约束并用该 SDK 验证。

### 本地库

插件依赖的共用库尚未发布时，把库的源码工程同样放进 `plugins/<目录>`（`src/` 下恰好一个普通包，`pyproject.toml` 的 `keywords` 写 `auto-mas-library`、不写 `auto-mas-plugin`）。主程序把它当作本地库，不进插件中心、不进注册表：
- **依赖求解**：库目录作为求解目标，插件对该包名（带版本范围也行）的依赖由它满足；库自己的包不装进共享环境，它声明的第三方依赖照常安装。改库的 `pyproject.toml` 会触发重新求解。
- **导入优先级**：启动时把库的 `src` 放到导入路径最前，优先于共享环境里的同名发行包。改库代码要重启后端，库不支持热重载。
- **联调**：先卸掉共享环境里的同名发行包，否则 `importlib.metadata` 读到的仍是发行包的版本。

专项新增或迁移日志节点时，按 [LogFlow 接入与迁移](../.agents/skills/mas-script-specialized-adapter/references/logflow-api.md) 声明采集规则、绑定实际运行并验收节点和报告。

## 前端静态页面归属

在动态前端加载上线前，MAA、奇想盒、SRC、BetterGI 的编辑页面暂由主程序 `frontend/src/views/` 维护并随桌面端构建（通过各目录的 `entry.ts` 注册，无计划表的专项可省略 `plan`）。新建托管与路由入口按后端实际启用的插件能力动态开放；后端实现、专用接口与配置模型由各自插件仓库持有。

`frontend/src/views/gamesign/` 这类由插件能力承载的普通功能页同样留在主程序，但走普通路由（不经 `entry.ts`），页面只调 `frontend/src/services/` 下的薄封装。

插件自有的 HTTP 端点（如 `/api/plugin/signflow/*`）由宿主在启停时挂到 `app.routes`，因此只有生成那一刻已启用的插件才会进 `frontend/src/api`。整仓重跑 `yarn openapi` 会把未启用插件的契约模型当作过期文件清掉，**不要用它来同步插件端点**；这类端点改在主程序 `frontend/src/services/` 里手写薄封装，视图与组合式函数只调该模块。

## 回归与测试环境

主仓专项集成测试消费 `tests/requirements-plugins.txt` 中锁定版本与 SHA-256 的已发布 wheel（安装到 `.test-plugins/`，SDK 使用当前主仓源码）：

```powershell
uv sync --locked --group dev
uv run --no-sync python scripts/prepare_test_plugins.py
uv run --no-sync python -m pytest tests -q

Set-Location frontend
yarn test
yarn audit:i18n --check
yarn e2e:check
yarn e2e --grep '@plugins'
```

升级集成测试依赖的插件包时，须同步更新版本号与 PyPI wheel 的 SHA-256 摘要。插件自身的单元测试在各自独立仓库内运行。

## 生成 dev alpha 测试包

代码合入 `dev` 后，可手动触发打包工作流生成跟随 `dev` 的前端测试包（产物位于 Actions 运行附件，包内 `build-source.json` 记录版本、提交与 Runtime 摘要）：

```powershell
gh workflow run ci-package.yml --repo AUTO-MAS-Project/AUTO-MAS --ref dev -f alpha=true
```

## 发布与市场更新日志

1. 在插件仓库完成构建、元数据校验与 PyPI 发布（例如 `auto-mas-maa-adapter`），目录维护工作流会自动同步至插件市场。
2. **展示更新日志**：在插件仓库的 `CHANGELOG.md` 中使用 `## [版本] - 日期` 记录面向用户的改动，并在 `pyproject.toml` 的 `[project.urls]` 中配置指向该文件的公开 HTTPS `Changelog` 链接。
3. **发布验收**：等待索引工作流完成后，下载[公开插件目录](https://data.auto-mas.top/api/v1/files/auto-mas/Client/plugins/download)按 `package_name` 核对 `version` 与 `changelog`（收录最近五版）；随后在客户端刷新插件市场，检查「更新」与「已安装」详情展示。直接从 PyPI 或镜像刷新时日志为空。

PyPI Trusted Publishing 与完整发版步骤见[插件发布指南](https://doc.auto-mas.top/plugin/start/publish.html)及 [MAA 插件发布说明](https://github.com/AUTO-MAS-Project/AUTO-MAS-MAA-Adapter/blob/master/docs/PUBLISHING.md)。
