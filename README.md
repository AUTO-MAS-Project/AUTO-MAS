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

## 安装软件

```
本软件是MAA的外部工具，需要安装MAA后才能使用。
```

### 下载MAA

- 什么是MAA？    [官网](https://maa.plus/)/[GitHub](https://github.com/MaaAssistantArknights/MaaAssistantArknights)
- MAA下载地址    [GitHub下载](https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases)

### 安装MAA

- 将MAA压缩包解压至任意普通文件夹即可。
- 若为首次安装MAA，请双击`MAA.exe`启动MAA程序以生成MAA配置文件。

### 下载AUTO_MAA [![](https://img.shields.io/github/downloads/DLmaster361/AUTO_MAA/total?color=66ccff)](https://github.com/DLmaster361/AUTO_MAA/releases)

- GitHub下载地址    [GitHub下载](https://github.com/DLmaster361/AUTO_MAA/releases)

### 安装AUTO_MAA

- 将AUTO_MAA压缩包解压至任意普通文件夹即可。

## 配置AUTO_MAA

### 启动AUTO_MAA

- 双击`AUTO_MAA.exe`以启动软件。

```
注意：

    首次启动时会要求设置管理密钥。

    管理密钥是解密用户密码的唯一凭证，与用户数据库绑定。
    密钥丢失或data/key/目录下任一文件损坏都将导致解密无法正常进行。

    本项目采用自主开发的混合加密模式，项目组也无法找回您的管理密钥或修复data/key/目录下的文件。
    如果不幸的事发生，建议您删除data/key目录与config目录后重新录入信息。
```

### 配置信息

#### 设置脚本实例

1. 单击`+`并选择`MAA`以添加MAA脚本实例。
2. 在`MAA目录`选项卡中通过`选择文件夹`打开MAA软件目录以绑定MAA。
3. 在`MAA全局配置`选项卡中通过`设置`进行MAA全局设置。在打开的MAA界面完成`性能设置`、`游戏设置`、`连接设置`、`启动设置`、`界面设置`、`软件更新`等基本配置以及代理任务的详细配置。
4. 完成基本配置后，关闭MAA页面，AUTO_MAA会自动保存您的配置。

- 注意：在MAA的设置过程中，若MAA要求`立刻重启应用更改`，请选择`稍后`。否则，MAA重启后的一切更改都不会被程序记录。

- 特别的，在设置MAA过程中，您需要确保自己：
  - 在`切换配置`选项卡中选择了`Default`项。
  - 取消勾选`开机自启动MAA`。
  - 配置自己模拟器所在的位置并根据实际情况填写`等待模拟器启动时间`（建议预留10s以防意外）。
  - 如果是模拟器多开用户，还需要填写`附加命令`，具体填写值参见多开模拟器对应快捷方式路径（如`-v 1`）。

![MAA配置](https://github.com/DLmaster361/AUTO_MAA/blob/main/resources/images/README/MAA配置.png "MAA配置")


#### 设置用户配置

每一个脚本实例都有独立的用户数据库，您可以直接在`用户列表`选项卡配置用户相关信息，页面简介如下：
- `新建用户`、`删除用户`：新建一个用户到当前用户配置列表、删除当前所选第一行所对应的用户。
- `向上移动`、`向下移动`：移动用户位置，用户位置即代理顺序。
- `模式转换`：将当前所选第一行所对应的用户转为高级/简洁配置模式。
- `用户选项配置`：选择用户与对应配置项目，执行对应配置流程。
  - `自定义基建`：选择自定义基建配置文件。
  - `日常`、`剿灭`：打开MAA界面进行设置，设置方法与MAA全局配置相同。
- `显示密码`：输入管理密钥以显示用户密码，仅当管理密钥正确时能够修改`密码栏目`。
- `简洁用户配置列表`：仅支持核心代理选项的设置，其它设置选项沿用MAA的全局设置，部分代理核心功能选项由程序托管。
- `高级用户配置列表`：支持几乎所有代理选项的设置，通过`用户选项配置`进行MAA自定义，仅部分代理核心功能选项由程序托管。
- `用户配置列表栏目`详解如下：
  - `用户名`：展示在执行界面的用户名，用于区分不同用户。
  - `账号ID`：MAA进行账号切换所需的凭据，官服用户请输入手机号码、B服请输入B站ID。
  - `服务器`：当前支持官服、B服。
  - `代理天数`：剩余需要进行代理的天数，输入`任意负数`可设置为无限代理天数，当剩余天数为0时不再代理或排查。
  - `状态`：用户的状态，禁用时将不再对其进行代理或排查。
  - `执行情况`：当日执行情况，不可编辑。
  - `关卡`、`备选关卡-1`、`备选关卡-2`：关卡号。
  - `日常`：单独设定是否进行自动代理的日常部分，可进一步配置MAA的具体代理任务，该配置与全局MAA配置相互独立。
  - `剿灭`：单独设定是否进行自动代理的剿灭部分，高级配置模式下可进一步配置MAA的具体代理任务，该配置与全局MAA配置相互独立。
  - `自定义基建`：是否启用自定义基建功能，需要进一步配置自定义基建文件，该配置与其他用户相互独立。
  - `密码`：仅用于登记用户的密码，可留空。
  - `备注`：用于备注用户信息。

- 特别的：
  - 对于`简洁用户配置列表的关卡、备选关卡-1、备选关卡-2栏目`您可以自定义关卡号替换方案。
  - 程序会读取`data/gameid.txt`中的数据，依据此进行关卡号的替换，便于常用关卡的使用。
  - `gameid.txt`会在程序首次运行时生成，其中将预置一些常用资源本的替换方案。

![gameid](https://github.com/DLmaster361/AUTO_MAA/blob/main/resources/images/README/gameid.png "gameid")

#### 设置调度队列

- 单个调度队列可包含至多10个定时与至多10个任务实例。
- 调度队列状态为关闭时，将不会定时启动该调度队列，但仍能在主调度台直接运行该调度队列。
- 同一调度队列内任务实例被依次挨个调起运行，非同一调度队列内的不同任务实例可被同时调起。
- 同一时间内，任何脚本实例或调度队列都不会被重复调起，若某一任务运行时发现同一任务已在运行，将自动跳过。

#### 设置AUTO_MAA

- 详见软件中对应选项卡的注解。

## 运行代理任务

### 直接运行

- 在`调度中心`的`主调度台`选择对应任务与`自动代理`模式，单击`开始任务`即可开始代理。

### 定时运行

- 将调度队列状态设为开启，并在`定时`选项卡设置定时启动时间。
- 保持软件开启，软件会在设定的时间自动运行。

## 人工排查代理结果

### 直接开始人工排查

- 在`调度中心`的`主调度台`选择对应任务与`人工排查`模式，单击`开始任务`即可开始人工排查。
- 软件将调起MAA，依次登录各用户的账号。
- 完成PRTS登录后，请人工检查代理情况，可以手动完成未代理的任务。
- 在对话框中单击对应账号的代理情况。
- 结束人工排查后，相应排查情况将被写入用户管理页的`备注栏目`。

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

- QQ群：[957750551](https://qm.qq.com/q/bd9fISNoME)

---

如果喜欢这个项目的话，给作者来杯咖啡吧！

![payid](https://github.com/DLmaster361/AUTO_MAA/blob/main/resources/README/payid.png "payid")
