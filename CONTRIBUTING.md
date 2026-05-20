# 开发指引 / Developer Guidelines

欢迎参与 AUTO-MAS 项目开发！参与开发前，请阅读 **AUTO-MAS 开发文档**。

- [AUTO-MAS 开发文档](https://doc.auto-mas.top/developer/)。

## 开发规范（Skills）

本仓库在 [`skills/`](./skills/) 内置工程与协作 Skill。开发代码时建议先阅读 [**mas-skills**](./skills/mas-skills/SKILL.md) 并按任务加载子 Skill（API 契约、数据模型、模块边界等）。**新增专项脚本类型**（如 MaaEnd、M9A）请参阅 [**mas-script-specialized-adapter**](./skills/mas-script-specialized-adapter/SKILL.md)。上游 `mas-*` 更新见 [skills/SYNC.md](./skills/SYNC.md)。

## Issue 与 Pull Request 怎么写

提交 Issue 或 PR 时请用**简体中文**，由**提交者本人**填写正文（勿依赖 AI 代写）。规范见 [.github/ISSUE_PR_GUIDE.md](./.github/ISSUE_PR_GUIDE.md)：

- **Issue**：创建时可选 **[Enhancement]**（背景 / 期望 / 备注）、**[bug]**（问题描述 / 版本 / 日志 / 备注），或**空白 Issue**（普通模板）。不写实现方案、代码路径或冗长验收清单。详见 [Issue 模板](./.github/ISSUE_TEMPLATE/) 与 [撰写说明](./.github/ISSUE_PR_GUIDE.md)。
- **Pull Request**：只写简短**摘要**（1～4 条），并关联 Issue（如 `Closes #123`）。打开 PR 时会自动带出 [pull_request_template.md](./.github/pull_request_template.md)。

Welcome to contribute to the AUTO-MAS project! Before participating in development, please read the **AUTO-MAS Developer Documentation**.

- [AUTO-MAS Developer Documentation](https://doc.auto-mas.top/developer/).

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