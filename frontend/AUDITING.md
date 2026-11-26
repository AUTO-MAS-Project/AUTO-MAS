# 前端本地治理工具

在 `frontend/` 下使用项目 Yarn 4 运行（先执行 `yarn install --immutable`）。下列命令用于本地定位冗余与重复代码候选，**不是 CI 门槛，也不会自动删除文件**。

```powershell
New-Item -ItemType Directory -Force ../.dev/frontend-governance

yarn audit:baseline
yarn audit:baseline <基线提交>
yarn audit:unused
yarn audit:unused --reporter json > ../.dev/frontend-governance/knip.json
yarn audit:duplicates
```

原始报告保存在 Git 忽略的 `.dev/frontend-governance/` 中，不提交入库。

## 1. 基线统计（`audit:baseline`）

- 统计 Git 跟踪及未忽略的新增 `.ts` / `.vue` / `.css` 文件物理行（排除 `.test.*` / `.spec.*` 与构建产物）。
- 渲染层、生成 API、词表、Electron 分开计数；对比治理收益时只比较同组手写代码。

## 2. 未使用代码扫描（Knip）

- 配置文件 `knip.json` 已声明主应用/桌宠/桌宠菜单入口、Electron 主进程与 preload、构建脚本、测试与 `*.typecheck.ts` 契约入口；生成 API 参与引用解析但不报未使用导出。
- 发现候选时 Knip 返回退出码 `1` 属正常报告行为。清理前须逐条核对动态入口、扩展公开出口（如 MaaFW `pageKit`）、打包器隐式加载与类型契约入口；`pwsh` / `tasklist` 为系统命令，非缺失依赖。

## 3. 重复片段扫描（jscpd）

- 配置文件 `.jscpd.json` 以 `mild` 模式扫描手写 `src/` 与 `electron/`（阈值 ≥ 5 行且 ≥ 70 token），排除生成 API、词表、声明与单测。
- Vue SFC 的 script / template / style 分别统计，不可直接将各格式行数相加当作文件总行数；结合业务边界判断是否抽离复用，避免为相似 UI 强行耦合。

参考：[Knip 配置文档](https://knip.dev/guides/configuring-project-files) · [jscpd 文档](https://github.com/kucherenko/jscpd)

## 治理后验证

常规前端静态检查（`yarn lint`、`yarn typecheck`、`yarn format:check`、`audit:i18n` 与 Vue 行数基线）可在仓库根目录统一运行 `uv run --no-sync python scripts/pr_check.py`；行为测试按需在 `frontend/` 运行 `yarn test` 与相关 `yarn e2e`，一次性探针规则同 [TESTING.md](TESTING.md)。
