# 更新日志碎片指南

每个用户可见的 PR 在本目录下放**一个**碎片文件，用一句话概括给用户看的变化。每天北京时间 23:30，工作流自动把已合并碎片编译进 `CHANGELOG.md` 顶部的「未发布」段并删除碎片。平时**不要手改** `CHANGELOG.md`、`res/version.json` 或任何版本号。

## 快速创建

```powershell
python scripts/changelog.py add fix maa "修复理智不足时剿灭被误记为本周已完成的问题"
# 生成 changelog.d/<分支名>.fix.md，内容：
#   project: maa
#   修复理智不足时剿灭被误记为本周已完成的问题
```

也可手动新建 `<PR 号或分支名>.<分类>.md`：
- **首行** `project: <项目键>`（必填；仅 `dev` 分类可省略，命令行写 `-`）。
- **正文**一行、**不超过 50 字**，不加 `- ` 前缀，不写项目名、PR 号与署名（入账时自动补全为 `【项目】做了什么 (#PR) by @作者`）。
- **可选头部**：
  - `author: 甲, 乙`：多人合作或代提 PR 时覆盖默认署名（脚本不读 `Co-authored-by`）。
  - `highlight: true`：由维护者标出，入账时归入「本次亮点」。
  - `beta-only: true`：仅进公测公告，转正汇总时自动丢弃。
- **勿改动他人碎片**：重命名或改写会转移归属（仅加减 `highlight:` / `beta-only:` 允许）。

## 分类后缀与项目键

| 后缀 | 分类 | 说明 |
| --- | --- | --- |
| `breaking` | 破坏性变更 | 需用户确认或改变既有行为 |
| `feat` | 新增 | 新功能 |
| `change` | 变更 | 现有功能调整与优化（拿不准时优先用 `change` 而非 `fix`） |
| `remove` | 移除 | 已移除或即将移除 |
| `fix` | 修复 | Bug 修复 |
| `security` | 安全 | 安全性改进 |
| `dev` | 开发流程 | 仅影响贡献者，不进公告 |

项目键（定义于 `scripts/changelog.py` 的 `PROJECTS`，公告按表序排列）：

| 键 | 公告显示 | 键 | 公告显示 |
| --- | --- | --- | --- |
| `maa` | MAA | `mfw` | MFW |
| `end` | end（MaaEnd） | `general` | 通用脚本 |
| `m9a` | M9A | `home` | 主页 |
| `hsr` | HSR | `scheduler` | 调度 |
| `bgi` | bgi（BetterGI） | `emulator` | 模拟器 |
| `zzz` | 绝区零一条龙 | `notify` | 通知 |
| `okww` | ok-ww | `tools` | 工具 |
| `oknte` | ok-nte | `settings` | 设置 |
| `baah` | BAAH | `update` | 更新 |
| `whimbox` | 奇想盒（Whimbox） | `runtime` | Runtime |
| `mss` | MSS | | |
| `src` | SRC | | |

无兜底键，归类不清时就近归属：
- 界面语言 / 文案、帮助入口 → `settings`
- 虚拟显示器、游戏社区（签到 / 活动）、日志页 / 打包日志 → `tools`
- 调度中心、队列、计划、跨全部专项的配置来源/恢复 → `scheduler`（单专项归对应专项）
- 启动界面、初始化、依赖安装 → `runtime`

## 写作要求

- **面向用户、写症状不写根因**：只写用户可观察的变化或现象，去掉类型名、接口路径、状态码等实现细节；一条 PR 只合并为一句话。
- **本周期新增功能的后续修补仅公测**：上一个正式版公告里没有的新功能，其后续所有修复、调整与补充修改均按仅公测处理——同一 beta 内不写碎片（PR 打 `skip-changelog`），跨 beta 标 `beta-only: true`。上一个正式版已有的功能正常写碎片。
- 纯文档、CI、测试或用户不可见的重构不写碎片，给 PR 打 `skip-changelog` 标签。

## CI 检查与自动标签

- **必填检查**：改动 `app/`、`frontend/src/`、`frontend/electron/` 或 `main.py` 的 PR 必须恰好新增一个有效碎片（或带 `skip-changelog`）；禁止普通 PR 修改 `CHANGELOG.md`、`res/version.json` 及各处版本号（维护者整理历史时用 `changelog-maintenance` 放行）。
- **自动标签**：PR 创建或更新时按碎片自动同步 `类型: ...` 与 `专项: ...` / `模块: ...` 标签，保留人工标签。

## 入账与发版流程

- **晚间入账**：每天 23:30 自动将 `dev` 与 `release/*` 上的碎片编译入 `## [未发布]` 并更新 `res/version.json`（也可手动触发）。
- **准备发版**：维护者运行「准备发版」选择 `beta` / `stable` / `patch`，编译剩余碎片、写入版本号并生成 `Release vX.Y.Z` PR；转正时合并同号全部 beta 段并丢弃 `（仅公测）` 条目。
- **首行 JSON 预算**：Release 正文首行 JSON 供客户端更新提示使用，上限 18,000 字符（Mirror 酱截断上限 20,000 字符），超限时从最老版本段或本段末尾熔断并在发版 PR 中预告；如需手工精简，改完 `CHANGELOG.md` 后执行 `python scripts/changelog.py sync` 同步。
