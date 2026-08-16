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

---

### 根级设置

新版 MAA（PR #17392 后）将原本 `gui.json` 中的扁平字段迁移至 `gui.new.json` 的嵌套结构，以下是 AUTO-MAS 当前写入的字段。

#### Gui 全局设置

| 字段              | 类型/典型值 | 释义                          | 旧版 gui.json 字段            |
| ----------------- | ----------- | ----------------------------- | ----------------------------- |
| Localization      | "zh-cn"     | 语言                          | GUI.Localization              |
| UseTray           | bool        | 显示托盘图标                  | GUI.UseTray                   |
| MinimizeToTray    | bool        | 最小化时隐藏至托盘            | GUI.MinimizeToTray            |
| MinimizeOnStartup | bool        | 启动 MAA 后直接最小化         | Start.MinimizeDirectly        |

#### Update 更新设置

| 字段                       | 类型/常用值 | 释义           | 旧版 gui.json 字段                          |
| -------------------------- | ----------- | -------------- | ------------------------------------------- |
| CheckOnSchedule            | bool        | 定时检查更新   | VersionUpdate.ScheduledUpdateCheck          |
| AutoDownloadUpdatePackage  | bool        | 自动下载更新包 | VersionUpdate.AutoDownloadUpdatePackage     |
| AutoInstallUpdatePackage   | bool        | 自动安装更新包 | VersionUpdate.AutoInstallUpdatePackage      |

#### Timers 定时设置

| 字段 | 类型/常用值 | 释义         |
| ---- | ----------- | ------------ |
| List | Timer[]     | 定时器列表   |

List 中每项：

| 字段      | 类型/常用值 | 释义     |
| --------- | ----------- | -------- |
| IsEnabled | bool        | 是否启用 |

#### Configurations.Default.Gui 单配置设置

**ConnectSettings**

| 字段    | 类型/常用值       | 释义     | 旧版 gui.json 字段  |
| ------- | ----------------- | -------- | ------------------- |
| Address | 127.0.0.1:16384   | 连接地址 | Connect.Address     |

**StartUpSettings**

| 字段          | 类型/常用值 | 释义                        | 旧版 gui.json 字段            |
| ------------- | ----------- | --------------------------- | ----------------------------- |
| RunDirectly   | bool        | 启动 MAA 后直接运行         | Start.RunDirectly             |
| StartEmulator | bool        | 启动 MAA 后自动开启模拟器   | Start.OpenEmulatorAfterLaunch |

**RuntimeSettings**

| 字段       | 类型/常用值 | 释义                     | 旧版 gui.json 字段  |
| ---------- | ----------- | ------------------------ | ------------------- |
| StartGame  | bool        | 是否启动客户端           | Start.StartGame     |
| ClientType | int (0~5)   | 客户端类型（枚举整数）   | Start.ClientType    |

ClientType 枚举值：Official=0, Bilibili=1, YoStarEN=2, YoStarJP=3, YoStarKR=4, txwy=5

**PostActions**

完成后动作，`[Flags]` 枚举存储为整数：

| 整数 | 位组合 | 释义 |
| ---- | ------ | ---- |
| 0    | None   | 无动作 |
| 8    | ExitSelf | 完成后退出MAA |
| 9    | ExitSelf \| ExitArknights | 完成后退出MAA和游戏 |
| 12   | ExitSelf \| ExitEmulator | 完成后退出MAA和模拟器 |