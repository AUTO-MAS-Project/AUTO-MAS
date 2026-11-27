import pytest
from pydantic import ValidationError

from app.models.config import HSRConfig
from app.utils.common import io as _utils_io


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(False, "Off"), (True, "BeforeRun"), ("Off", "Off"), ("AfterRun", "AfterRun")],
)
def test_hsr_auto_update_mode_accepts_yaml_booleans(raw, expected):
    config = HSRConfig(Update={"AutoUpdateMode": raw})
    assert config.Update.AutoUpdateMode == expected


def test_hsr_auto_update_mode_still_rejects_unknown_values():
    with pytest.raises(ValidationError):
        HSRConfig(Update={"AutoUpdateMode": "Sometimes"})


def test_hsr_auto_update_mode_unquoted_yaml_off(tmp_path):
    path = tmp_path / "scripts.yaml"
    path.write_text("Update:\n  AutoUpdateMode: Off\n", encoding="utf-8")
    payload = _utils_io.read_dict_file(path)
    assert payload["Update"]["AutoUpdateMode"] is False
    config = HSRConfig(**payload)
    assert config.Update.AutoUpdateMode == "Off"
