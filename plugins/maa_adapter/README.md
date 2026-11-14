<!-- auto-mas:i18n
{
  "display_name_i18n": {
    "zh_CN": "MAA 专项",
    "en": "MAA Adapter"
  },
  "description_i18n": {
    "zh_CN": "MAA 专项适配插件",
    "en": "MAA specialized script adapter"
  },
  "tags_i18n": {
    "zh_CN": [
      "专项适配",
      "明日方舟"
    ],
    "en": [
      "Script adapter",
      "Arknights"
    ]
  }
}
-->

# MAA 专项插件

以 `origin/dev` 的 `5b8dc3cea01ba4741f4d0b7029ec9ed1ad963e77` 为核对基准，全量承接 MAA 专项；包含配置窗口延迟退出保存修复。旧 `app/task/MAA`、宿主内置 MAA 配置类及内置注册已移除，不提供旧导入路径转发。

## 使用

源码工作区及 Runtime 源码目录发现本插件后，首次按随附插件声明启用；之后尊重插件中心的启用选择。
在托管列表正常新建 MAA，使用原有的托管、账号、养成和计划界面。旧托管、账号与计划的 UID 和配置保持不变。
不再提供“创建测试托管”的临时设置入口。

## 归属与运行

- `src/maa_adapter` 持有完整模型、专项 API、配置恢复、作业平台、更新、养成、日志观察与执行逻辑。
- `frontend` 持有编辑页、计划表、养成组件、专项组合函数、元数据及图标；当前由宿主前端构建收集入口，随桌面应用交付，Python wheel 不替换桌面渲染产物。
- `i18n` 持有 MAA 专属界面词条，公共词条仍使用 core。HTTP 路径和路由名保留原有公开契约，插件停用后专项 HTTP 路径随调用门排空后卸载。
- L2 持有托管锁、预下载会话与本次进程归属，停止前先确认安装停写和配置保存；L3 使用 `UserExpander`，L4 使用 `ModeWorker`，用户锁内完成恢复。
- 自动代理继续复用宿主的模拟器、通知、历史及社区公共服务；没有创建游戏适配插件。
- 统一下载中心提供预下载文件。安装编排整体移入 L2 仍按已确认的后续任务推进；当前复用宿主公共安装执行及恢复入口，不保留旧 MAA manager。

## 源码结构

```text
src/maa_adapter/
  plugin.py          插件声明、启用预热与公共服务接线
  config/            托管、用户、计划、插件缓存及配置迁移
  tasks/             L3/L4 编排、配置入口、查看入口和共用 GUI 会话
  native/            MAA 配置下发、预设、快照、恢复与基建设置
  updates/           本体、资源、游戏更新及预下载需求
  cultivate/         养成、库存、作业来源和编辑业务
  stages/            关卡解释、缓存访问及活动时段判断
  logs/              MAA 输出解析、统计和截图
  api/               按业务拆分的 HTTP 端点及端点专用模型
  notifications.py   MAA 专属报告内容，投递仍直接使用宿主 Notify
frontend/
  entry.ts           唯一前端能力声明
  plan/              计划表数据协调
  script/            托管编辑
  user/              账号编辑与养成组件
  composables/       插件 API 与编辑会话调用
```

配置和查看分别由 `tasks/config_session.py`、`tasks/view_session.py` 提供入口，
两者共享 `tasks/session.py` 的 GUI 运行与保存确认能力，查看不继承配置入口。
任务执行顺序仍集中在 `tasks/manager.py` 与 `tasks/auto_proxy.py`，
配置转换、养成任务构造和日志解析通过明确调用接入，不引入任务 mixin。

## 关卡数据归属

关卡号、资源关卡和材料名称全部由插件持有。启用时通过插件背景任务组首次获取
MAA 官方资源，以 `MaaPluginConfig.stage_cache` 保存正文、ETag 和检查时间，
由宿主配置框架统一持久化到 `config/plugins/maa_adapter.yaml`。
刷新失败保留已有缓存，停用会结束刷新任务，卸载按插件配置删除语义清理缓存。

插件注册 `/api/plugin/maa_adapter/stages/options` 和 `/stages/overview`，
账号及计划表的主备关卡字段均以 `select(endpoint=...)` 声明选项接口。
当前前端直接使用生成的插件 API 客户端，保留现有编辑器和自定义关卡；
没有接入动态 UI。宿主不再保存关卡缓存，也不保留旧关卡号接口。

## 验证入口

```powershell
uv run --no-sync python -m pytest tests/task -k maa plugins/maa_adapter/tests -q
```

浏览器通过 `frontend/e2e/run.mjs` 运行 `@plugins|@maa-plan-display|@maa-update`。
进程、网络及设备边界采用隔离替身的检查不代表真实 MAA、游戏或模拟器验收。
