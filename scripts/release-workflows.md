# 每日入账、nightly 与独立发布线

## 实现与操作

- 北京时间每日凌晨 02:00（UTC 前一天 18:00），默认分支 main 上的 `nightly.yml` 调用
  `absorb-changelog.yml`，等待成功后才检出 dev 检查源码 SHA。
  Actions 定时可能延迟；顺序由 `needs` 保证。手动运行入账也只处理 dev，
  无碎片不提交；推送竞争最多从 dev 顶端重算三次。
- nightly SHA 与最后一次完整公开发布相同且 tag/附件完整时跳过。
  缺失 Release/tag、草稿、附件缺失或元数据不完整均重新构建。
  构建工作区注入 `vX.Y.Z-alpha.<github.run_number>`，Electron 使用去 v 的
  SemVer，Python/uv 使用 PEP 440，应用显示与构建元数据保留完整 v 版本。
  CHANGELOG.md 和远端 dev 版本文件不改。
- 完整安装包、便携包、源码/版本信息和删除前的 Release 状态先上传 Actions，
  保留 30 天。然后只删除重建 dev Release/tag，在草稿中上传全部附件和
  `nightly-build.json`，确认完整后公开为预发布、非 Latest。失败可从 Artifact
  下载包；下一次运行不会把失败当成成功，可手动重跑 nightly。
  nightly 不签名、不调用 CNB/Mirror 酱/自建源的产物发布。
- alpha 首装和更新从 dev 读 Runtime 钉扎，Runtime 始终按实际 Commit 检查滚动更新；
  dev 源码版本可跨开发周期，与 alpha 构建号无需相同。受管仓库绑定完整目标版本、
  源码版本和 SHA，启动/恢复继续严格校验身份。正式版和 beta 使用原 release 分支。
  普通客户端更新仍走 stable/beta 正常发布源；nightly 包在 GitHub 手动下载，
  不加入普通用户默认升级目标。后台更新提示继续显示真实目标提交信息。
- 旧版本后端热修：将兼容验证过的修复及一个碎片通过 cherry-pick PR 纳入旧
  `release/vX.Y.Z`。不入账、不提升版本、不合入 dev，不要求先入账才能热更。
  下一补丁从正式 tag 快照重放选定修复，不能依赖旧 release 的全部分支内容。

## 准备与正常发布

1. 在 main 或 dev 入口运行「准备发版」。开发线选择 beta/stable；正式补丁选择
   patch，填写 `base_version=v5.6.0` 和 `fix_commits=<sha1> <sha2>`。
   explicit 正式补丁也必须给基准与修复，只接受基准 Z+1。修复按依赖顺序填写；
   缺失修复、merge/root 提交、冲突或修改发布版本字段都会拒绝，绝不隐式合入 dev。
   若确实要把 dev 全量发布为补丁，须另行确认范围并修改方案，此入口不提供捷径。
2. 工作流先在本地组装独立 `codex/release-base-v目标`，从正式 tag 仅 cherry-pick
   所选修复（原修复即使已在旧 release 上也会纳入；已在基准中的等效补丁跳过）。
   补丁仅另外迁移 dev 当前的四个 CI 入口：入账、准备发版、构建发布和更新日志检查，
   防止旧 tag 的 push 入账与旧守门规则在新 release 上复活；工具由入口从 dev 读取。
   不带入 dev 业务代码、版本文件、更新日志或其他工作流，旧 release 的 CI 文件不改。
   原始修复碎片随提交保留并统一编译、署名和清理。依赖是否满足运行语义、是否兼容
   旧客户端仍由维护者审核和运行对应测试；自动 cherry-pick 成功不代表兼容证明。
3. 发版 PR 的 head 为 `codex/release-v目标`，base 为独立准备分支，只有 head
   写入版本/日志生成物。所有检查通过后才普通原子推送两个新分支并创建 PR。
   已有准备分支拒绝重置，维护者继续原 PR；PR 创建失败时可对保留分支手动续建。
