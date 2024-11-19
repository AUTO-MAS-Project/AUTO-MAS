# AUTO_MAA

MAA多账号管理与自动化软件

!["软件图标"](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/AUTO_MAA.png "软件图标")

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

本软件是明日方舟第三方软件`MAA`的第三方工具，即第3^3^方软件。旨在优化MAA多账号功能体验，并通过一些方法解决MAA项目未能解决的部分问题，提高代理的稳定性。

### 原理

本软件可以存储多个明日方舟账号数据，并通过以下流程实现代理功能：

1. **配置：** 根据对应用户的配置信息，生成配置文件并将其导入MAA。
2. **监测：** 在MAA开始代理后，持续读取MAA的日志以判断其运行状态。当软件认定MAA出现异常时，通过重启MAA使之仍能继续完成任务。
3. **循环：** 重复上述步骤，使MAA依次完成各个用户的日常代理任务。

### 优势

- **节省运行开销：** 只需要一份MAA软件与一个模拟器，无需多开就能完成多账号代理，羸弱的电脑也能代理日常。
- **自定义空间大：** 依靠高级用户配置模式，支持MAA几乎所有设置选项自定义，同时保留对模拟器多开的支持。
- **一键代理无忧：** 无须中途手动修改MAA配置，将繁琐交给AUTO_MAA，把游戏留给自己。
- **代理结果复核：** 通过人工排查功能核实各用户代理情况，堵住日常代理的最后一丝风险。

## 重要声明

本开发团队承诺，不会修改明日方舟游戏本体与相关配置文件。本项目使用GPL开源，相关细则如下：

- **作者：** AUTO_MAA软件作者为DLmaster、DLmaster361或DLmaster_361，以上均指代同一人。
- **使用：** AUTO_MAA使用者可以按自己的意愿自由使用本软件。依据GPL，对于由此可能产生的损失，AUTO_MAA项目组不负任何责任。
- **分发：** AUTO_MAA允许任何人自由分发本软件，包括进行商业活动牟利。但所有分发者必须遵循GPL向接收者提供本软件项目地址、完整的软件源码与GPL协议原文（件），违反者可能会被追究法律责任。
- **传播：** AUTO_MAA原则上允许传播者自由传播本软件。但由于软件性质，项目组不希望发现任何人在明日方舟官方媒体（包括官方媒体账号与森空岛社区等）或明日方舟游戏相关内容（包括同好群、线下活动与游戏内容讨论等）下提及AUTO_MAA或MAA，希望各位理解。
- **衍生：** AUTO_MAA允许任何人对软件本体或软件部分代码进行二次开发或利用。但依据GPL，相关成果也必须使用GPL开源。
- **授权：** 如果希望在使用AUTO_MAA的相关成果后仍保持自己的项目闭源，请在Issues中说明来意。得到项目组认可后，我们可以提供另一份使用不同协议的代码，此协议主要内容如下：被授权者可以自由使用该代码并维持闭源；被授权者必须定期为AUTO_MAA作出贡献。
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

