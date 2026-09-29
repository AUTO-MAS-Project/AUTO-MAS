"""发布工作流的 Git/GitHub 编排；放在 .github 内以便独立同步到 main。"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request


def run(*args, input=None):
    return subprocess.run(
        args,
        input=input,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def git(*args):
    return run("git", *args)


def output(**values):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def load_changelog(path):
    spec = importlib.util.spec_from_file_location("changelog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GitHub:
    def __init__(self):
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GH_TOKEN"]

    def request(self, path, method="GET", data=None, missing=False):
        url = (
            path
            if path.startswith("https://")
            else f"https://api.github.com/repos/{self.repo}/{path}"
        )
        raw = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=raw,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise

    def asset_json(self, asset):
        req = urllib.request.Request(
            asset["url"],
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/octet-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)

    def nightly(self):
        # 包含草稿：失败上传后的 dev 草稿仍需识别和清理。
        for page in range(1, 101):
            releases = self.request(f"releases?per_page=100&page={page}")
            for release in releases:
                if release["tag_name"] == "dev":
                    return release
            if len(releases) < 100:
                return None
        raise RuntimeError("release pagination exceeded")


def completed_nightly(api, release, sha):
    if not release or release["draft"] or not release["prerelease"]:
        return False
    assets = {asset["name"]: asset for asset in release["assets"]}
    metadata = assets.get("nightly-build.json")
    if not metadata or metadata["state"] != "uploaded":
        return False
    try:
        manifest = api.asset_json(metadata)
    except (ValueError, UnicodeError):
        return False
    if (
        not isinstance(manifest, dict)
        or manifest.get("source_sha") != sha
        or manifest.get("status") != "complete"
    ):
        return False
    expected = manifest.get("assets", {})
    if (
        not isinstance(expected, dict)
        or len(expected) != 2
        or not any(n.startswith("AUTO-MAS-Setup-") for n in expected)
    ):
        return False
    for name, info in expected.items():
        if (
            not isinstance(info, dict)
            or not isinstance(info.get("size"), int)
            or not re.fullmatch(r"[a-f0-9]{64}", info.get("sha256", ""))
        ):
            return False
        asset = assets.get(name)
        if not asset or asset["state"] != "uploaded" or asset["size"] != info["size"]:
            return False
        if asset.get("digest") and asset["digest"] != "sha256:" + info["sha256"]:
            return False
    tag = api.request("git/ref/tags/dev", missing=True)
    return bool(
        tag and tag["object"]["type"] == "commit" and tag["object"]["sha"] == sha
    )


def nightly_check(args):
    sha = git("rev-parse", "HEAD")
    api = GitHub()
    previous = api.nightly()
    # 在任何删除前持久化；它随后与安装包一起进入 Actions Artifact。
    Path(args.state).write_text(
        json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    skip = completed_nightly(api, previous, sha)
    output(source_sha=sha, build=str(not skip).lower())


def nightly_version(args):
    module = load_changelog(args.changelog)
    version = json.loads(module.VERSION_JSON_PATH.read_text(encoding="utf-8"))[
        "version"
    ]
    key = module.version_key(version)
    if key is None or not re.fullmatch(r"[1-9][0-9]*", args.number):
        raise ValueError("invalid nightly version source or run number")
    target = f"v{key[0]}.{key[1]}.{key[2]}-alpha.{args.number}"
    for path, pattern in (
        (module.PACKAGE_JSON_PATH, module.PACKAGE_JSON_VERSION),
        (module.APP_CONFIG_PATH, module.APP_CONFIG_VERSION),
        (module.PYPROJECT_PATH, module.PYPROJECT_VERSION),
        (module.UV_LOCK_PATH, module.UV_LOCK_VERSION),
    ):
        # Electron package 使用 SemVer；Python 和 uv.lock 使用 PEP 440。
        value = (
            module.to_pep440(target)
            if path in (module.PYPROJECT_PATH, module.UV_LOCK_PATH)
            else target
        )
        if path == module.PACKAGE_JSON_PATH:
            value = target.removeprefix("v")
        path.write_text(
            module.substitute_once(module.read_text(path), pattern, value, str(path)),
            encoding="utf-8",
        )
    payload = json.loads(module.VERSION_JSON_PATH.read_text(encoding="utf-8"))
    payload["version"] = target
    module.VERSION_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    windows_version = f"{key[0]}.{key[1]}.{key[2]}.0"
    package = json.loads(module.PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    package.setdefault("build", {})["buildVersion"] = windows_version
    module.PACKAGE_JSON_PATH.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output(version=target, windows_version=windows_version)


def nightly_publish(args):
    api = GitHub()
    directory = Path(args.artifacts)
    source = json.loads(
        (directory / "build-source.json").read_text(encoding="utf-8-sig")
    )
    if source["source_sha"] != args.sha or source["version"] != args.version:
        raise ValueError("artifact source and requested release do not match")
    if not re.fullmatch(r"[a-f0-9]{40}", args.sha) or not re.fullmatch(
        r"v\d+\.\d+\.\d+-alpha\.\d+", args.version
    ):
        raise ValueError("invalid nightly release identity")
    files = sorted(directory.glob("AUTO-MAS-*-x64.zip"))
    if len(files) != 2 or not any(p.name.startswith("AUTO-MAS-Setup-") for p in files):
        raise ValueError("nightly requires installer and portable packages")
    manifest = {
        "status": "complete",
        "source_sha": args.sha,
        "version": args.version,
        "run_id": os.environ["GITHUB_RUN_ID"],
        "assets": {
            p.name: {
                "size": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in files
        },
    }
    metadata = directory / "nightly-build.json"
    previous = api.nightly()
    if previous:
        if previous.get("immutable"):
            raise RuntimeError(
                "dev release is immutable; maintainer must disable nightly immutability"
            )
        api.request(f"releases/{previous['id']}", "DELETE")
    if api.request("git/ref/tags/dev", missing=True):
        api.request("git/refs/tags/dev", "DELETE")
    api.request("git/refs", "POST", {"ref": "refs/tags/dev", "sha": args.sha})
    release = api.request(
        "releases",
        "POST",
        {
            "tag_name": "dev",
            "target_commitish": args.sha,
            "name": "dev",
            "draft": True,
            "prerelease": True,
            "make_latest": "false",
            "body": f"Nightly {args.version}\n\nSource: `{args.sha}`\n\n未签名 alpha，每晚从 dev 构建。",
        },
    )
    # 任意附件上传失败保持草稿，下一次检查不会把它算作成功。
    run("gh", "release", "upload", "dev", *map(str, files), "--repo", api.repo)
    metadata.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    run("gh", "release", "upload", "dev", str(metadata), "--repo", api.repo)
    uploaded = api.request(f"releases/{release['id']}")
    names = {a["name"]: a for a in uploaded["assets"]}
    for path in [*files, metadata]:
        asset = names.get(path.name)
        if (
            not asset
            or asset["state"] != "uploaded"
            or asset["size"] != path.stat().st_size
        ):
            raise RuntimeError(f"incomplete nightly asset: {path.name}")
        if (
            asset.get("digest")
            and asset["digest"]
            != "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise RuntimeError(f"nightly asset digest mismatch: {path.name}")
    api.request(
        f"releases/{release['id']}",
        "PATCH",
        {"draft": False, "prerelease": True, "make_latest": "false"},
    )


def prepare(args):
    module = load_changelog(args.changelog)
    tags = module.all_tags()
    basis = args.base_version
    if args.kind == "patch" or basis:
        if basis not in tags or not re.fullmatch(r"v\d+\.\d+\.\d+", basis):
            raise ValueError("patch requires a published stable --base-version")
        if module.latest_on_line(basis, tags) != basis:
            raise ValueError(
                "patch base is not the latest stable on this maintenance line"
            )
        fixes = args.fixes.split()
        if not fixes:
            raise ValueError(
                "patch requires explicit fix commits; dev is never included implicitly"
            )
        target = module.next_version(args.kind, basis, args.version or None)
        if target != module.next_version("patch", basis):
            raise ValueError("patch explicit version must be base Z+1")
        source = git("rev-parse", f"refs/tags/{basis}^{{commit}}")
    else:
        if args.fixes:
            raise ValueError("fix commits require a patch base")
        latest = module.latest_version(
            v
            for v in tags
            if module.version_key(v)
            and module.version_key(v)[3]
            in (module.PHASE_RANK["beta"], module.PHASE_RANK[None])
        )
        target = module.next_version(args.kind, latest, args.version or None)
        target_key = module.version_key(target)
        if (
            target_key
            and target_key[3] == module.PHASE_RANK[None]
            and target_key[2] > 0
        ):
            raise ValueError(
                "stable patch versions require an explicit base and selected fixes"
            )
        source = git("rev-parse", "origin/dev")
        # 维护补丁不回 dev；最近一次 beta 或开发线转正必须已合入发布记录。
        development_release = module.latest_version(
            v
            for v in tags
            if (key := module.version_key(v)) is not None
            and (
                key[3] == module.PHASE_RANK["beta"]
                or (key[3] == module.PHASE_RANK[None] and key[2] == 0)
            )
        )
        if development_release:
            _, sections, _ = module.parse_changelog(
                git("show", "origin/dev:CHANGELOG.md")
            )
            if development_release not in sections:
                raise ValueError(
                    f"merge the development release record PR for {development_release} into dev before continuing beta/stable"
                )
        fixes = []
    if target in tags or not re.fullmatch(r"v\d+\.\d+\.\d+(?:-beta\.\d+)?", target):
        raise ValueError("duplicate or unsupported release version")
    base = "codex/release-base-" + target
    head = "codex/release-" + target
    # 准备分支不可重置或覆盖；重跑时维护者继续已创建的 PR，或关闭后另选版本。
    if git(
        "ls-remote", "--heads", "origin", f"refs/heads/{base}", f"refs/heads/{head}"
    ):
        raise ValueError(
            "preparation branch exists; continue its PR instead of replacing history"
        )
    git("checkout", "-b", base, source)
    if fixes:
        for value in fixes:
            if not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
                raise ValueError(
                    "fixes must be explicit commit SHAs in dependency order"
                )
            sha = git("rev-parse", f"{value}^{{commit}}")
            if len(git("rev-list", "--parents", "-n", "1", sha).split()) != 2:
                raise ValueError(
                    "merge/root fixes are unsupported; select single-parent commits"
                )
            paths = git(
                "diff-tree", "--no-commit-id", "--name-only", "-r", sha
            ).splitlines()
            if any(p == "CHANGELOG.md" or p == "res/version.json" for p in paths):
                raise ValueError(
                    "select original fix with fragment, not an absorb/release commit"
                )
            comparison = git("cherry", "HEAD", sha, sha + "^")
            if not comparison or comparison.startswith("-"):
                print(f"修复已在基准快照中：{sha}")
                continue
            # -x 保留来源证据；依赖缺失和冲突失败关闭，交维护者人工验证兼容性。
            git("cherry-pick", "-x", sha)
        if git("show", "HEAD:res/version.json") != git(
            "show", f"{basis}:res/version.json"
        ):
            raise ValueError("fix commits changed published version metadata")
        for name, pattern in module.VERSION_FIELDS:
            if module.extract_version_field(
                git("show", f"HEAD:{name}"), pattern
            ) != module.extract_version_field(git("show", f"{basis}:{name}"), pattern):
                raise ValueError(f"fix commit changed version field: {name}")
        # 旧 tag 的 push 入账和发版检查不能沿用到新来源；只迁移必要 CI 入口。
        # 工具由这些入口从 dev 读取，不把 dev 的业务、版本或日志带进补丁。
        entries = [
            f".github/workflows/{name}.yml"
            for name in (
                "absorb-changelog",
                "prepare-release",
                "build-app",
                "check-changelog",
            )
        ]
        for path in entries:
            git("restore", "--source=origin/dev", "--staged", "--worktree", path)
        if git("diff", "--cached", "--name-only"):
            git("commit", "-m", "ci: 更新独立补丁的入账与发布入口")
    # 至此仅本地组装，检查/编译失败前不创建任何远端分支。
    output(version=target, base=base, head=head, source_sha=git("rev-parse", "HEAD"))


def sync_github(args):
    branch = "codex/sync-github-main"
    git("fetch", "origin", "main", "dev")
    remote = git("ls-remote", "--heads", "origin", "refs/heads/" + branch)
    if remote:
        git("fetch", "origin", branch)
        git("checkout", "-B", branch, "origin/" + branch)
        git("merge", "--no-edit", "-s", "ours", "origin/main")
    else:
        git("checkout", "-b", branch, "origin/main")
    # 将树明确重建为 main + dev/.github；删除亦通过 restore --staged --worktree 同步。
    git("restore", "--source=origin/main", "--staged", "--worktree", ".")
    git("restore", "--source=origin/dev", "--staged", "--worktree", ".github")
    diff = git("diff", "--cached", "--name-only", "origin/main")
    if any(not p.startswith(".github/") for p in diff.splitlines()):
        raise RuntimeError("workflow sync contains non-.github changes")
    api = GitHub()
    prs = api.request(
        f"pulls?state=open&base=main&head={api.repo.split('/')[0]}:{branch}"
    )
    if not diff:
        if prs:
            api.request(f"pulls/{prs[0]['number']}", "PATCH", {"state": "closed"})
        return
    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", "ci: 同步 dev/.github 到 main")
    git("push", "origin", f"HEAD:refs/heads/{branch}")
    body = "- 仅同步 dev/.github 的新增、修改和删除。\n- 请维护者审核合并；不自动合并。"
    if prs:
        pr = api.request(f"pulls/{prs[0]['number']}", "PATCH", {"body": body})
    else:
        pr = api.request(
            "pulls",
            "POST",
            {
                "head": branch,
                "base": "main",
                "title": "ci: 同步 dev/.github 到 main",
                "body": body,
            },
        )
    api.request(f"issues/{pr['number']}/labels", "POST", {"labels": ["skip-changelog"]})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("nightly-check")
    check.add_argument("--state", required=True)
    version = sub.add_parser("nightly-version")
    version.add_argument("--number", required=True)
    version.add_argument("--changelog", default="scripts/changelog.py")
    publish = sub.add_parser("nightly-publish")
    publish.add_argument("--sha", required=True)
    publish.add_argument("--version", required=True)
    publish.add_argument("--artifacts", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument(
        "--kind", required=True, choices=["beta", "stable", "patch", "explicit"]
    )
    prep.add_argument("--version", default="")
    prep.add_argument("--base-version", default="")
    prep.add_argument("--fixes", default="")
    prep.add_argument("--changelog", required=True)
    sub.add_parser("sync-github")
    args = parser.parse_args()
    {
        "nightly-check": nightly_check,
        "nightly-version": nightly_version,
        "nightly-publish": nightly_publish,
        "prepare": prepare,
        "sync-github": sync_github,
    }[args.command](args)


if __name__ == "__main__":
    main()
