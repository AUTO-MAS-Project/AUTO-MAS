from auto_mas_core.host.services_common_update import (
    transport as _service_update_transport,
)
from auto_mas_core.host.utils import get_logger

logger = get_logger("MAA")


async def query_mirror_cdk(
    cdk: str,
) -> tuple[_service_update_transport.MirrorCdkStatus, bool]:
    """校验编辑草稿，并返回是否使用全局凭据；查询失败沿用错误状态。"""
    from maa_adapter.updates.credentials import query_takeover_cdk

    using_global = not cdk.strip()
    try:
        result = await query_takeover_cdk(cdk)
    except Exception as error:
        logger.warning(f"脚本 Mirror 酱 CDK 查询失败: {type(error).__name__}")
        result = _service_update_transport.MirrorCdkStatus(status="error")
    return result, using_global
