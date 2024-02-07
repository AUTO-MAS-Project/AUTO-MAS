# AUTO_MAA
MAA多账号管理与自动化软件

----------------------------------------------------------------------------------------------

## 免责声明
本软件是一个外部工具，旨在优化MAA多账号功能体验。该软件包可以存储多账号数据，并通过修改MAA配置文件、读取MAA日志等行为自动完成多账号代理。

This software is open source, free of charge and for learning and exchange purposes only. The developer team has the final right to interpret this project. All problems arising from the use of this software are not related to this project and the developer team. If you encounter a merchant using this software to practice on your behalf and charging for it, it may be the cost of equipment and time, etc. The problems and consequences arising from this software have nothing to do with it.

本软件开源、免费，仅供学习交流使用。开发者团队拥有本项目的最终解释权。使用本软件产生的所有问题与本项目与开发者团队无关。若您遇到商家使用本软件进行代练并收费，可能是设备与时间等费用，产生的问题及后果与本软件无关。

## 安装与配置MAA

本软件是MAA的外部工具，需要安装配置MAA后才能使用。

**MAA安装**

什么是MAA？    [官网](https://maa.plus/)/[GitHub](https://github.com/CHNZYX/Auto_Simulated_Universe/archive/refs/heads/main.zip)

MAA下载地址    [GitHub下载](https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases)

**MAA配置**

1.完成MAA的adb配置等基本配置

2.在“完成后”菜单，选择“退出MAA和模拟器”。勾选“手动输入关卡名”和“无限吃48小时内过期的理智药”

![MAA配置1](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置1.png "MAA配置1")

3.确保当前配置名为“Default”，取消所有“定时执行”

![MAA配置2](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置2.png "MAA配置2")

4.取消勾选“开机自启动MAA”，勾选“启动MAA后直接运行”和“启动MAA后自动开启模拟器”。配置自己模拟器所在的位置并根据实际情况填写“等待模拟器启动时间”（建议预留10s以防意外）。如果是多开用户，需要填写“附加命令”，具体填写值参见多开模拟器对应快捷方式路径（如“-v 1”）。

![MAA配置3](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置3.png "MAA配置3")

5.勾选“定时检查更新”、“自动下载更新包”和“自动安装更新包”

![MAA配置4](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/MAA配置4.png "MAA配置4")

## 下载AUTO_MAA软件包 [![](https://img.shields.io/github/downloads/DLmaster361/AUTO_MAA/total?color=66ccff)](https://github.com/DLmaster361/AUTO_MAA/releases)

GitHub下载地址    [GitHub下载](https://github.com/DLmaster361/AUTO_MAA/releases)

## 配置用户信息与相关参数

**第一次启动**

双击启动`manage.exe`，输入MAA所在文件夹路径并回车（注意使用斜杠的种类，不要使用反斜杠）

![信息配置1](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置1.png "MAA配置1")

**添加用户**

输入“+”以开始添加用户。依次输入：

用户名：管理用户的惟一凭证

手机号码：允许隐去中间四位以“****”代替

代理天数：这个还要我解释吗？

密码：警告！密码功能暂未开发，输入的信息会以明文存储，有泄露风险，请勿使用。可以用无意义的字符串代替。由于忽略警告导致的信息泄露，本项目组概不负责

![信息配置2](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置2.png "MAA配置2")

**删除用户**

输入用户名+“-”以删除用户。格式：

```plaintext
用户名 -
```

![信息配置3](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置3.png "MAA配置3")

**配置用户状态**

启用代理：输入用户名+“y”以启用该用户的代理。格式：

```plaintext
用户名 y
```

![信息配置4](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置4.png "MAA配置4")

禁用代理：输入用户名+“n”以禁用该用户的代理。格式：

```plaintext
用户名 n
```

![信息配置5](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置5.png "MAA配置5")

**续期**

输入用户名+续期天数+“+”以延长该用户的代理天数。格式：

```plaintext
用户名 续期天数 +
```

![信息配置6](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置6.png "MAA配置6")

**修改刷取关卡**

输入用户名+关卡号+“~”以更改该用户的代理关卡。格式：

```plaintext
用户名 关卡号 ~
```

![信息配置7](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置7.png "MAA配置7")

特别的：

你可以自定义关卡号替换方案。程序会读取`gameid.txt`中的数据，依据此进行关卡号的替换，便于常用关卡的使用。`gameid.txt`在初始已经存储了一些常用资源本的替代方案。

![gameid](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/gameid.png "gameid")

**设置MAA路径**

输入“/”+新的MAA文件夹路径以修改MAA安装位置的配置。格式：

```plaintext
/新的MAA文件夹路径
```

注意：‘/’与路径间没有空格，路径同样不能使用反斜杠

![信息配置8](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置8.png "MAA配置8")

**设置启动时间**

添加启动时间：输入“:+”+时间以添加定时启动时间。格式：

```plaintext
:+小时:分钟
```

注意：所有输入间没有空格

![信息配置9](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置9.png "MAA配置9")

删除启动时间：输入“:-”+时间以删除定时启动时间。格式：

```plaintext
:-小时:分钟
```

注意：所有输入间没有空格

![信息配置10](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置10.png "MAA配置10")

**检索信息**

检索所有信息：`manage.exe`打开时会打印所有用户与配置信息。除此之外，你可以通过输入“all ?”以打印所有信息，如下：

```plaintext
all ?
```

![信息配置11](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置11.png "MAA配置11")

检索MAA路径：输入“maa ?”以检索MAA安装路径，如下：

```plaintext
maa ?
```

![信息配置12](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置12.png "MAA配置12")

检索启动时间：输入“time ?”以检索定时启动的时间，如下：

```plaintext
time ?
```

![信息配置13](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置13.png "MAA配置13")

检索指定用户：输入用户名+“?”以检索指定用户信息，如下：

```plaintext
用户名 ?
```

![信息配置14](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/信息配置14.png "MAA配置14")

## 运行代理

**直接运行**

双击`run.exe`直接运行 

**定时运行**

双击`AUTO_MAA.exe`打开，不要关闭。它会读取设定时间，在该时刻自动运行

注意：周一将自动进行剿灭代理

----------------------------------------------------------------------------------------------

欢迎加入，欢迎反馈bug

QQ群：没有

----------------------------------------------------------------------------------------------

如果喜欢本项目，可以打赏送作者一杯咖啡喵！

![打赏](https://github.com/DLmaster361/AUTO_MAA/blob/main/res/README/payid.png "打赏")

----------------------------------------------------------------------------------------------
## 贡献者

感谢以下贡献者对本项目做出的贡献

<a href="https://github.com/DLmaster361/AUTO_MAA/graphs/contributors">

  <img src="https://contrib.rocks/image?repo=DLmaster361/AUTO_MAA" />

</a>

![Alt](https://repobeats.axiom.co/api/embed/a24da575ebc375e58ec8d8a0d7fff6d26306d2fc.svg "Repobeats analytics image")

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=DLmaster361/AUTO_MAA&type=Date)](https://star-history.com/#DLmaster361/AUTO_MAA&Date)
