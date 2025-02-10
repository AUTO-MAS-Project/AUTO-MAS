# AUTO_MAA

MAA多账号管理与自动化软件

!["软件图标"](https://github.com/DLmaster361/AUTO_MAA/blob/main/resources/images/AUTO_MAA.png "软件图标")

---

</h1>

[![GitHub Stars](https://img.shields.io/github/stars/DLmaster361/AUTO_MAA?style=flat-square)](https://github.com/DLmaster361/AUTO_MAA/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/DLmaster361/AUTO_MAA?style=flat-square)](https://github.com/DLmaster361/AUTO_MAA/network)
[![GitHub Issues](https://img.shields.io/github/issues/DLmaster361/AUTO_MAA?style=flat-square)](https://github.com/DLmaster361/AUTO_MAA/issues)
[![GitHub Contributors](https://img.shields.io/github/contributors/DLmaster361/AUTO_MAA?style=flat-square)](https://github.com/DLmaster361/AUTO_MAA/graphs/contributors)
[![GitHub License](https://img.shields.io/github/license/DLmaster361/AUTO_MAA?style=flat-square)](https://github.com/DLmaster361/AUTO_MAA/blob/main/LICENSE)
</div>

## 软件介绍

### 性质

本软件是明日方舟第三方软件`MAA`的第三方工具，即第3<sup>3</sup>方软件。旨在优化MAA多账号功能体验，并通过一些方法解决MAA项目未能解决的部分问题，提高代理的稳定性。

### 原理

本软件可以存储多个明日方舟账号数据，并通过以下流程实现代理功能：

1. **配置：** 根据对应用户的配置信息，生成配置文件并将其导入MAA。
2. **监测：** 在MAA开始代理后，持续读取MAA的日志以判断其运行状态。当软件认定MAA出现异常时，通过重启MAA使之仍能继续完成任务。
3. **循环：** 重复上述步骤，使MAA依次完成各个用户的自动代理任务。

### 优势

- **节省运行开销：** 只需要一份MAA软件与一个模拟器，无需多开就能完成多账号代理，羸弱的电脑也能代理日常。
- **自定义空间大：** 依靠高级用户配置模式，支持MAA几乎所有设置选项自定义，支持模拟器多开。
- **调度方法自由：** 通过调度队列功能，自由实现MAA多开等多种调度方式。
- **一键代理无忧：** 无须中途手动修改MAA配置，将繁琐交给AUTO_MAA，把游戏留给自己。
- **代理结果复核：** 通过人工排查功能核实各用户代理情况，堵住自动代理的最后一丝风险。

## 重要声明

本开发团队承诺，不会修改明日方舟游戏本体与相关配置文件。本项目使用GPL开源，相关细则如下：

- **作者：** AUTO_MAA软件作者为DLmaster、DLmaster361或DLmaster_361，以上均指代同一人。
- **使用：** AUTO_MAA使用者可以按自己的意愿自由使用本软件。依据GPL，对于由此可能产生的损失，AUTO_MAA项目组不负任何责任。
- **分发：** AUTO_MAA允许任何人自由分发本软件，包括进行商业活动牟利。若为直接分发本软件，必须遵循GPL向接收者提供本软件项目地址、完整的软件源码与GPL协议原文（件）；若为修改软件后进行分发，必须遵循GPL向接收者提供本软件项目地址、修改前的完整软件源码副本与GPL协议原文（件），违反者可能会被追究法律责任。
- **传播：** AUTO_MAA原则上允许传播者自由传播本软件，但无论在何种传播过程中，不得删除项目作者与开发者所留版权声明，不得隐瞒项目作者与相关开发者的存在。由于软件性质，项目组不希望发现任何人在明日方舟官方媒体（包括官方媒体账号与森空岛社区等）或明日方舟游戏相关内容（包括同好群、线下活动与游戏内容讨论等）下提及AUTO_MAA或MAA，希望各位理解。
- **衍生：** AUTO_MAA允许任何人对软件本体或软件部分代码进行二次开发或利用。但依据GPL，相关成果再次分发时也必须使用GPL或兼容的协议开源。
- **贡献：** 不论是直接参与软件的维护编写，或是撰写文档、测试、反馈BUG、给出建议、参与讨论，都为AUTO_MAA项目的发展完善做出了不可忽视的贡献。项目组提倡各位贡献者遵照GitHub开源社区惯例，发布Issues参与项目。避免私信或私发邮件（安全性漏洞或敏感问题除外），以帮助更多用户。

以上细则是本项目对GPL的相关补充与强调。未提及的以GPL为准，发生冲突的以本细则为准。如有不清楚的部分，请发Issues询问。若发生纠纷，相关内容也没有在Issues上提及的，项目组拥有最终解释权。

**注意**

- 由于本软件有修改其它目录JSON文件等行为，使用前请将AUTO_MAA添加入Windows Defender信任区以及防病毒软件的信任区或开发者目录，避免被误杀。

---

# 使用方法

本项目已改用腾讯文档展示使用方法

- [《AUTO_MAA用户指南》](https://docs.qq.com/aio/DQ2NwUHRiWGtMWHBy)

---

# 关于

## 项目开发情况

可在[《AUTO_MAA开发者协作文档》](https://docs.qq.com/aio/DQ3Z5eHNxdmxFQmZX)的`开发任务`页面中查看开发进度。

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

![payid](https://github.com/DLmaster361/AUTO_MAA/blob/main/resources/README/payid.png "payid")
