# AUTO_MAA
MAA多账号管理与自动化软件

!["软件图标"](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/AUTO_MAA.png "软件图标")

----------------------------------------------------------------------------------------------

## 重要声明
本软件是一个外部工具，旨在优化MAA多账号功能体验。该软件包可以存储明日方舟多账号数据，并通过修改MAA配置文件、读取MAA日志等行为自动完成多账号代理。本开发团队承诺，不会修改明日方舟游戏本体与相关配置文件。

本项目使用GPL开源，相关细则如下：

- **作者：** AUTO_MAA软件作者为DLmaster、DLmaster361或DLmaster_361，以上均指代同一人。
- **使用：** AUTO_MAA使用者可以按自己的意愿自由使用本软件。依据GPL，对于由此可能产生的损失，AUTO_MAA项目组不负任何责任
- **分发：** AUTO_MAA允许任何人自由分发本软件，包括进行商业活动牟利。但所有分发者必须遵循GPL向接收者提供本软件项目地址、完整的软件源码与GPL协议原文（件），违反者可能会被追究法律责任
- **传播：** AUTO_MAA原则上允许传播者自由传播本软件。但由于软件性质，项目组不希望发现任何人在明日方舟官方媒体（包括官方媒体账号与森空岛社区等）或明日方舟游戏相关内容（包括同好群、线下活动与游戏内容讨论等）下提及AUTO_MAA或MAA，希望各位理解
- **衍生：** AUTO_MAA允许任何人对软件本体或软件部分代码进行二次开发或利用。但依据GPL，相关成果也必须使用GPL开源
- **授权：** 如果希望在使用AUTO_MAA的相关成果后仍保持自己的项目闭源，请在Issues中说明来意。得到项目组认可后，我们可以提供另一份使用不同协议的代码，此协议主要内容如下：被授权者可以自由使用该代码并维持闭源；被授权者必须定期为AUTO_MAA作出贡献
- **贡献：** 不论是直接参与软件的维护编写，或是撰写文档、测试、反馈BUG、给出建议、参与讨论，都为AUTO_MAA项目的发展完善做出了不可忽视的贡献。项目组提倡各位贡献者遵照GitHub开源社区惯例，发布Issues参与项目。避免私信或私发邮件（安全性漏洞或敏感问题除外），以帮助更多用户

以上细则是本项目对GPL的相关补充与强调。未提及的以GPL为准，发生冲突的以本细则为准。如有不清楚的部分，请发Issues询问。若发生纠纷，相关内容也没有在Issues上提及的，项目组拥有最终解释权

**注意**
- 由于本软件有修改其它目录JSON文件等行为，使用前请将AUTO_MAA添加入Windows Defender信任区以及防病毒软件的信任区或开发者目录，避免被误杀

---
# 使用方法

## 安装与配置MAA

```
本软件是MAA的外部工具，需要安装配置MAA后才能使用。
```

### MAA安装

- 什么是MAA？    [官网](https://maa.plus/)/[GitHub](https://github.com/CHNZYX/Auto_Simulated_Universe/archive/refs/heads/main.zip)

- MAA下载地址    [GitHub下载](https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases)

### MAA配置

1. 完成MAA的adb配置等基本配置

2. 确保当前配置名为“Default”，取消所有“定时执行”

![MAA配置1](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置1.png "MAA配置1")

3. 取消勾选“开机自启动MAA”，勾选“启动MAA后直接运行”和“启动MAA后自动开启模拟器”。配置自己模拟器所在的位置并根据实际情况填写“等待模拟器启动时间”（建议预留10s以防意外）。如果是多开用户，需要填写“附加命令”，具体填写值参见多开模拟器对应快捷方式路径（如“-v 1”）。

![MAA配置2](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置2.png "MAA配置2")

4. 勾选“定时检查更新”、“自动下载更新包”和“自动安装更新包”

![MAA配置3](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置3.png "MAA配置3")

## 下载AUTO_MAA [![](https://img.shields.io/github/downloads/DLmaster361/AUTO_MAA/total?color=66ccff)](https://github.com/DLmaster361/AUTO_MAA/releases)

- GitHub下载地址    [GitHub下载](https://github.com/DLmaster361/AUTO_MAA/releases)

## 配置AUTO_MAA


### 启动AUTO_MAA

- 双击`AUTO_MAA.exe`以启动软件

```
注意：

首次启动时会要求设置管理密钥。

管理密钥是解密用户密码的唯一凭证，与数据库绑定。
密钥丢失或data/key/目录下任一文件损坏都将导致解密无法正常进行。

本项目采用自主开发的混合加密模式，项目组也无法找回您的管理密钥或修复data/key/目录下的文件。
如果不幸的事发生，建议您删除data/key/目录与data/data.db文件后重新录入信息。
```

### 配置信息

- 本项目已初步完成GUI开发，您可以在用户管理页与设置页配置信息。

```
特别的：

你可以自定义关卡号替换方案。
程序会读取data/gameid.txt中的数据，依据此进行关卡号的替换，便于常用关卡的使用。
gameid.txt在初始已经存储了一些常用资源本的替代方案。
```

![gameid](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/gameid.png "gameid")

## 运行代理任务

### 直接运行

- 在执行页单击`立即执行`直接运行 

### 定时运行

- 在执行页的`定时执行`栏设置时间

- 保持软件打开，软件会在设定的时间自动运行

---
# 关于

欢迎加入AUTO_MAA项目组，欢迎反馈bug

QQ群：957750551

----------------------------------------------------------------------------------------------

作者即将高考，如果喜欢本项目，请祝福他

----------------------------------------------------------------------------------------------
## 贡献者

感谢以下贡献者对本项目做出的贡献

<a href="https://github.com/DLmaster361/AUTO_MAA/graphs/contributors">

  <img src="https://contrib.rocks/image?repo=DLmaster361/AUTO_MAA" />

</a>

![Alt](https://repobeats.axiom.co/api/embed/6c2f834141eff1ac297db70d12bd11c6236a58a5.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=DLmaster361/AUTO_MAA&type=Date)](https://star-history.com/#DLmaster361/AUTO_MAA&Date)