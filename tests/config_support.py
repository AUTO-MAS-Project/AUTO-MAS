"""配置框架迁移期间的本地验证夹具；不进入实现提交。"""

from pathlib import Path

from app.config import NodeState, config_manager


async def activate_config(config, path: Path | None = None):
    if path is not None:
        await config_manager.flush()
        for root in list(config_manager.iter_persist_roots()):
            if root.persist_path == path:
                config_manager.unregister_root(root)
        config_manager.register_root(config, path)
    if config.activation_state == NodeState.INACTIVE:
        await config.activate()
    await config_manager.flush()
    return config


def group_view(config, group):
    class Group:
        def __getattr__(self, name):
            return config.get(group, name)
    return Group()
