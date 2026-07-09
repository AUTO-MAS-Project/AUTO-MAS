# AUTO-MAS 游戏中心插件

游戏中心系统插件：统一管理 PC / 模拟器游戏的版本检查、下载安装、启动与关闭。

- 以 `game_center` 服务名发布能力，`app/api/game_center.py` 与其他插件通过
  `PluginManager.service.get("game_center")` 调用。
- 暴露给其他插件的核心能力：`install`（更新游戏）、`launch`（启动游戏）、
  `close`（关闭游戏）；安卓模拟器游戏会先自动启动关联模拟器再执行更新/启动
  （仅支持 MuMu / 雷电）。
- 其他插件可通过 `register_provider` 注册自定义游戏 provider。
- 核心域逻辑位于主程序 `app/core/game_center`，本插件为服务与页面接入层。