4. 审核并合并 PR 后，从 **main 的最新构建工作流入口**选择该准备分支。
   构建守门按发布线和全仓库 tag 拒绝重号/倒退；正式补丁不受下一周期 beta 阻挡。
   GitHub 新 tag 与新 `release/<完整版本>` 原子创建于构建 SHA；不覆盖旧 tag/Release。
   CNB 源码先普通推送，再从同一个 GitHub Actions run 下载包，直接调用现有 CNB
   上传脚本，以相同 SHA/tag/预发布标记发布。无需把新准备分支补进 `.cnb.yml` 的
   main/dev 触发配置，也不再调用与该配置不匹配的准备分支事件。
   Mirror 酱和自建源继续按 stable/beta 渠道发布同一版本包。
5. beta/开发线正式版发布后会创建发布记录 PR 到 dev。维护者保留后续未发布改动、
   解决可能的更新日志冲突后合并，才能继续下个 beta/转正，防止重复发布同批条目。
   补丁不送回 dev；5.6.1/5.6.2 和 5.7.0-beta.2/beta.3/5.7.0 各自推进。
   正常发布中途失败保留已创建的引用，勿删改已发布版本；未完成的平台由维护者
   使用同次 Actions 包补传。这与可删除重建的 nightly dev 不同。

## Secrets、权限与首次上线

1. **先发布 Runtime**：当前 Runtime 已有 alpha 绑定与恢复实现，本次新增
   `version.result.details.alphaBackend=dev` 供打包确认能力。发布并联调该代码后，
   再更新 AUTO-MAS dev 的 `res/runtime-version.txt` 为那个实际发布版本。
   本次不预测版本号，也不提前改钉扎；v0.1.14 和已发布的 v0.1.15 均无新能力声明，nightly 会明确失败。
   v0.1.15 发行文件的 SHA-256 与清单一致，但其构建提交为 `67e52f7`，尚未包含 `7489dee` 的声明。
