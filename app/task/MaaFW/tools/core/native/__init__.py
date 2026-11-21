"""原生库识别（将来的库 ``maafw_native``）：只看项目目录，认项目自带的 MaaFramework 原生库。

没有状态，只读项目目录里的 DLL、dist-info、requirements：

- ``project_runtime``：项目原生库目录在哪（候选搜索、取最高版本）、读原生库版本、能否在本机
  加载、缺依赖、完整与损坏、架构不匹配的描述、项目自带 maafw 版本探测；
- ``pe``：PE 架构与导入表解析（只读文件头，不映射不执行）；
- ``requirement``：项目对 maafw 的版本需求解析（自带原生库的实测版本优先于声明）；
- ``versions``：maafw 版本与 requirement 的规范化；
- ``architecture``：本机架构的唯一判定来源；
- ``requirements_file``：按 pip 的规则读 ``requirements.txt``；
- ``offline_dependencies``：项目自带的离线依赖材料（本库自己不用，agent 环境与项目更新共用）；
- ``layout``：``data/mfw``、``.payloads``、``.pycache`` 这类目录布局常量。

依赖方向：别的包（runner / agent_env / runtime_pool / project_update / 宿主接缝）导入本库，
本库**不导入**它们，只用标准库与 ``packaging``。worker 子进程也导入本库，所以同样不得
碰宿主模块。这里不做急切的 re-export，按子模块导入。
"""
