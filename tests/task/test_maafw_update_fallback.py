"""真实差量构建失败时只在登记前回退；取消与环境错误保持原语义。"""

import hashlib
import io
import json
import threading
import zipfile
from pathlib import Path

import httpx
import pytest

from app.task.MaaFW.tools.core.interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.project_update import payloads, transport, updater
from app.task.MaaFW.tools.core.project_update.blob_store import RuntimeBlobStore
from app.task.MaaFW.tools.core.project_update.projection import PROJECTION_REVISION


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["baseline", "full_is_delta", "cancel", "disk", "metadata_disk", "registered"],
)
async def test_delta_fallback_uses_real_package_validation(
    tmp_path, monkeypatch, failure
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AUTO_MAS_MAAFW_FORCE_FULL_PACKAGE", raising=False)
    monkeypatch.setattr(updater, "DEFAULT_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(transport, "DEFAULT_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(updater, "DEFAULT_OPERATION_ROOT", tmp_path / "operations")
    interface = {
        "interface_version": 2,
        "name": "Audit",
        "version": "1.0",
        "mirrorchyan_rid": "Audit",
        "resource": [{"name": "Default", "path": ["resource"]}],
        "task": [],
    }
    source = tmp_path / "package"
    (source / "resource").mkdir(parents=True)
    (source / "interface.json").write_text(json.dumps(interface))
    (source / "resource/data.json").write_text("old")
    empty = tmp_path / "empty"
    empty.mkdir()
    staging = tmp_path / "initial"
    built = payloads.build_from_package({}, empty, source, source, staging)
    root = tmp_path / "payloads"
    lineage = payloads.lineage_key(interface)
    initial = payloads.register(
        root,
        staging,
        lineage=lineage,
        channel="stable",
        source={"kind": "update"},
        by="audit",
        version="1.0",
        origins=built.origins,
        projection_revision=PROJECTION_REVISION,
    )
    target = payloads.PayloadTarget(
        root=root,
        lineage=lineage,
        payload_id=initial.payload_id,
        channel="stable",
        by="audit",
        staging_root=tmp_path / "staging",
        blob_store=RuntimeBlobStore(tmp_path / "blobs"),
    )
    before = {
        p.relative_to(target.directory()): p.read_bytes()
        for p in target.directory().rglob("*")
        if p.is_file()
    }
    new_interface = {**interface, "version": "2.0"}
    packages = {}
    for kind in ("delta", "full"):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            archive.writestr("interface.json", json.dumps(new_interface))
            archive.writestr("resource/data.json", "new")
            if kind == "delta":
                archive.writestr(
                    "changes.json",
                    json.dumps(
                        {
                            "packageType": "delta",
                            "baseVersion": "1.0",
                            "baseFingerprint": "0" * 64
                            if failure in {"baseline", "full_is_delta"}
                            else target.manifest()["fingerprint"],
                            "targetVersion": "2.0",
                        }
                    ),
                )
        packages[kind] = content.getvalue()
    downloads = []
    authorizations = []
    cancel = threading.Event()

    def respond(request):
        if request.url.host == "mirrorchyan.com":
            kind = "delta" if "current_version" in request.url.params else "full"
            if "cdk" in request.url.params:
                authorizations.append(kind)
                assert len(authorizations) <= 2, "全量回退只允许一次"
            if failure == "full_is_delta":
                kind = "delta"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "version_name": "2.0",
                        "url": f"https://example.com/{kind}.zip",
                        "update_type": "incremental" if kind == "delta" else "full",
                        "sha256": hashlib.sha256(packages[kind]).hexdigest(),
                        "file_size": len(packages[kind]),
                    },
                },
            )
        kind = request.url.path.split("/")[-1].removesuffix(".zip")
        assert kind in packages
        downloads.append(kind)
        # 请求全量时旧载荷仍完整，尚未登记任何新版本。
        if kind == "full":
            assert payloads.latest(root, lineage, "stable")["id"] == initial.payload_id
            assert all(
                (target.directory() / rel).read_bytes() == data
                for rel, data in before.items()
            )
        if failure == "cancel":
            cancel.set()
        return httpx.Response(200, content=packages[kind])

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    if failure == "metadata_disk":
        read_text = Path.read_text

        def read(path, *args, **kwargs):
            if path.name == "changes.json":
                raise OSError("metadata disk unavailable")
            return read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", read)

    def validate(_):
        if failure == "disk":
            raise OSError("disk unavailable")
        return True

    async def registered(_):
        if failure == "registered":
            raise updater.UpdateApplyError("registration callback failed")

    async def run():
        return await updater.update_maafw_project_if_needed(
            target.directory(),
            MaaFWInterface.model_validate(interface),
            payload=target,
            mirror_cdk="test",
            source_config={
                "source": "MirrorChyan",
                "package_mode": "incremental",
                "project_shell_hint": "MXU",
            },
            cancel_event=cancel,
            post_validate=validate,
            after_register=registered,
        )

    if failure == "baseline":
        result = await run()
        assert result.updated
        assert downloads == ["delta", "full"]
        assert authorizations == ["delta", "full"]
        latest = payloads.latest(root, lineage, "stable")
        assert latest["version"] == "2.0"
        directory = payloads.payload_dir(root, lineage, latest["id"])
        assert (directory / "resource/data.json").read_text() == "new"
    elif failure == "registered":
        result = await run()
        assert result.updated
        assert downloads == ["delta"]
        assert authorizations == ["delta"]
        assert payloads.latest(root, lineage, "stable")["version"] == "2.0"
    else:
        with pytest.raises(updater.MaaFWProjectUpdateError) as caught:
            await run()
        assert downloads == ["delta"]
        assert authorizations == (
            ["delta", "full"] if failure == "full_is_delta" else ["delta"]
        )
        assert caught.value.cancelled is (failure == "cancel")
        assert payloads.latest(root, lineage, "stable")["version"] == "1.0"
    assert all(
        (target.directory() / rel).read_bytes() == data for rel, data in before.items()
    )
