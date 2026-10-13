"""去广告开关：基类默认不做事 + MuMu 宿主机侧占位双向生效。

开关的扇出（``GameManager.on_block_ad``）在这里只验品牌侧的那一半 ——
信号接线本身属于 ``Config.init_domain_configs``，需要整套引导，不在单测面内。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from app.config import ConfigCollection

_PLUGINS = Path(__file__).resolve().parents[3] / "plugins"
for _p in (
    str(_PLUGINS / "auto_mas_core" / "src"),
    str(_PLUGINS / "mumu_adapter" / "src"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mumu_adapter.control as control_mod  # noqa: E402
from mumu_adapter.config import MuMuGame  # noqa: E402
from mumu_adapter.control import MuMuControl  # noqa: E402


async def _ctrl() -> MuMuControl:
    games: ConfigCollection[MuMuGame] = ConfigCollection(
        [MuMuGame], name=f"games_{uuid4().hex}"
    )
    await games.activate()
    uid = games.add(MuMuGame)
    await games.commit()
    return MuMuControl(config=games[uid])


def test_placeholder_replaces_cache_dir_and_reverts(tmp_path: Path) -> None:
    """开着：目录换成同名空文件；关着：空文件删掉，目录留给 MuMu 自己重建。"""
    paths = (tmp_path / "a/data/startupImage", tmp_path / "b/data/startupImage")
    for p in paths:
        p.mkdir(parents=True)
        (p / "ad.png").write_bytes(b"x")  # 缓存里已经有图
    async def run() -> None:
        # control 是 ``from .constants import`` 直接绑名，改它的模块属性才生效
        old = control_mod._SPLASH_ADS_PATHS
        control_mod._SPLASH_ADS_PATHS = paths
        try:
            ctrl = await _ctrl()

            await ctrl.set_block_ad(True)
            for p in paths:
                assert p.is_file(), "目录须被同名空文件顶掉"
                assert p.stat().st_size == 0

            await ctrl.set_block_ad(False)
            for p in paths:
                assert not p.exists(), "只删占位文件，目录不替 MuMu 重建"
        finally:
            control_mod._SPLASH_ADS_PATHS = old

    asyncio.run(run())


def test_placeholder_is_idempotent(tmp_path: Path) -> None:
    """已占位再开一次不报错也不重建 —— 开关可能被反复拨。"""
    path = tmp_path / "data/startupImage"
    path.parent.mkdir(parents=True)

    async def run() -> None:
        old = control_mod._SPLASH_ADS_PATHS
        control_mod._SPLASH_ADS_PATHS = (path,)
        try:
            ctrl = await _ctrl()
            await ctrl.set_block_ad(True)
            await ctrl.set_block_ad(True)
            assert path.is_file()
            await ctrl.set_block_ad(False)
            await ctrl.set_block_ad(False)
            assert not path.exists()
        finally:
            control_mod._SPLASH_ADS_PATHS = old

    asyncio.run(run())


def test_placeholder_paths_cover_program_ads() -> None:
    """占位集必须含 ``ProgramAds`` —— 只占 ``startupImage`` 拦不住弹窗。

    上面那几个用例都把 ``_SPLASH_ADS_PATHS`` 换成 tmp_path 下的桩，
    真实路径集是谁一个断言都没有：漏掉某类缓存，开关照样"生效"。
    ``startupImage`` 实测会被实例启动时删掉重建（``emulator2/master_mode:308``），
    真正拦住小程序弹窗的是常驻服务读的 ``ProgramAds``，故这条单独钉住。
    12.0 与 6 两套安装路径各要一份：装哪个版本不确定。
    """
    from mumu_adapter import control as control_mod

    tails = {"/".join(p.parts[-3:]) for p in control_mod._SPLASH_ADS_PATHS}
    for ver in ("MuMuPlayer-12.0", "MuMuPlayer"):
        for kind in ("startupImage", "ProgramAds"):
            assert f"{ver}/data/{kind}" in tails, f"占位集缺 {ver}/data/{kind}: {tails}"


def test_base_default_is_noop() -> None:
    """没有宿主机侧广告处理的品牌不实现该钩子，基类默认什么都不做。"""
    from app.plugin.base.game import GameControl

    async def run() -> None:
        # 不经子类：直接拿基类未重写的实现调，确认既不抛也无副作用
        await GameControl.set_block_ad(object(), True)  # type: ignore[arg-type]

    asyncio.run(run())
