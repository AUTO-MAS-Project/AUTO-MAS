# 插件开发、联调与交付

主程序仓库只维护宿主和核心 SDK（`plugins/auto_mas_core`）；所有适配器插件在独立仓库开发，通过插件中心安装。

## 目录结构

```text
AUTO-MAS/
├── app/
├── frontend/src/views/
│   ├── maa/               # 待迁出的历史静态页
│   └── whimbox/           # 待迁出的历史静态页
└── plugins/
    ├── auto_mas_core/     # 主仓跟踪的 SDK
    └── src_adapter/       # 本地克隆的独立插件仓（.gitignore 忽略，联调基准）
```

Runtime 运行时，用户插件装在安装根目录的 `plugins/`（源码插件优先覆盖同 ID 发行包），SDK 随 `repo/plugins/auto_mas_core/` 更新。

## 插件界面：三层积木模型

托管、账号、计划及后续所有插件界面，统一由后端按 `blocks` 编排，前端由通用壳（`ConfigEditor` / `ConfigBlockList`）渲染：

1. **`mascore` 预设块（`HostBlock`）**：宿主现成的完整业务块（如 `game_binding`、`config_restore`、`native_session`、`webhooks`），插件只声明块名，零前端代码。
2. **MAS 可组合组件（`DeclarativeBlock`）**：在 Python `ConfigModel` 上用 `ui()` / `select()` / `table()` 组合宿主原子控件（开关、步进器、下拉/有序多选、路径选择、表格等），零前端代码。
3. **完全下游自定义（`PluginBlock`）**：声明式表达不了的局部复杂卡片，由插件随 wheel 交付前端产物并通过 `MountedFrontend` 挂载（参考 `src_adapter` 的 `stage.html`），必须提供 `fallbackGroups` 兜底；页头、配置锁、保存和离页守卫归宿主。

原则：
- 按 **L1 `HostBlock` → L2 `DeclarativeBlock` → L3 `PluginBlock`** 递进选型。
- 新增或外迁插件**不再**往主仓添加静态 `entry.ts` 或整页手写 Vue（SRC 已移出；MAA / 奇想盒 / BetterGI 随外迁逐步清理）。
- 插件文案统一放在插件包 `i18n/{zh-CN,en-US,ja-JP}.json`，由宿主 `I18nManager` 解析。
- 插件自有 HTTP 端点（如 `/api/plugin/signflow/*`）按启用状态动态挂载，不要用 `yarn openapi` 同步，在 `frontend/src/services/` 写薄封装即可。

## 本地联调

1. 克隆插件仓到 `plugins/<插件目录>`（例如 `AUTO-MAS-Project/AUTO-MAS-SRC-Adapter` → `plugins/src_adapter`），启动后在插件中心启用。
2. 未发布的共用库也可放在 `plugins/<库目录>`（`pyproject.toml` 的 `keywords` 写 `auto-mas-library`），启动时自动优先导入；需先卸载共享环境里的同名发行包，改库代码后重启后端。

## 测试与防漂移门禁

### 1. 主仓回归（锁定已发布 wheel）

```powershell
uv sync --locked --group dev
uv run --no-sync python scripts/prepare_test_plugins.py
uv run --no-sync python -m pytest tests -q

Set-Location frontend
yarn test
yarn audit:i18n --check
yarn e2e --grep '@plugins'
```

### 2. 真实下游联调（以 `src_adapter` 为基准）

修改主仓插件协议、三层积木、声明式表单或 `plugins/auto_mas_core/` 时，**必须用本地 `plugins/src_adapter` 跑通联调**，不能只跑主仓 mock 测试：

```powershell
# 1) 以当前主仓作为宿主，跑真实下游 SRC 测试
$env:AUTO_MAS_HOST_SOURCE = (Get-Location).Path
$env:PYTHONPATH = "$((Get-Location).Path);$((Get-Location).Path)\plugins\src_adapter\src"
uv run --no-sync python -m pytest plugins/src_adapter/tests/ -v

# 2) 跑主仓插件挂载与声明式 UI 回归
uv run --no-sync python -m pytest tests/api/test_generic_declarative_editors.py tests/api/test_plugin_frontend_mount.py -q
yarn --cwd frontend test src/components/declarative/ src/views/plugins/ConfigEditor.test.ts src/components/PluginUiMount.test.ts
```

验证记录里附上主仓与 `src_adapter` 的 commit SHA。

## 发布

1. 插件仓发 PyPI（`CHANGELOG.md` 用 `## [版本] - 日期`，`pyproject.toml` 配好 `Changelog` 公开链接），市场索引自动同步。
2. 如需发主仓前端测试包：`gh workflow run ci-package.yml --repo AUTO-MAS-Project/AUTO-MAS --ref dev -f alpha=true`。
3. 完整发版步骤见[插件发布指南](https://doc.auto-mas.top/plugin/start/publish.html)。
