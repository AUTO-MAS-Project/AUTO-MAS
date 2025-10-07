<h1 align="center">AUTO_MAA</h1>
<p align="center">
  MAA多账号管理与自动化软件<br><br>
  <img alt="软件图标" src="https://github.com/DLmaster361/AUTO_MAA/blob/main/resources/images/AUTO_MAA.png">
</p>

---

<p align="center">
  <a href="https://github.com/DLmaster361/AUTO_MAA/stargazers"><img alt="GitHub Stars" src="https://img.shields.io/github/stars/DLmaster361/AUTO_MAA?style=flat-square"></a>
  <a href="https://github.com/DLmaster361/AUTO_MAA/network"><img alt="GitHub Forks" src="https://img.shields.io/github/forks/DLmaster361/AUTO_MAA?style=flat-square"></a>
  <a href="https://github.com/DLmaster361/AUTO_MAA/releases/latest"><img alt="GitHub Downloads" src="https://img.shields.io/github/downloads/DLmaster361/AUTO_MAA/total?style=flat-square"></a>
  <a href="https://github.com/DLmaster361/AUTO_MAA/issues"><img alt="GitHub Issues" src="https://img.shields.io/github/issues/DLmaster361/AUTO_MAA?style=flat-square"></a>
  <a href="https://github.com/DLmaster361/AUTO_MAA/graphs/contributors"><img alt="GitHub Contributors" src="https://img.shields.io/github/contributors/DLmaster361/AUTO_MAA?style=flat-square"></a>
  <a href="https://github.com/DLmaster361/AUTO_MAA/blob/main/LICENSE"><img alt="GitHub License" src="https://img.shields.io/github/license/DLmaster361/AUTO_MAA?style=flat-square"></a>
  <a href="https://deepwiki.com/DLmaster361/AUTO_MAA"><img alt="DeepWiki" src="https://deepwiki.com/badge.svg"></a>
  <a href="https://mirrorchyan.com/zh/projects?rid=AUTO_MAA&source=auto_maa-readme"><img alt="mirrorc" src="https://img.shields.io/badge/Mirror%E9%85%B1-%239af3f6?logo=countingworkspro&logoColor=4f46e5"></a>
</p>

## 软件介绍

### 性质

本软件是明日方舟第三方软件`MAA`的第三方工具，即第3<sup>3</sup>方软件。旨在优化MAA多账号功能体验，并通过一些方法解决MAA项目未能解决的部分问题，提高代理的稳定性。

- **集中管理**：一站式管理多个MAA脚本与多个用户配置，和凌乱的散装脚本窗口说再见！
- **无人值守**：自动处理MAA相关报错，再也不用为代理任务卡死时自己不在电脑旁烦恼啦！
- **配置灵活**：通过调度队列与脚本的组合，自由实现您能想到的所有调度需求！
- **信息统计**：自动统计用户的公招与关卡掉落物，看看这个月您的收益是多少！

### 原理

本软件可以存储多个明日方舟账号数据，并通过以下流程实现代理功能：

1. **配置：** 根据对应用户的配置信息，生成配置文件并将其导入MAA。
2. **监测：** 在MAA开始代理后，持续读取MAA的日志以判断其运行状态。当软件认定MAA出现异常时，通过重启MAA使之仍能继续完成任务。
3. **循环：** 重复上述步骤，使MAA依次完成各个用户的自动代理任务。

### 优势

- **高效稳定**：通过日志监测、异常处理等机制，保障代理任务顺利完成。
- **简洁易用**：无需手动修改配置文件，实现自动化调度与多开管理。
- **兼容扩展**：支持 MAA 几乎所有的配置选项，满足不同用户需求。

## 重要声明

本开发团队承诺，不会修改明日方舟游戏本体与相关配置文件。本项目使用GPL开源，相关细则如下：

