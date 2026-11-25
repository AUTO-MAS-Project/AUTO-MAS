import io
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from PIL import Image

from app.services.common.config_center import ConfigCenterClient, ConfigCenterError


@pytest.mark.asyncio
@pytest.mark.parametrize("file_id", [None, 42], ids=["first-upload", "new-version"])
@pytest.mark.parametrize(
    "default_image",
    [None, b"\x89PNG\r\n\x1a\n"],
    ids=["missing-default", "broken-image"],
)
async def test_theme_with_menu_icons_requires_valid_default(
    tmp_path, monkeypatch, file_id, default_image
):
    package = tmp_path / "theme.zip"
    image = io.BytesIO()
    Image.new("RGB", (24, 24)).save(image, format="PNG")
    menu_icons = {"home": "assets/home.png"}
    with ZipFile(package, "w") as archive:
        if default_image is not None:
            menu_icons["default"] = "assets/default.png"
            archive.writestr(menu_icons["default"], default_image)
        archive.writestr(
            "theme.json",
            json.dumps(
                {
                    "formatVersion": 1,
                    "id": "test-theme",
                    "preview": "assets/home.png",
                    "menuIcons": menu_icons,
                }
            ),
        )
        archive.writestr("assets/home.png", image.getvalue())

    client = ConfigCenterClient()
    request = AsyncMock(side_effect=AssertionError("不应向分享站发起请求"))
    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(client, "_require_token", lambda: "test-token")

    with pytest.raises(
        ConfigCenterError, match=r"menuIcons\.default|默认菜单图标无法解码"
    ) as error:
        await client.upload_appearance(
            zip_path=str(package),
            display_name="Test theme",
            description="",
            change_note="",
            file_id=file_id,
        )

    assert error.value.status_code == 400
    request.assert_not_awaited()
