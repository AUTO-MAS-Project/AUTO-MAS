## gui.json
| 字段                                    | 类型   | 类型 / 典型值                                                | 释义                                                         |
| :-------------------------------------- | ------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| MainFunction.PostActions                | 子配置 | "8"<br/>"9"<br/>"12"                                         | 完成后退出MAA<br/>完成后退出MAA和游戏<br/>完成后退出MAA和模拟器 |
| Timer.Timer1                            | 全局   | bool                                                         | 定时设置 - 1                                                 |
| Connect.AdbPath                         | 子配置 | 127.0.0.1:16384                                              | ADB 路径                                                     |
| Connect.Address                         | 子配置 | path                                                         | 连接地址                                                     |
| VersionUpdate.ScheduledUpdateCheck      | 全局   | bool                                                         | 定时检查更新                                                 |
| VersionUpdate.AutoDownloadUpdatePackage | 全局   | bool                                                         | 自动下载更新包                                               |
| VersionUpdate.AutoInstallUpdatePackage  | 全局   | bool                                                         | 自动安装更新包                                               |
| Start.MinimizeDirectly                  | 全局   | bool                                                         | 启动 MAA 后直接最小化                                        |
| Start.RunDirectly                       | 子配置 | bool                                                         | 启动 MAA 后直接运行                                          |
| Start.OpenEmulatorAfterLaunch           | 全局   | bool                                                         | 启动 MAA 后自动开启模拟器                                    |
| GUI.Localization                        | 全局   | "zh-cn"                                                      | 语言                                                         |
| GUI.UseTray                             | 全局   | bool                                                         | 显示托盘图标                                                 |
| GUI.MinimizeToTray                      | 全局   | bool                                                         | 最小化时隐藏至托盘                                           |
| VersionUpdate.package                   | 全局   | FileName                                                     | 更新包标识                                                   |
| Start.ClientType                        | 子配置 | "Official"<br />"Bilibili"<br />"YoStarEN"<br />"YoStarJP"<br />"YoStarKR"<br />"txwy" | 官服<br />B服<br />外服<br />日服<br />韩服<br />繁中服      |
| Start.StartGame                         | 子配置 | bool                                                         | 是否启动客户端                                               |
| Start.AutoRestartOnDrop                 | 子配置 | bool                                                         | 游戏掉线时自动重连                                           |

## gui.new.json

### 基础字段

| 字段     | 类型/常用值 | 释义       |
| -------- | ----------- | ---------- |
| $type    | < T >Task   | 识别字段   |
| Name     | str         | 任务显示名 |
| IsEnable | bool        | 启用       |
| TaskType | < T >       | 任务类型   |

### 开始唤醒

> StartUp

| 字段        | 类型/常用值       | 释义     |
| ----------- | ----------------- | -------- |
| AccountName | 手机号、B站用户名 | 账号切换 |

### 理智作战

> Fight

| 字段                  | 类型/常用值                                                  | 释义                                                 |
| --------------------- | ------------------------------------------------------------ | ---------------------------------------------------- |
| UseMedicine           | bool                                                         | 吃理智药                                             |
| MedicineCount         | int                                                          | 吃理智药数量                                         |
| EnableTimesLimit      | bool                                                         | 指定次数                                             |
| TimesLimit            | int                                                          | 指定次数数量                                         |
| EnableTargetDrop      | bool                                                         | 指定材料                                             |
| Series                | int                                                          | 连战次数                                             |
| StagePlan             | ["", "1-7"]                                                  | 关卡列表                                             |
| UseCustomAnnihilation | bool                                                         | 启用自定义剿灭关卡                                   |
| AnnihilationStage     | "Annihilation"<br />"Chernobog@Annihilation"<br />"LungmenOutskirts@Annihilation"<br />"LungmenDowntown@Annihilation" | 当期剿灭<br />切尔诺伯格<br />龙门外环<br />龙门市区 |
| IsDrGrandet           | bool                                                         | 博朗台模式                                           |
| IsStageManually       | bool                                                         | 手动输入关卡名                                       |
| UseOptionalStage      | bool                                                         | 使用备选关卡                                         |
| UseStoneAllowSave     | bool                                                         | 允许吃源石保持状态                                   |
| UseExpiringMedicine   | bool                                                         | 无限吃48小时内过期的理智药                           |
| HideUnavailableStage  | bool                                                         | 隐藏当日不开放关卡                                   |
| HideSeries            | bool                                                         | 隐藏连战次数                                         |
| UseWeeklySchedule     | bool                                                         | 启用周计划                                           |
| WeeklySchedule        | { "day": bool }                                              | 周计划                                               |

### 基建换班

> Infrast

| 字段        | 类型/常用值                                                  | 释义                                       |
| ----------- | ------------------------------------------------------------ | ------------------------------------------ |
| Mode        | "Normal"<br />"Rotation"<br />"Custom"                       | 常规模式<br />队列轮换<br />自定义基建配置 |
| Filename    | path                                                         | 自定义基建配置文件地址                     |
| InfrastPlan | [ {<br/>       "Index": 0,<br/>       "Name": "第01班",<br/>       "Description": "第01班的描述",<br/>       "DescriptionPost": "第01班完成后的描述",<br/>       "Period": [ [ "19:05:00", "19:05:00" ] ]<br/>} ] | 自定义基建配置文件信息                     |
| PlanSelect  | int                                                          | 自定义基建班次索引号                       |

### 自动公招

> Recruit

| 字段 | 类型/常用值 | 释义 |
| ---- | ----------- | ---- |
|      |             |      |

### 信用收支

> Mall

| 字段 | 类型/常用值 | 释义 |
| ---- | ----------- | ---- |
|      |             |      |

### 领取奖励

> Award

| 字段 | 类型/常用值 | 释义 |
| ---- | ----------- | ---- |
|      |             |      |

### 自动肉鸽

> Roguelike

| 字段 | 类型/常用值 | 释义 |
| ---- | ----------- | ---- |
|      |             |      |

### 生息演算

> Reclamation

| 字段 | 类型/常用值 | 释义 |
| ---- | ----------- | ---- |
|      |             |      |










