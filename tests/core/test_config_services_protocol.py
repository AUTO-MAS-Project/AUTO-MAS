from app.core.config import AppConfig, AppConfigServices, Config

_SERVICE_SURFACE = {
    "restore_service",
    "list_config_backups",
    "ensure_config_backup",
    "restore_config_backup",
    "get_config_backup_preview",
    "get_config_backup_file",
    "add_user",
}


def test_app_config_satisfies_services_protocol() -> None:
    """消费面契约：单例结构化满足服务协议，作为 api 层注入面可用。"""

    assert isinstance(Config, AppConfigServices)


def test_services_protocol_surface_stays_declared() -> None:
    """协议声明面即契约清单：缩水（方法被移出协议）立即暴露。"""

    for name in _SERVICE_SURFACE:
        assert callable(getattr(AppConfig, name, None)), name
