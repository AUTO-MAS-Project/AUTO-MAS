# 前端本地治理工具

从 `frontend/` 使用项目 Yarn 4 执行，先 `yarn install --immutable`。工具版本由
`package.json` 和 `yarn.lock` 固定。报告用于定位候选，不是 CI 门槛，不自动删除文件。

```powershell
yarn audit:baseline
yarn audit:baseline <基线提交>
yarn audit:i18n
yarn audit:i18n --check
```

重定向报告前创建本地目录：`New-Item -ItemType Directory -Force ../.dev/frontend-governance`。
原始报告保存在 Git 忽略的 `.dev/frontend-governance/`，不提交。

## 统计口径

`audit:baseline` 统计 Git 跟踪的文件与未忽略的新文件；传提交时只统计该提交的树。
按物理行（含空行）统计 `.ts`、`.vue`、`.css`，排除 `.test.*` / `.spec.*`。
渲染层、生成 API、词表、Electron 分开计算，构建产物不计入。
比较业务实现时只看相同组，不把锁文件、生成物或文件搬迁算成代码治理收益。

## 词表审计

`audit:i18n --check` 拒绝缺译、占位符差异、源码引用不存在的词条和用户界面硬编码中文。
死词条和疑似动态引用只输出报告，不作为失败条件。

未使用符号、重复文本和 Markdown 写法不再设独立扫描入口。

## 验证

前端检查使用当前 `package.json`：`yarn lint`、`yarn typecheck`、`yarn format:check`。
行为测试按影响面选择，本机需要限并发时用 `yarn test --maxWorkers=4`。
浏览器验证先运行 `yarn e2e:check`，再通过 `yarn e2e --grep '<标签>'` 启动隔离环境。
独立检出默认按开发环境运行，无需 `.env`；验证生产行为须显式设置 `AUTO_MAS_ENV=production` 并隔离用户数据与遥测。
一次性回归探针遵守 [TESTING.md](TESTING.md)，留在本地，不扩充长期测试集。