2. 配置 `RELEASE_PR_TOKEN`，用于准备分支与 `.github` 同步 PR：PAT classic 需要
   repo/workflow；细粒度 PAT 或 GitHub App 需要 Contents、Pull requests、Workflows
   写权限。令牌必须能修改工作流并触发 PR 检查，本实现不回退普通 GITHUB_TOKEN。
   具体权限参见 [GitHub 令牌说明](https://docs.github.com/en/actions/concepts/security/github_token)。
   自动 PR 不合并。GITHUB_TOKEN 供入账、nightly、正式 Release 使用，需要 Contents
   写和 Actions 写；正式流程另外需要 Issues 写。准备和记录 PR 标签需预先存在：
   `release`、`skip-changelog`、`changelog-maintenance`。
3. 正常发布继续需要 `SIGNPATH_API_TOKEN`、`SENTRY_AUTH_TOKEN`、`SENTRY_ORG` /
   `SENTRY_PROJECT` 变量、`CNB_TOKEN`、`GIT_PASSWORD`、`MirrorChyanUploadToken`、
   `UPDATE_URL`。nightly 仅使用 GITHUB_TOKEN 下载 Runtime 与发布 GitHub 产物。
4. 先把实现合入 dev，再将 **仅 .github** 的首次上线 PR 合入 main，带入每日入口、
   可复用入账与同步工作流。main 上的新工作流从 dev 读取发布工具，不要求将
   scripts、版本文件、业务代码或 `.cnb.yml` 一起同步；不要将旧发布准备代码写回旧 release。
   main 已安装新同步工作流后，dev/.github 后续变化自动更新同一个同步 PR。
   删除亦同步，无差异不创建，更新仅普通推送；main 分支保护照常由维护者合并。
   **已有 release 分支的旧 push 工作流不会随 main/dev 更新自动消失。** 必须将这些
   分支的 `absorb-changelog.yml` 替换为新的仅 dev 入口或移除它，同时移除旧的
   `prepare-release.yml` / `build-app.yml` 手动发布入口，统一从 main 运行新流程。
   只改这三份 CI 入口，可随下一次经过兼容验证的修复一并纳入同一个 PR；
   不编译/清理碎片、不提升版本，不另外追加入账机器人提交，不改写已有历史。
   迁移完成前不能宣称旧 release 已停止自动入账。
5. GitHub immutable releases 不能用于滚动 dev Release；若仓库启用了这项设置，
   维护者须处理 nightly 可变发布要求。普通版本不可改写。
   CNB 远端有分叉时普通源码同步会失败，须维护者诊断，不使用 force push。

## 改动清单

| 仓库 / 文件 | 行为 |
| --- | --- |
| AUTO-MAS `.github/workflows/absorb-changelog.yml`、`nightly.yml` | 仅 dev 入账；明确依赖后构建、先 Actions 后 GitHub 发布 |
| `.github/workflows/prepare-release.yml`、`build-app.yml`、`check-changelog.yml` | 独立准备分支、选定补丁范围、按发布线守门；正常签名与多平台发布 |
| `.github/workflows/sync-github-main.yml`、`sync-cnb.yml` | 仅 .github 同步 PR；普通源码镜像推送，排除 dev 滚动 tag |
| `.github/workflows/mirrorchyan.yml`、`mirrorchyan-release-note.yml` | 手动补传必须明确正式/beta 版本，排除 nightly |
| `.github/scripts/release_automation.py`、`absorb.ps1`、`download-runtime.ps1`、`sync-cnb.ps1` | Git/GitHub 编排、失败重试、Runtime 钉扎与能力校验、源码同步 |
| `scripts/changelog.py` | 发布线、基准、版本下限、PR、编译和生成物检查；可检查旧快照 |
| `frontend/electron/services/runtimeBinaryService.ts`、`frontend/src/views/Initialization/useInitializationFlow.ts` | alpha 初始化与 Runtime 钉扎读取 dev；其他版本保留原定位 |
| `res/packaging/AUTO-MAS.iss` | alpha 的 Windows 数字文件版本 |
| `AGENTS.md`、`changelog.d/README.md`、本文件、`changelog.d/nightly-release.feat.md` | 约定、操作说明和一个用户更新日志碎片 |
| `CHANGELOG.md` | 通过生成器只同步顶部入账说明，历史版本和条目不改 |
| AUTO-MAS-Runtime `internal/cli/version.go`、`doc/架构设计.md`、`doc/任务拆分.md` | 新增可选 alpha 能力声明，复用已有滚动 dev 绑定、更新与恢复流程 |

验证文件：AUTO-MAS `tests/tools/test_release_workflows_temp.py`、
`tests/tools/test_changelog_script.py`、`frontend/electron/services/runtimeBinaryService.test.ts`，
以及 Runtime `internal/cli/version_test.go`。AUTO-MAS 的一次性验证文件保留本地，不纳入本次 PR。

## 已执行的验证与边界

- AUTO-MAS：`python -m pytest tests/tools/test_release_workflows_temp.py tests/tools/test_changelog_script.py tests/core/test_git_version.py tests/api/test_core_health.py -q`：141 通过，1 跳过。
  临时本地仓库和模拟 GitHub API 覆盖 dev 入账、真实非快进拒绝后重算、补丁与 beta 并行、旧来源保留、必要 CI 入口迁移、nightly 完整/缺失/部分失败与重试、同步 PR 增删改与重复运行。
- `python -m pytest tests --collect-only -q`：437 项收集成功。
- 前端：`yarn typecheck`、`yarn build:main` 通过；`yarn test electron/services/runtimeBinaryService.test.ts electron/services/runtimeInitializationService.test.ts electron/services/runtimeUpdateService.test.ts src/utils/changelog.test.ts`：182 项通过；三个修改过的 TypeScript 文件格式检查通过。
- Runtime：`gofmt`、`go vet ./...`、`go build -buildvcs=false ./...`、`go test -p 1 ./... -count=1` 通过；已有 alpha 首装、滚动提交更新、身份校验、启动及恢复测试随完整套件执行。
- `actionlint -shellcheck= -pyflakes=`、Python 编译、四个 `.ps1` 文件及 40 段工作流 PowerShell 语法检查通过；`scripts/changelog.py check` 和两仓库 `git diff --check` 通过。
- 隔离工作区产物检查确认 Electron 包版本 `5.6.0-alpha.123`、生产模式、Windows 文件版本 `5.6.0.0` 和未签名状态。构建会话中断后无法取回最终退出码；该产物使用 Electron 默认 NSIS，未执行工作流的 Inno/Runtime 放入步骤，不代表安装及首启验证完成。

远端定时、令牌权限、分支保护、SignPath、GitHub/CNB 实际附件发布、Mirror 酱、自建源，
以及含已发布新版 Runtime 的完整安装/便携包首启和已有 dev 工作区更新仍须部署后验收。
本次仅交付代码 PR，未发布版本或修改仓库设置；本地临时测试仓库的提交与推送仅用于验证。