- 什么是MAA？    [官网](https://maa.plus/)/[GitHub](https://github.com/CHNZYX/Auto_Simulated_Universe/archive/refs/heads/main.zip)

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

    管理密钥是解密用户密码的唯一凭证，与数据库绑定。
    密钥丢失或data/key/目录下任一文件损坏都将导致解密无法正常进行。

    本项目采用自主开发的混合加密模式，项目组也无法找回您的管理密钥或修复data/key/目录下的文件。
    如果不幸的事发生，建议您删除data/key/目录与data/data.db文件后重新录入信息。
```

### 配置信息

#### 设置MAA

1. 通过`浏览`绑定MAA后，单击`设置MAA`进行MAA全局设置。

2. 在打开的MAA界面完成`性能设置`、`游戏设置`、`连接设置`、`启动设置`、`界面设置`、`软件更新`等基本配置以及代理任务的详细配置。

3. 完成基本配置后，关闭MAA页面，AUTO_MAA会自动保存您的配置。

- 注意：在MAA的设置过程中，若MAA要求`立刻重启应用更改`，请选择`稍后`。否则，MAA重启后的一切更改都不会被程序记录。

- 特别的，您需要确保自己：
  - 取消勾选`开机自启动MAA`。
  - 配置自己模拟器所在的位置并根据实际情况填写`等待模拟器启动时间`（建议预留10s以防意外）。
  - 如果是模拟器多开用户，还需要填写`附加命令`，具体填写值参见多开模拟器对应快捷方式路径（如`-v 1`）。

![MAA配置](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置.png "MAA配置")

#### 设置AUTO_MAA

本项目已基本完成GUI开发，您可以直接在设置页配置AUTO_MAA相关信息，页面简介如下：
- `MAA路径`：该项无法直接编辑，仅用于展示当前程序所绑定MAA的路径。
- `浏览`：选择MAA文件夹。
- `设置MAA`：编辑MAA全局配置，具体使用方法参见前文。
- `日常限制`：执行日常代理的日常部分时的超时阈值，当MAA日志无变化时间超过阈值时，视为超时。
- `剿灭限制`：执行日常代理的剿灭部分时的超时阈值，当MAA日志无变化时间超过阈值时，视为超时。
- `运行失败重试次数上限`：对于每一用户，若超过该次数限制仍未完成代理，视为代理失败。
- `开机自动启动AUTO_MAA`：实现AUTO_MAA的自启动。
- `AUTO_MAA启动时禁止电脑休眠`：仅阻止电脑自动休眠，不会影响屏幕是否熄灭。
- `启动AUTO_MAA后直接代理`：在AUTO_MAA启动后立即执行代理任务。
- `通过邮件通知结果`：在AUTO_MAA完成任务后将结果发送至用户指定邮箱。
- `检查版本更新`：从GitHub上获取版本更新，要求网络能够访问GitHub。获取版本信息时若遇网络不稳定，主程序有概率未响应，稍等片刻后恢复。
- `修改管理密钥`：修改管理密钥，当用户列表中无用户时，将跳过验证旧管理密钥。

#### 设置用户配置

本项目已基本完成GUI开发，您可以直接在用户管理页配置用户相关信息，页面简介如下：
- `新建`、`删除`：新建一个用户到当前用户配置列表、删除当前所选第一行所对应的用户。
- `转为高级/简洁`：将当前所选第一行所对应的用户转为高级/简洁配置模式。
- `修改配置`：修改更深层的用户配置信息，当前支持该项的有`简洁用户配置列表的自定义基建栏目`、`高级用户配置列表的日常、剿灭栏目`，详解如下：
  - `简洁用户配置列表的自定义基建栏目`：获取自定义基建的JSON文件。
  - `高级用户配置列表的日常、剿灭栏目`：打开MAA进行具体的任务配置，配置方法参见上文。注意，此时你还需要确保所要执行的任务被勾选。
- `显示密码`：输入管理密钥以显示用户密码，仅当管理密钥正确时能够修改`密码栏目`。
- `刷新`：清除临时保存的管理密钥。
- `简洁用户配置列表`：仅支持核心代理选项的设置，其它设置选项沿用MAA的全局设置，部分代理核心功能选项由程序托管。
- `高级用户配置列表`：支持几乎所有代理选项的设置，通过`修改配置`进行MAA自定义，仅部分代理核心功能选项由程序托管。
- `用户配置列表栏目`：详解如下：
  - `用户名`：展示在执行界面的用户名，用于区分不同用户。
  - `账号ID`：MAA进行账号切换所需的凭据，官服用户请输入手机号码、B服请输入B站ID。
  - `服务器`：当前支持官服、B服。
  - `代理天数`：剩余需要进行代理的天数，输入`任意负数`可设置为无限代理天数，当剩余天数为0时不再代理或排查。
  - `状态`：用户的状态，禁用时将不再对其进行代理或排查。
  - `执行情况`：当日执行情况，不可编辑。
  - `关卡`、`备选关卡-1`、`备选关卡-2`：关卡号。
  - `日常`：单独设定是否进行日常代理的日常部分，可进一步配置MAA的具体代理任务，该配置与全局MAA配置相互独立。
  - `剿灭`：单独设定是否进行日常代理的剿灭部分，高级配置模式下可进一步配置MAA的具体代理任务，该配置与全局MAA配置相互独立。
  - `自定义基建`：是否启用自定义基建功能，可进一步配置自定义基建文件，该配置与其他用户相互独立。
  - `密码`：仅用于登记用户的密码，可留空。
  - `备注`：用于备注用户信息。

- 特别的：
  - 对于`简洁用户配置列表的关卡、备选关卡-1、备选关卡-2栏目`您可以自定义关卡号替换方案。
  - 程序会读取`data/gameid.txt`中的数据，依据此进行关卡号的替换，便于常用关卡的使用。
  - `gameid.txt`会在程序首次运行时生成，其中将预置一些常用资源本的替换方案。

![gameid](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/gameid.png "gameid")

## 运行代理任务

### 直接运行

- 在执行页单击`立即执行`直接运行。

### 定时运行

- 在执行页的`定时执行`栏设置时间。

- 保持软件打开，软件会在设定的时间自动运行。

## 人工排查代理结果

### 直接开始人工排查

- 在执行页单击`开始排查`启动排查进程。

- 软件将调起MAA，依次登录各用户的账号。

- 完成PRTS登录后，请人工检查代理情况，可以手动完成未代理的任务。

- 在对话框中单击对应账号的代理情况。

- 结束人工排查后，相应排查情况将被写入用户管理页的`备注栏目`。

---

# 关于

## 未来开发方向

- [x] 支持B服
- [x] 支持完全自定义MAA配置
- [x] 支持程序版本更新
- [ ] 支持对MAA运行状况的进一步识别
- [ ] 支持宽幅ADB连接适配
- [ ] 添加更多通知手段
- [ ] GUI界面美化

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

- QQ群：957750551

---

如果喜欢这个项目的话，给作者来杯咖啡吧！

![payid](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/payid.png "payid")