- **作者：** AUTO_MAA软件作者为DLmaster、DLmaster361或DLmaster_361，以上均指代同一人。
- **使用：** AUTO_MAA使用者可以按自己的意愿自由使用本软件。依据GPL，对于由此可能产生的损失，AUTO_MAA项目组不负任何责任。
- **分发：** AUTO_MAA允许任何人自由分发本软件，包括进行商业活动牟利。若为直接分发本软件，必须遵循GPL向接收者提供本软件项目地址、完整的软件源码与GPL协议原文（件）；若为修改软件后进行分发，必须遵循GPL向接收者提供本软件项目地址、修改前的完整软件源码副本与GPL协议原文（件），违反者可能会被追究法律责任。
- **传播：** AUTO_MAA原则上允许传播者自由传播本软件，但无论在何种传播过程中，不得删除项目作者与开发者所留版权声明，不得隐瞒项目作者与相关开发者的存在。由于软件性质，项目组不希望发现任何人在明日方舟官方媒体（包括官方媒体账号与森空岛社区等）或明日方舟游戏相关内容（包括同好群、线下活动与游戏内容讨论等）下提及AUTO_MAA或MAA，希望各位理解。
- **衍生：** AUTO_MAA允许任何人对软件本体或软件部分代码进行二次开发或利用。但依据GPL，相关成果再次分发时也必须使用GPL或兼容的协议开源。
- **贡献：** 不论是直接参与软件的维护编写，或是撰写文档、测试、反馈BUG、给出建议、参与讨论，都为AUTO_MAA项目的发展完善做出了不可忽视的贡献。项目组提倡各位贡献者遵照GitHub开源社区惯例，发布Issues参与项目。避免私信或私发邮件（安全性漏洞或敏感问题除外），以帮助更多用户。
- **图像：** `AUTO_MAA主页默认图像` 并不适用开源协议，著作权归 [NARINpopo](https://space.bilibili.com/1877154) 画师所有，商业使用权归 [DLmaster (@DLmaster361)](https://github.com/DLmaster361) 所有，软件用户仅拥有非商业使用权。不得以开源协议已授权为由在未经授权的情况下使用 `AUTO_MAA主页默认图像`，不得在未经授权的情况下将 `AUTO_MAA主页默认图像` 用于任何商业用途。

以上细则是本项目对GPL的相关补充与强调。未提及的以GPL为准，发生冲突的以本细则为准。如有不清楚的部分，请发Issues询问。若发生纠纷，相关内容也没有在Issues上提及的，项目组拥有最终解释权。

---

# 使用方法

访问AUTO_MAA官方文档站以获取使用指南和项目相关信息

- [AUTO_MAA官方文档站](https://doc.auto-mas.top)

---

# 关于

## 项目开发情况

可在[《AUTO_MAA开发者协作文档》](https://docs.qq.com/aio/DQ3Z5eHNxdmxFQmZX)的`开发任务`页面中查看开发进度。

## 代码签名策略（Code signing policy）

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/)

- 审批人（Approvers）: [DLmaster (@DLmaster361)](https://github.com/DLmaster361)

## 隐私政策（Privacy policy）

除非用户、安装者或使用者特别要求，否则本程序不会将任何信息传输到其他网络系统。

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

## 特别鸣谢

- 下载服务器：由[AoXuan (@ClozyA)](https://github.com/ClozyA) 个人为项目赞助。

- EXE签名: 由 [SignPath.io](https://signpath.io/)提供免费代码签名，签名来自[SignPath Foundation](https://signpath.org/)。

## 贡献者

感谢以下贡献者对本项目做出的贡献

<a href="https://github.com/DLmaster361/AUTO_MAA/graphs/contributors">

  <img src="https://contrib.rocks/image?repo=DLmaster361/AUTO_MAA" />

</a>

![Alt](https://repobeats.axiom.co/api/embed/6c2f834141eff1ac297db70d12bd11c6236a58a5.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=DLmaster361/AUTO_MAA&type=Date)](https://star-history.com/#DLmaster361/AUTO_MAA&Date)

## 交流与赞助

欢迎加入AUTO_MAA项目组，欢迎反馈bug

- QQ交流群：[957750551](https://qm.qq.com/q/bd9fISNoME)

---

如果喜欢这个项目的话，给作者来杯咖啡吧！

![payid](resources/images/README/payid.png "payid")
