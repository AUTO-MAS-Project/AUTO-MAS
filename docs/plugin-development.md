# 插件源码、开发与交付

## 目录归属

主程序仓库只跟踪 `plugins/auto_mas_core`，SDK 的版本和源码随主程序更新。
其他插件以独立仓库维护，发行包通过插件中心安装。开发者可以将插件仓库克隆到
主程序的 `plugins` 目录，该目录中的其他源码由主程序 Git 忽略。

源码开发环境使用下列结构。

```text
AUTO-MAS/
  app/
  frontend/src/views/maa/    暂时保留的 MAA 静态页面
  frontend/src/views/whimbox/ 暂时保留的奇想盒静态页面
  plugins/
    auto_mas_core/         主程序跟踪的 SDK
    maa_adapter/           开发者克隆的独立仓库
    whimbox_adapter/       奇想盒独立仓库
```

Runtime 使用安装根目录保存用户插件，运行代码位于 `repo`。

```text
安装根目录/
  plugins/
    maa_adapter/           用户自行放入的源码插件
    pypi/site-packages/    插件中心安装的发行包与插件依赖
  repo/
    app/
    plugins/auto_mas_core/ 当前后端对应的 SDK
```

Runtime 从安装根目录启动后端。插件发现会扫描用户插件目录，并从当前源码目录
单独加载 SDK。Runtime 更新与源码切换保留安装根目录的 `plugins`，SDK 则随 `repo` 更新。

## 本地开发

在主程序根目录执行下列命令。若目标目录已经存在，先保留其中的本地改动，再选择空目录克隆。

```powershell
git clone https://github.com/AUTO-MAS-Project/AUTO-MAS-MAA-Adapter.git plugins/maa_adapter
cd plugins/maa_adapter
git status
```

奇想盒对应仓库为 `AUTO-MAS-Project/AUTO-MAS-Whimbox-Adapter`，本地目录为
`plugins/whimbox_adapter`。两个适配器分别维护自己的配置、执行器与专用接口。

启动主程序后，在插件中心手动启用源码插件。插件代码的提交、推送、版本推进和发布
均在该独立仓库中进行。主程序 Git 只交付 SDK。

本地源码保留同 ID 发行包的覆盖语义。验证市场安装时，先停止后端，将源码工程移出
插件扫描目录，再启动并从插件中心安装。已有托管的配置升级需要 MAA 实现时，
主程序会在领域配置激活前通过正常发行包安装入口补齐。用户主动放入的有效源码
仍可承担对应插件实现。

奇想盒的旧托管同样会在配置激活前补齐插件。先发布适配器发行包，再交付移除内置实现的
主程序版本；首个发行包发布前，使用本地源码工程或本地构建的 wheel 联调。
首发前应按实际配套 SDK 发行版本收紧插件的最低版本约束，并用该 SDK 发行包验证。
同版本号的开发源码可能包含尚未发布的接口，不能据此推断旧 SDK 已兼容。

## 前端归属

动态前端尚未上线，MAA 页面由主程序的 `frontend/src/views/maa` 维护并随桌面应用构建。
新建托管、MAA 页面路由与 MAA 计划创建入口按后端提供的插件能力开放。
动态页面上线后再将这些页面迁回插件。专项 API、配置模型、关卡缓存和语言资源
仍由 MAA 插件持有。

奇想盒页面按相同方式由 `frontend/src/views/whimbox/entry.ts` 汇入静态页面声明。
不使用计划表的专项可以不声明 `plan`。奇想盒静态页面及其中英日文案暂由主程序维护，
后端实现、通知内容、任务目录与备份恢复接口由 `whimbox_adapter` 持有。

## 回归环境

主仓专项集成回归消费锁定的已发布插件 wheel，版本与摘要见
`tests/requirements-plugins.txt`。测试插件安装到忽略目录 `.test-plugins`，
运行依赖来自 `uv.lock`，SDK 使用当前主程序源码。

```powershell
uv sync --locked --group dev
uv run --no-sync python scripts/prepare_test_plugins.py
uv run --no-sync python -m pytest tests -q
cd frontend
yarn test
yarn audit:i18n --check
yarn e2e:check
yarn e2e --grep '@plugins'
```

普通隔离浏览器测试将测试发行包复制到临时用户插件目录，再走正常初始化和启用流程。
真实与就地模式沿用所选用户环境。插件自身回归在独立仓库内执行，具体命令见插件 README。
升级集成测试使用的发行包时，同时更新版本与 PyPI wheel 的 SHA256 摘要。

## dev alpha 测试包

合入 dev 后，可以手动运行现有构建工作流生成跟随 dev 的前端测试包。

```powershell
gh workflow run ci-package.yml --repo AUTO-MAS-Project/AUTO-MAS --ref dev -f alpha=true
```

alpha 构建在构建工作区写入前端 alpha 版本，并随包交付经过摘要及能力校验的 Runtime。
首次启动由 Runtime 从 dev 准备后端源码，之后继续跟随 dev。
包内 `build-source.json` 记录前端版本、源码提交、后端分支及 Runtime 版本和摘要。
构建产物保存在对应 Actions 运行的附件中。

## 发布与用户安装

MAA 包名为 `auto-mas-maa-adapter`。插件仓库完成构建、元数据校验和版本发布后，
目录维护工作流同步市场信息，用户从插件市场安装。
主程序源码更新只带入其跟踪的 SDK 与静态页面，发行包安装结果和用户根目录源码插件
按上述目录边界继续保留。

### 在市场展示更新日志

在适配器仓库的 `CHANGELOG.md` 写入本版面向用户的变化，使用 `## [版本] - 日期` 作为章节标题。在 `pyproject.toml` 的 `[project.urls]` 声明指向该文件的公开 HTTPS `Changelog` 链接，并随发行包发布。完整示例见[插件发布指南](https://doc.auto-mas.top/plugin/start/publish.html)。

数据站目录按 PyPI 的发行版本收录最近五版内的章节。测试时刷新插件市场，在「更新」查看跨版说明，在「已安装」详情核对本机版本。主程序直接从 PyPI 或镜像刷新时，日志为空。

PyPI Trusted Publishing、标签发布与市场安装验收步骤见
[MAA 插件发布说明](https://github.com/AUTO-MAS-Project/AUTO-MAS-MAA-Adapter/blob/master/docs/PUBLISHING.md)。
