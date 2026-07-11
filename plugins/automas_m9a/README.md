# automas-m9a

M9A 专项插件组合包（meta-package）。安装此包会自动拉入 M9A 全部运行所需的 8 个插件包。

## 安装

```bash
pip install automas-m9a
```

## 包含的插件包

| 包名 | 职责 |
| --- | --- |
| automas-maafw-interface | MaaFW ProjectInterface 解析 |
| automas-maafw-project-update | MaaFW 项目资源升级 |
| automas-maafw-agent-env | MaaFW agent 命令计划与环境准备 |
| automas-maafw-runner | MaaFW 隔离运行服务（含 maafw 运行依赖） |
| automas-maafw-controller-adb | ADB controller |
| automas-maafw-controller-win32 | Win32 controller |
| automas-script-maafw | MaaFW 脚本适配插件 |
| automas-script-maafw-pack-m9a | M9A project pack 声明 |

## 说明

此包是纯依赖聚合包，不包含任何 Python 代码或插件入口点。安装后，8 个插件包会被自动安装到 `plugins/pypi/site-packages`，插件加载器会自动发现并注册它们。
