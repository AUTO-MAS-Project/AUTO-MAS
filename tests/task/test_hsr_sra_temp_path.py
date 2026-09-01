"""HSR SRA 临时配置目录改用 `data/` 后的路径与旧目录迁移回归

同一 runtime 目录改造：`_sra_temp_path` 原先落在 `<app-root>/runtime/hsr/
sra-config` 下，改存受保护的 `data/hsr/sra-config`；用户机器上的 sra-config
是运行期状态（尤其是已保存的临时配置），首次访问新路径时要整体搬迁过去。
"""

from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.core import Config
from app.task.HSR.tools.sra_runtime import _sra_temp_path


def test_new_path_is_used_under_data_dir(tmp_path: Path, monkeypatch) -> None:
    """无历史目录时，临时配置路径必须落在 `data/hsr/sra-config` 下，不再是 `runtime/`。"""

    monkeypatch.setattr(Config, "config_path", tmp_path / "config")

    result = _sra_temp_path("script-uid", "user-uid", "Daily")

    assert result == (
        tmp_path / "data" / "hsr" / "sra-config" / "script-uid" / "user-uid" / "Daily.json"
    )
    assert not (tmp_path / "runtime").exists()


def test_legacy_runtime_dir_is_migrated_on_first_access(
    tmp_path: Path, monkeypatch
) -> None:
    """旧 `runtime/hsr/sra-config` 有历史配置时，首次访问须整体搬到 `data/` 下。"""

    monkeypatch.setattr(Config, "config_path", tmp_path / "config")
    legacy_root = tmp_path / "runtime" / "hsr" / "sra-config"
    legacy_user_dir = legacy_root / "script-uid" / "user-uid"
    legacy_user_dir.mkdir(parents=True)
    (legacy_user_dir / "Daily.json").write_text("{}", encoding="utf-8")

    result = _sra_temp_path("script-uid", "user-uid", "Daily")

    new_root = tmp_path / "data" / "hsr" / "sra-config"
    assert result == new_root / "script-uid" / "user-uid" / "Daily.json"
    assert result.read_text(encoding="utf-8") == "{}"
    assert not legacy_root.exists()
