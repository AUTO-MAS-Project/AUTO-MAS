"""插件声明的管线配置，不携带运行对象、监控器或模块搜索路径。"""

from pydantic import BaseModel

from .contracts import FileInput, WorkerFactorySpec
from .simple import SimpleFlowDeclaration


class PluginFlowDeclaration(BaseModel, frozen=True):
    rules: SimpleFlowDeclaration = SimpleFlowDeclaration()
    use_mas_log: bool = True
    accept_push: bool = False
    file: FileInput | None = None
    source: WorkerFactorySpec | None = None
    sink: WorkerFactorySpec | None = None
