# GitHub 协作上传方案：传什么 / 怎么传 / 开什么分支

> 2026-07-26。基于只读预检（remote 拓扑、脏文件构成、.gitignore、敏感扫描、体积、CI 基建）。
> 本文是方案，未执行任何 commit/push；执行需明确确认。

---

## 〇、预检结论（决定方案形态的四个事实）

1. **远端拓扑**：`origin` = `github.com/qiyinxi/AUTO-MAS-with-M9A`（个人 fork），
   `upstream` = `github.com/AUTO-MAS-Project/AUTO-MAS`。
2. **基线已在库上**：A 测包工作树（D:\AM6R）的基线 aceb651a 正是
   `origin/integration/dev-v2-dev-all-plugins` 的 tip，且与远端完全同步。
   dev_v2 本地领先的 32 个 commit 全部是 aceb651a 的祖先——**已经在服务器上**
   （经 integration 分支可达），推 dev_v2 只是快进指针，零风险。
3. **真正没上库的 = 工作树脏改动**：571 条（264 修改 / 20 删除 / 364 未跟踪文件），
   即本批全部 UI 收口、Config v2 收口、测试与文档。
4. **无敏感泄露**：将入库文件扫描零真实凭据（config/ 已忽略）；唯一体积雷区是
   `plugins/wheels/` 的 127 个 .whl（147MB，被 .gitignore 负向规则有意纳入但
   尚未跟踪）。

---

## 一、传什么

| 内容 | 传不传 | 说明 |
|---|---|---|
| 工作树全部源码改动（frontend 168M+20D、app 51M、tests、scripts、res） | ✅ | 本批成果主体 |
| 未跟踪源码/测试/文档（约 237 个文件，除 wheels 外最大 188KB） | ✅ | app-shell 壳层、新组件、契约测试、两份新文档 |
| `docs/config-v2-refactor-status.md`、`docs/design/config-plugin-redesign.md`、`docs/github-collab-plan.md`（本文） | ✅ | 协作者入门必读，防重复造轮子 |
| `res/version.json`（改为 v6.0.0-alpha.NEXUS-OVERDRIVE.20260726.11） | ✅ | 随 alpha 分支走；发布前另行核对 |
| `plugins/wheels/*.whl`（127 个，147MB 二进制） | ❌ **不传** | 进 git 历史即永久膨胀；设计文档 P 系列已计划移除 wheelhouse 锁定链。发行需要时改走 GitHub Release 资产。已跟踪的 manifest/lock 4 个小文件照常提交 |
| `config_framework_v2` 归档源码 | ❌ 不进主仓 | 项目内 `app/configuration/v2/` 才是权威实现，双份必漂移 |
| 「配置基类.md」设计文档（修复 mojibake 文件名后） | ✅ | 放 `docs/design/reference/配置基类.md`，供协作者读框架语义 |
| `.claude/`、交接 zip、截图、`_handoff_*` 快照目录 | ❌ | 本就在仓外或已忽略 |

## 二、怎么传（执行序，共 6 步）

```bash
# 0) 家务：清 worktree 悬挂引用（预检发现 1 条 garbage）
git worktree prune && git gc --auto

# 1) 在 D:\AM6R 从 aceb651a 建收口分支
git switch -c alpha/v6-ui-config-20260726

# 2) 分批提交（不要一锅 -A；wheels 用 pathspec 排除）
#    建议 5 个逻辑 commit：
git add frontend/ && git commit -m "feat(ui): mac 壳层收口批——侧栏/主页/向导/设置三档瀑布/调度台/标题统一"
git add app/ tests/ scripts/ && git commit -m "refactor(config): Config v2 authoritative 收口与测试"
git add docs/ && git commit -m "docs: Config v2 现状报告 + 配置/插件重设计文档 + 协作方案"
git add res/ interface.json PROGRESS.md && git commit -m "chore: alpha 版本标记与进度"
git add -A ':!plugins/wheels/*.whl' && git commit -m "chore: 其余收口（旧 API model 清理等）"

# 3) 推收口分支
git push -u origin alpha/v6-ui-config-20260726

# 4) 开 PR：alpha/v6-ui-config-20260726 → integration/dev-v2-dev-all-plugins
#    （基线即其 tip，PR diff 恰好 = 本批全部改动，评审面干净）

# 5) 快进 dev_v2（32 个 commit 已在服务器可达，纯指针推进）
git push origin dev_v2

# 6) （稳定后）integration → upstream/dev_v2 开跨仓 PR
```

注意：真实机回归（WS v2/Config v2 GUI 六项）尚未回传，第 4 步 PR 描述里
标注 "alpha，未过真实机回归，禁止合入即发布"。

## 三、开什么分支（协作分支模型）

```
upstream/dev_v2            ← 稳定后大 PR（阶段性）
└── origin/dev_v2          ← fork 主线，只快进，不直接开发
    └── integration/dev-v2-dev-all-plugins   ← v6 alpha 集成线（现基线）
        ├── alpha/v6-ui-config-20260726      ← 本批收口（第一个 PR）
        ├── feat/ui-hints-introspect         ← 设计文档 P1
        ├── feat/history-store               ← P2
        ├── refactor/plugin-runtime          ← P3（core 插件+新加载器）
        ├── feat/plugin-adapters             ← P4（四拓展基类+存量插件迁移）
        ├── feat/game-manager-host           ← P5
        └── feat/home-tools-pluginization    ← P6
```

规则建议：
- 一律 PR 进 integration，禁 direct push；integration 与 dev_v2 开分支保护
  （require PR + CI 绿 + 1 review）；
- 分支名对齐设计文档分期，一期一分支一 PR，互相并行（P1/P2 无依赖可先行）；
- CI 门禁即现有 workflows（AM6R 侧比 dev_v2 多 build-experimental-alpha 与
  发布加固脚本，随本批一并入库后对全体协作者生效）+ 建议新增 PR 必跑：
  前端 `vue-tsc / eslint / prettier --check / vitest run`、后端 `pytest -q`；
- 补齐协作基建（预检确认缺失）：`.github/PULL_REQUEST_TEMPLATE.md`、
  `ISSUE_TEMPLATE/`、`CODEOWNERS`（frontend / app/configuration /
  app/plugin_runtime / docs 各设 owner）。

## 四、风险与遗留

1. wheels 例外规则（`!/plugins/wheels/`）保留在 .gitignore 里，协作者一旦
   `git add -A` 仍会把 147MB 二进制打进历史——建议在第一个 PR 里顺手把负向
   规则删掉或改为仅 manifest/lock 白名单（与设计文档 P 期"移除 wheelhouse
   锁定链"一致）。
2. 主仓 pack 已 1.69GiB：历史包袱与本次无关，但提醒后续不要再进大二进制。
3. `feat/browser-capability` worktree 落后 upstream/dev_v2 39 个 commit，
   协作开始前建议 rebase 或声明冻结。
4. 13 个 `legacy/auto-mas/*` 本地分支无需上传。
