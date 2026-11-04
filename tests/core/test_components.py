"""共享组件在不同导入顺序下保持唯一，启动模块不提前加载组件。"""

import pytest


@pytest.mark.asyncio
async def test_community_flow_excludes_concurrent_callers_and_releases_after_use():
    import asyncio

    from app.core import Community
    from app.tools.common.community.contracts import CommunitySignInProgressError

    async def enter() -> bool:
        try:
            async with Community.community_sign_flow():
                return True
        except CommunitySignInProgressError:
            return False

    async with Community.community_sign_flow():
        assert await asyncio.create_task(enter()) is False
    assert await asyncio.create_task(enter()) is True
