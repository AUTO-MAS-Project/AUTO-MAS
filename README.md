<h1 align="center">AUTO-MAS</h1>
<p align="center">
  多脚本多配置统一管理与自动化软件<br><br>
  <img alt="软件图标" src="https://auto-mas.top/resources/icon.png">
</p>

---

<p align="center">
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/stargazers"><img alt="GitHub Stars" src="https://img.shields.io/github/stars/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/network"><img alt="GitHub Forks" src="https://img.shields.io/github/forks/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/latest"><img alt="GitHub Downloads" src="https://img.shields.io/github/downloads/AUTO-MAS-Project/AUTO-MAS/total?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/issues"><img alt="GitHub Issues" src="https://img.shields.io/github/issues/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/graphs/contributors"><img alt="GitHub Contributors" src="https://img.shields.io/github/contributors/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/blob/main/LICENSE"><img alt="GitHub License" src="https://img.shields.io/github/license/AUTO-MAS-Project/AUTO-MAS?style=flat-square"></a>
  <a href="https://deepwiki.com/AUTO-MAS-Project/AUTO-MAS"><img alt="DeepWiki" src="https://deepwiki.com/badge.svg"></a>
  <a href="https://mirrorchyan.com/zh/projects?rid=AUTO-MAS&source=auto_mas-readme"><img alt="mirrorc" src="https://img.shields.io/badge/Mirror%E9%85%B1-%239af3f6?logo=countingworkspro&logoColor=4f46e5"></a>
</p>

## 软件介绍

### 性质

本软件是自动化脚本类软件的管理工具，能够管理大量脚本并存储多个用户配置、设计自动化任务流、监看脚本日志，提高自动化代理效率与稳定性。

- **集中管理**：一站式管理多个脚本与多个用户配置，和凌乱的散装脚本窗口说再见！
- **无人值守**：监看脚本日志并自动处理报错，再也不用为代理任务卡死时自己不在电脑旁烦恼啦！
- **配置灵活**：通过调度队列与脚本的组合设计调度队列，自由实现您能想到的所有调度需求！
- **代理记录**：记录所有代理记录与日志片段，定位问题更快更准更方便！

### 原理

本软件可以存储多个脚本的多个配置，并通过以下流程实现代理功能：

1. **配置：** 根据对应用户的配置信息，生成配置文件并将其导入对应脚本。
2. **监测：** 在脚本开始代理后，持续读取脚本日志以判断其运行状态。当软件认定脚本出现异常时，通过重启脚本使之仍能继续完成任务。
3. **循环：** 重复上述步骤，使脚本依次完成各个用户的自动代理任务。

## 重要声明

本开发团队承诺，不会主动修改游戏本体与相关配置文件。本项目使用GPL开源，相关细则如下：

- **作者：** AUTO-MAS 项目作者为 AUTO-MAS Team，AUTO-MAS Team 的所有权利均授权给 [DLmaster (@DLmaster361)](https://github.com/DLmaster361)，仅该被授权人能代表 AUTO-MAS Team 行使全部权利。
- **使用：** AUTO-MAS 使用者可以按自己的意愿自由使用本软件。依据GPL，对于由此可能产生的损失，AUTO-MAS Team 不负任何责任。
- **分发：** AUTO-MAS 允许任何人自由分发本软件，包括进行商业活动牟利。若为直接分发本软件，必须遵循 GPL 向接收者提供本软件项目地址、完整的软件源码与 GPL 协议原文（件）；若为修改软件后进行分发，必须遵循 GPL 向接收者提供本软件项目地址、修改前的完整软件源码副本与 GPL 协议原文（件），违反者可能会被追究法律责任。
- **传播：** AUTO-MAS 原则上允许传播者自由传播本软件，但无论在何种传播过程中，不得删除原有版权声明，不得隐瞒 AUTO-MAS Team 的存在。由于软件性质，AUTO-MAS Team 不希望发现任何人在游戏官方媒体（包括官方媒体账号与官方社区等）或游戏相关内容（包括同好群、线下活动与游戏内容讨论等）下提及 AUTO-MAS 或相关自动化软件，希望各位理解。
- **衍生：** AUTO-MAS 允许任何人对软件本体或软件部分代码进行二次开发或利用。但依据GPL，相关成果再次分发时也必须使用GPL或兼容的协议开源。
- **图像：** `AUTO-MAS 图标` 并不适用开源协议，著作权归 [NARINpopo](https://space.bilibili.com/1877154) 画师所有，商业使用权归 [DLmaster (@DLmaster361)](https://github.com/DLmaster361) 所有，软件用户仅拥有非商业使用权。不得以开源协议已授权为由在未经授权的情况下使用 `AUTO-MAS 图标`，不得在未经授权的情况下将 `AUTO-MAS 图标` 用于任何商业用途。

以上细则是本项目对GPL的相关补充与强调。未提及的以 GPL 为准，发生冲突的以本细则为准。如有不清楚的部分，请发 Issues 询问。若发生纠纷，相关内容也没有在 Issues 上提及的，AUTO-MAS Team 拥有最终解释权。

## 使用方法

访问 AUTO-MAS 官方文档站以获取使用指南和更多项目相关信息

- [AUTO-MAS 官方文档站](https://doc.auto-mas.top)

## 代码签名策略（Code signing policy）

免费代码签名由 [SignPath.io](https://signpath.io/) 提供，证书由 [SignPath Foundation](https://signpath.org/) 提供。

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

- 审批人（Approvers）: [DLmaster (@DLmaster361)](https://github.com/DLmaster361)

## 隐私政策（Privacy policy）

为更好地提供服务，AUTO-MAS 将自动收集以下信息：

- 软件版本号
- 运行时错误信息

AUTO-MAS 尊重并保护用户隐私，上报的所有信息均经过匿名化处理，不包含任何个人身份信息。所收集的数据存储于 AUTO-MAS 官方服务器，不会传输至任何第三方机构或设施。

To better serve you, AUTO-MAS will automatically collect the following information:

- Software version number
- Runtime error information

AUTO-MAS respects and protects user privacy, all collected information has been anonymized and does not contain any personal identity information. All collected data is stored on the official server of AUTO-MAS, and will not be transmitted to any third-party institution or facility.


---

# 关于

## 特别鸣谢

- 下载服务器：由[AoXuan (@ClozyA)](https://github.com/ClozyA) 个人为项目赞助。

## 贡献者

感谢以下贡献者对本项目做出的贡献

<a href="https://github.com/AUTO-MAS-Project/AUTO-MAS/graphs/contributors">

  <img src="https://contrib.rocks/image?repo=AUTO-MAS-Project/AUTO-MAS" />

</a>

![Alt](https://repobeats.axiom.co/api/embed/6c2f834141eff1ac297db70d12bd11c6236a58a5.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=AUTO-MAS-Project/AUTO-MAS&type=Date)](https://star-history.com/#AUTO-MAS-Project/AUTO-MAS&Date)

## 交流与赞助

欢迎加入AUTO-MAS项目组，欢迎反馈bug

- QQ交流群：[957750551](https://qm.qq.com/q/bd9fISNoME)

