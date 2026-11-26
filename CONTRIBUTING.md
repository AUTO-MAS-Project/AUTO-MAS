# 开发起步 / Quick Start

参与开发前建议先浏览 **[AUTO-MAS 开发文档](https://doc.auto-mas.top/developer/)**；日常提 PR 只需走下面 4 步：

1. **从最新 `origin/dev` 拉出开发分支**（不要在旧本地 `dev` 上直接改）：

   ```powershell
   git fetch origin dev
   git switch --no-track -c feat/<你的功能名> origin/dev
   ```

2. **安装锁定依赖并启动**（需已安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 与 Node 24 / Yarn 4；开发端默认使用 `36164` 端口，与正式安装版 `36163` 隔离、可同时运行）：

   ```powershell
   # 仓库根目录：准备后端环境
   uv sync --locked --group dev

   # frontend/ 目录：安装前端依赖
   Set-Location frontend
   yarn install --immutable
   ```

   按开发习惯任选一种官方启动方式：

   | 模式 | 启动命令 | 适用场景 |
   | --- | --- | --- |
   | **桌面全栈（推荐）** | `cd frontend && yarn dev` | 日常联调与前端开发；Windows 自动缓存 Runtime 并在关闭窗口时回收后端进程树 |
   | **分离调试（后端断点）** | 根目录 `uv run --no-sync python main.py`（或 IDE 调试器）+ `cd frontend && yarn dev:frontend` | 给 Python 后端打断点或频繁重启后端 |
   | **轻量浏览器 / 非 Windows** | `cd frontend && yarn backend` + `cd frontend && yarn web` | 纯网页预览或非 Windows 系统 |

   > 遇到端口冲突、残留开发后端或需要生成可选的 `.vscode/launch.json` 模板时，可在仓库根目录运行 `uv run --no-sync python scripts/dev_doctor.py`（详见 [scripts/README.md](scripts/README.md)）。`requirements.txt` 与 `pyproject.toml` 并存，改依赖时同步更新两者并执行 `uv lock` 提交 `uv.lock`。桌面端完整调试见 [frontend/README.md](frontend/README.md)。

3. **参考代码样例**：

   | 改动范围 | 参考文件 | 关键约束 |
   | --- | --- | --- |
   | 后端 HTTP 接口 | `app/api/setting.py`、`app/api/queue.py` | 路由保持薄适配；破坏性接口须加 `tags=["Delete"]`；改完 schema 跑 `cd frontend && yarn openapi`，禁手改 `frontend/src/api/` |
   | 后端配置模型 | `app/models/config/setting.py` | `ConfigEntry`/`ConfigGroup` 单点声明，经 `app/config/wire.py` 派生 API 契约 |
   | WebSocket 通信 | [docs/websocket-architecture.md](docs/websocket-architecture.md) | 前后端共用唯一主连接 `/api/core/ws`，统一 `WSEnvelope` 信封 |
   | 前端页面 / 弹窗 | `frontend/src/views/setting/`、`frontend/src/components/ui/` | 单个 `.vue` ≤ 500 行；三语词表（`zh-CN`/`en-US`/`ja-JP`）同步更新；暗色只用 `--ant-*` / `html.dark` |
   | 回归测试 | `tests/scripts/test_pr_check.py`、`frontend/src/composables/useSaveQueue.test.ts` | 后端 `uv run --no-sync python -m pytest <路径> -q`；前端 Node-only（无 `jsdom`） |

4. **提 PR 前跑 1 条本地一键预检**（自动按改动路径运行对应 CI 门禁，失败会直接给出修复命令）：

   ```powershell
   # 用户可见改动先加 1 条更新日志碎片（不超过 50 字）：
   uv run --no-sync python scripts/changelog.py add <fix|feat|change> <项目键> "<一句话说明>"

   # 一键跑完本地全部相关 CI 门禁（纯文档/测试/CI 改动加 --skip-changelog）：
   uv run --no-sync python scripts/pr_check.py
   ```

   可选开启本地 `pre-push` 温和提示钩子（默认只提醒不阻断推送，并兼容已有的 `.git/hooks/`）：

   ```powershell
   git config core.hooksPath .githooks
   ```

   全绿后推送分支并向 `AUTO-MAS-Project/AUTO-MAS:dev` 提 PR（纯文档/测试/CI PR 加上 `skip-changelog` 标签）。

---

Welcome to contribute to AUTO-MAS! Please read the **[Developer Documentation](https://doc.auto-mas.top/developer/)** first. Quick start:

1. Branch off latest `origin/dev`: `git fetch origin dev && git switch --no-track -c feat/<name> origin/dev`
2. Sync locked deps: `uv sync --locked --group dev` (backend) and `cd frontend && yarn install --immutable` (frontend). Keep `requirements.txt` and `uv.lock` (`uv lock`) in sync whenever changing `pyproject.toml`.
3. Add a changelog fragment for user-visible changes (`uv run --no-sync python scripts/changelog.py add <type> <project> "<summary>"`), then run `uv run --no-sync python scripts/pr_check.py` (pass `--skip-changelog` for docs/tests/CI-only PRs) before opening a PR to `dev`.

# 重要事项 / Important Terms

您通过任意方式提交代码到 **AUTO-MAS-Project** 下属任意仓库，即代表您理解并同意以下条款：

- 您授权 **AUTO-MAS-Project** 的开发团队 **AUTO-MAS Team** 使用您所提交代码的部分权利：

    1. **版权许可**  
    您授予 **AUTO-MAS Team** 一项永久的、全球性的、不可撤销的、免版税的、非独占的版权许可，允许其使用、复制、修改、分发、公开演示和展示您的贡献，并基于您的贡献创作衍生作品。

    2. **专利许可**  
    您同时授予 **AUTO-MAS Team** 一项永久的、全球性的、不可撤销的、免版税的专利许可，覆盖您贡献中所必需的专利权利。

    3. **保留权利**  
    您仍保有您原创贡献的版权和署名权。您的姓名将作为作者保留在 Git 提交历史及项目致谢中。

- **AUTO-MAS Team** 的所有权利均授权给 [DLmaster (@DLmaster361)](https://github.com/DLmaster361)，仅该被授权人能代表 **AUTO-MAS Team** 行使全部权利。补充细则如下：

    1. 无法联系到 [DLmaster (@DLmaster361)](https://github.com/DLmaster361) 时，**AUTO-MAS Team** 相关事务由 [AUTO-MAS 主要开发者](https://github.com/orgs/AUTO-MAS-Project/teams/core) 依据社区共识处理。
    
    2. [DLmaster (@DLmaster361)](https://github.com/DLmaster361) 退出项目时，必须将 **AUTO-MAS Team** 的所有授权移交给另一项目开发者。

    3. [AUTO-MAS 主要开发者](https://github.com/orgs/AUTO-MAS-Project/teams/core) 绝对多数通过时，允许取消对 [DLmaster (@DLmaster361)](https://github.com/DLmaster361) 的授权，由 [AUTO-MAS 主要开发者](https://github.com/orgs/AUTO-MAS-Project/teams/core) 重新授权给其他项目开发者。

以上条款用于保证 **AUTO-MAS-Project** 项目拥有清晰的责任主体，能够对侵权者采取法律手段进行法律维权，并确保 **AUTO-MAS Team** 的权利不会被滥用。

By submitting code—via any means—to any repository under **AUTO-MAS-Project**, you acknowledge and agree to the following terms:

- You grant the development team of **AUTO-MAS-Project**, namely the **AUTO-MAS Team**, certain rights to your submitted code:

    1. **Copyright License**  
    You grant the **AUTO-MAS Team** a perpetual, worldwide, irrevocable, royalty-free, non-exclusive copyright license to use, copy, modify, distribute, publicly perform, and display your contribution, and to create derivative works based on it.

    2. **Patent License**  
    You also grant the **AUTO-MAS Team** a perpetual, worldwide, irrevocable, royalty-free patent license to practice any patent claims necessarily infringed by your contribution.

    3. **Reserved Rights**  
    You retain full ownership of the copyright and authorship of your original contribution. Your name will be preserved as an author in Git commit history and project acknowledgments.

- All rights of the **AUTO-MAS Team** are exclusively delegated to [DLmaster (@DLmaster361)](https://github.com/DLmaster361), who alone may represent the **AUTO-MAS Team** in exercising all such rights. The following supplementary provisions apply:

    1. If [DLmaster (@DLmaster361)](https://github.com/DLmaster361) becomes unreachable, matters concerning the **AUTO-MAS Team** shall be handled by the [AUTO-MAS Core Developers](https://github.com/orgs/AUTO-MAS-Project/teams/core) according to community consensus.

    2. Should [DLmaster (@DLmaster361)](https://github.com/DLmaster361) leave the project, they must transfer all delegated rights of the **AUTO-MAS Team** to another project developer.

    3. The [AUTO-MAS Core Developers](https://github.com/orgs/AUTO-MAS-Project/teams/core) may, by an absolute majority vote, revoke the delegation to [DLmaster (@DLmaster361)](https://github.com/DLmaster361) and reassign it to another project developer.

These terms ensure that the **AUTO-MAS-Project** maintains a clear legal representative, enabling effective enforcement against infringement and preventing misuse of the **AUTO-MAS Team**’s rights.