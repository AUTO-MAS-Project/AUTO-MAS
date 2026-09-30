"""发布工作流的 Git/GitHub 编排；放在 .github 内以便独立同步到 main。"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


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
    version = manifest.get("version")
    if (
        not isinstance(version, str)
        or not re.fullmatch(r"v\d+\.\d+\.\d+-alpha\.\d+", version)
        or not isinstance(expected, dict)
        or set(expected)
        != {f"AUTO-MAS-{version}-x64.zip", f"AUTO-MAS-Setup-{version}-x64.zip"}
    ):
        return False
    for name, info in expected.items():
        if (
            not isinstance(info, dict)
            or not isinstance(info.get("size"), int)
            or not isinstance(info.get("sha256"), str)
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


def nightly_identity(release):
    """比较发布身份和附件内容，下载次数等读操作引起的变化不算替换。"""
    if release is None:
        return None
    return (
        tuple(
            release.get(key)
            for key in ("id", "tag_name", "body", "draft", "prerelease", "immutable")
        ),
        {
            asset["name"]: tuple(
                asset.get(key) for key in ("id", "state", "size", "digest")
            )
            for asset in release["assets"]
        },
    )


def nightly_publish(args):
    api = GitHub()
    directory = Path(args.artifacts)
    source = json.loads(
        (directory / "build-source.json").read_text(encoding="utf-8-sig")
    )
    if source["source_sha"] != args.sha or source["version"] != args.version:
        raise ValueError("artifact source and requested release do not match")
    run_id = os.environ["GITHUB_RUN_ID"]
    if source.get("run_id") != run_id:
        raise ValueError("artifact run and requested release do not match")
    if not re.fullmatch(r"[a-f0-9]{40}", args.sha) or not re.fullmatch(
        r"v\d+\.\d+\.\d+-alpha\.\d+", args.version
    ):
        raise ValueError("invalid nightly release identity")
    files = sorted(directory.glob("AUTO-MAS-*-x64.zip"))
    if {p.name for p in files} != {
        f"AUTO-MAS-{args.version}-x64.zip",
        f"AUTO-MAS-Setup-{args.version}-x64.zip",
    }:
        raise ValueError("nightly requires installer and portable packages")
    manifest = {
        "status": "complete",
        "source_sha": args.sha,
        "version": args.version,
        "run_id": run_id,
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
    identity_before = nightly_identity(previous)
    if previous:
        # 并发只串行化作业，旧运行的失败重试仍可能晚于新运行到达。
        # 草稿未上传元数据时也用正文的构建号保护，不能让旧重试清掉较新草稿。
        identity = re.search(
            r"^Nightly (v\d+\.\d+\.\d+-alpha\.(\d+))\b",
            previous.get("body") or "",
            re.MULTILINE,
        )
        if not identity:
            raise RuntimeError(
                "cannot identify previous nightly; preserve release for review"
            )
        previous_number = int(identity[2])
        number = int(args.version.rsplit(".", 1)[1])
        if previous_number > number:
            print("已有较新的 nightly，跳过旧运行重试，保留当前 Release/tag。")
            return
        previous_run = re.search(
            r"^Run: `(\d+)`$", previous.get("body") or "", re.MULTILINE
        )
        if previous_number == number and previous_run and previous_run[1] != run_id:
            raise RuntimeError(
                "nightly number belongs to another run; preserve release"
            )
        assets = {a["name"]: a for a in previous["assets"]}
        previous_metadata = assets.get("nightly-build.json")
        if previous_number == number and previous_metadata:
            try:
                previous_source = api.asset_json(previous_metadata)
            except (ValueError, UnicodeError):
                previous_source = None
            if (
                isinstance(previous_source, dict)
                and previous_source.get("run_id") != run_id
            ):
                raise RuntimeError(
                    "nightly number belongs to another run; preserve release"
                )
        if completed_nightly(api, previous, args.sha):
            print("本次源码已有完整 nightly，跳过重复发布。")
            return
        if previous.get("immutable"):
            raise RuntimeError(
                "dev release is immutable; maintainer must disable nightly immutability"
            )
    if nightly_identity(api.nightly()) != identity_before:
        raise RuntimeError(
            "nightly changed before replacement; retry with current state"
        )
    if previous:
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
            "body": f"Nightly {args.version}\n\nSource: `{args.sha}`\n\nRun: `{run_id}`\n\n未签名 alpha，每晚从 dev 构建。",
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


def changed_line_ranges(patch, *, new):
    """零上下文 diff 的改动范围；插入/删除点同时占用相邻边界。"""
    ranges = []
    for match in re.finditer(r"(?m)^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", patch):
        start = int(match[3 if new else 1])
        count = int(match[4 if new else 2] or "1")
        ranges.append((start, start + count - 1 if count else start + 1))
    return ranges


def check_backend_hotfixes(basis):
    """所选快照必须保留基准客户端已拿到的后端热修。"""
    release_ref = f"refs/remotes/origin/release/{basis}"
    if not git("ls-remote", "--heads", "origin", f"refs/heads/release/{basis}"):
        raise ValueError("patch base has no backend release branch to verify")
    git("fetch", "--no-tags", "origin", f"refs/heads/release/{basis}:{release_ref}")
    git("merge-base", "--is-ancestor", f"refs/tags/{basis}^{{commit}}", release_ref)
    # 虚拟合并只写 Git 对象；如果保留热修仍会改变候选业务树，说明候选漏了修复。
    # 比按补丁上下文反向 apply 更能容忍同文件里的后续兼容改动。
    try:
        merged = git(
            "merge-tree",
            "--write-tree",
            f"--merge-base=refs/tags/{basis}",
            "HEAD",
            release_ref,
        )
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise
        merged = error.stdout
    tree = merged.splitlines()[0]
    if not re.fullmatch(r"[a-f0-9]{40}", tree):
        raise ValueError("cannot verify the backend hotfix merge")
    missing = git(
        "diff",
        "--name-only",
        tree,
        "HEAD",
        "--",
        ".",
        ":(exclude).github",
        ":(exclude).cnb.yml",
        ":(exclude)scripts",
        ":(exclude)tests",
        ":(exclude)changelog.d",
        ":(exclude)CHANGELOG.md",
        ":(exclude)res/version.json",
        ":(exclude)AGENTS.md",
    )
    conflicts = []
    for path in missing.splitlines():
        hotfix_lines = changed_line_ranges(
            git("diff", "--unified=0", f"refs/tags/{basis}", release_ref, "--", path),
            new=True,
        )
        candidate_lines = changed_line_ranges(
            git("diff", "--unified=0", release_ref, "HEAD", "--", path), new=False
        )
        # Git 按整个块合并可能把相邻的独立改动判成冲突；仅在热修改动行完全未动时放行。
        if (
            not hotfix_lines
            or not candidate_lines
            or any(
                a <= d and c <= b for a, b in hotfix_lines for c, d in candidate_lines
            )
        ):
            conflicts.append(path)
    if conflicts:
        raise ValueError(
            "selected fixes do not preserve the current backend hotfixes: "
            + ", ".join(conflicts)
            + "; include missing SHAs or review conflicting changes before preparing"
        )


def patch_check(args):
    module = load_changelog(args.changelog)
    version = json.loads(module.VERSION_JSON_PATH.read_text(encoding="utf-8"))[
        "version"
    ]
    key = module.version_key(version)
    if key and key[3] == module.PHASE_RANK[None] and key[2] > 0:
        basis = module.latest_on_line(
            version, [tag for tag in module.all_tags() if tag != version]
        )
        if not basis:
            raise ValueError("patch has no stable base on its maintenance line")
        check_backend_hotfixes(basis)


def prepare(args):
    module = load_changelog(args.changelog)
    tags = module.all_tags()
    basis = args.base_version
    if args.kind == "patch" or basis:
        if basis not in tags or not re.fullmatch(r"v\d+\.\d+\.\d+", basis):
            raise ValueError("patch requires a published stable --base-version")
        if module.latest_on_line(module.next_version("patch", basis), tags) != basis:
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
            if development_release not in module.reachable_tags("origin/dev"):
                raise ValueError(
                    f"merge the release record PR for {development_release} into dev with a merge commit, not squash; release tag ancestry is missing"
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
            # 历史里有同一补丁不代表当前快照仍保留它（可能已经 revert）。
            # 实际重放，只跳过当前树上确实没有差异的修复。
            git("cherry-pick", "-x", "--empty=drop", sha)
        if git("show", "HEAD:res/version.json") != git(
            "show", f"{basis}:res/version.json"
        ):
            raise ValueError("fix commits changed published version metadata")
        for name, pattern in module.VERSION_FIELDS:
            if module.extract_version_field(
                git("show", f"HEAD:{name}"), pattern
            ) != module.extract_version_field(git("show", f"{basis}:{name}"), pattern):
                raise ValueError(f"fix commit changed version field: {name}")
        # 已安装客户端拿到的热修也必须保留，不能因漏填 SHA 而随升级消失。
        check_backend_hotfixes(basis)
    # 旧 tag 迁移必要 CI 入口；生成器与发布工具一同冻结，构建不再随 dev 漂移。
    # 不带入 dev 的业务、版本或日志，旧 release 来源保持不变。
    entries = ["scripts/changelog.py", ".github/scripts"]
    if fixes:
        entries += [
            f".github/workflows/{name}.yml"
            for name in (
                "absorb-changelog",
                "prepare-release",
                "build-app",
                "check-changelog",
                "sync-cnb",
                "mirrorchyan-release-note",
            )
        ]
    entries += git(
        "ls-tree",
        "-r",
        "--name-only",
        "origin/dev",
        "--",
        ".github/workflows/cnb_release.py",
        ".github/workflows/github_download_and_cnb_upload.py",
        ".github/workflows/requirements.txt",
    ).splitlines()
    for path in entries:
        git("restore", "--source=origin/dev", "--staged", "--worktree", path)
    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", "ci: 固定独立发布的检查与发布工具")
    # 至此仅本地组装，检查/编译失败前不创建任何远端分支。
    output(version=target, base=base, head=head, source_sha=git("rev-parse", "HEAD"))


def sync_github(args):
    branch = "codex/sync-github-main"
    git(
        "fetch", "--no-tags", "origin", "main", "refs/heads/dev:refs/remotes/origin/dev"
    )
    main_paths = set(
        git("ls-tree", "-r", "--name-only", "origin/main", "--", ".github").splitlines()
    )
    dev_paths = set(
        git("ls-tree", "-r", "--name-only", "origin/dev", "--", ".github").splitlines()
    )
    unmigrated = [
        path
        for path in sorted(main_paths - dev_paths)
        if not git("log", "-1", "--format=%H", "origin/dev", "--", path)
    ]
    if unmigrated:
        raise ValueError(
            "migrate main-only CI to dev before syncing: " + ", ".join(unmigrated)
        )
    remote = git("ls-remote", "--heads", "origin", "refs/heads/" + branch)
    if remote:
        git("fetch", "--no-tags", "origin", branch)
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


def publish_refs(args):
    """同次失败作业可续跑，只接受已存在且仍指向本次构建的引用。"""
    if not re.fullmatch(
        r"v\d+\.\d+\.\d+(?:-beta\.\d+)?", args.version
    ) or not re.fullmatch(r"[a-f0-9]{40}", args.sha):
        raise ValueError("invalid release identity")
    branch = f"refs/heads/release/{args.version}"
    tag = f"refs/tags/{args.version}"
    remote = dict(
        line.split()[::-1]
        for line in git("ls-remote", "origin", branch, tag, tag + "^{}").splitlines()
    )
    for ref in (branch, tag):
        if ref in remote and remote.get(ref + "^{}", remote[ref]) != args.sha:
            raise ValueError(f"published ref belongs to another source: {ref}")
    missing = [ref for ref in (branch, tag) if ref not in remote]
    if missing:
        git("push", "--atomic", "origin", *(f"{args.sha}:{ref}" for ref in missing))


def record_dev(args):
    """从当前 dev 重建发布记录，保留后续条目和业务树，并保留 tag 祖先关系。"""
    if not re.fullmatch(r"v\d+\.\d+\.0(?:-beta\.\d+)?", args.version):
        raise ValueError("only development releases are recorded into dev")
    git(
        "fetch",
        "--no-tags",
        "origin",
        "refs/heads/dev:refs/remotes/origin/dev",
        f"refs/tags/{args.version}:refs/tags/{args.version}",
    )
    sha = git("rev-parse", f"refs/tags/{args.version}^{{commit}}")
    if sha != args.sha:
        raise ValueError("release tag does not match the built source")
    module = load_changelog(args.changelog)
    prepared = git("merge-base", sha, "origin/dev")
    _, baseline, baseline_dates = module.parse_changelog(
        git("show", f"{prepared}:CHANGELOG.md")
    )
    _, published, published_dates = module.parse_changelog(
        git("show", f"{sha}:CHANGELOG.md")
    )
    current_version, current, current_dates = module.parse_changelog(
        git("show", "origin/dev:CHANGELOG.md")
    )
    if args.version not in published or module.version_key(
        current_version
    ) > module.version_key(args.version):
        raise ValueError("release record is missing or older than current dev")
    recorded = (
        args.version in current and current_dates[args.version] != module.UNRELEASED
    )
    if recorded and (
        current[args.version] != published[args.version]
        or current_dates[args.version] != published_dates[args.version]
    ):
        raise ValueError("dev release record differs from the published snapshot")
    pending = {
        category: list(items)
        for version, categories in current.items()
        if current_dates[version] == module.UNRELEASED
        for category, items in categories.items()
    }
    consumed = {
        module.split_entry(item).render()
        for version, categories in baseline.items()
        if baseline_dates[version] == module.UNRELEASED
        for items in categories.values()
        for item in items
    }
    fragments = []
    for path in git(
        "ls-tree", "-r", "--name-only", prepared, "--", "changelog.d"
    ).splitlines():
        if not module.FRAGMENT_NAME.match(Path(path).name):
            continue
        before = module.show_file(prepared, path)
        if module.show_file(sha, path) is not None:
            raise ValueError("published snapshot still contains a consumed fragment")
        fragment = module.parse_fragment(Path(path), before)
        fragments.append((path, before, fragment))
    if not recorded:
        # 准备时尚未入账、后来被 nightly 入账的碎片也按内容身份扣除。
        fragment_keys = {
            (fragment.project_name, fragment.text) for _, _, fragment in fragments
        }
        pending = {
            category: [
                item
                for item in items
                if module.split_entry(item).render() not in consumed
                and (module.split_entry(item).project, module.split_entry(item).text)
                not in fragment_keys
            ]
            for category, items in pending.items()
        }
    pending = {category: items for category, items in pending.items() if items}
    removed = {
        version
        for version in baseline
        if baseline_dates[version] != module.UNRELEASED and version not in published
    }
    history = {
        version: categories
        for version, categories in current.items()
        if current_dates[version] != module.UNRELEASED
        and version not in published
        and version not in removed
    }
    sections = {
        **({module.UNRELEASED: pending} if pending else {}),
        **published,
        **history,
    }
    dates = {
        **({module.UNRELEASED: module.UNRELEASED} if pending else {}),
        **published_dates,
        **{version: current_dates[version] for version in history},
    }
    branch = f"codex/release-record-{args.version}"
    existing = git("ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    if recorded and sha in git("rev-list", "origin/dev").split():
        print("开发线已包含完整发布记录与 tag，无需重复 PR。")
        return
    if existing:
        git(
            "fetch",
            "--no-tags",
            "origin",
            f"refs/heads/{branch}:refs/remotes/origin/{branch}",
        )
        git("checkout", "-B", branch, f"origin/{branch}")
        allowed = {
            "CHANGELOG.md",
            "res/version.json",
            *(name for name, _ in module.VERSION_FIELDS),
            *(path for path, _, _ in fragments),
        }
        if any(
            path not in allowed
            for path in git("diff", "--name-only", "origin/dev...HEAD").splitlines()
        ):
            raise ValueError(
                "record branch has unrelated changes; preserve it for review"
            )
        git("merge", "--no-ff", "--no-commit", "-s", "ours", "origin/dev")
        git("restore", "--source=origin/dev", "--staged", "--worktree", ".")
    else:
        git("checkout", "-b", branch, "origin/dev")
        git("merge", "--no-ff", "--no-commit", "-s", "ours", sha)
    for path, before, _ in fragments:
        file = Path(path)
        if file.exists():
            if (
                file.read_text(encoding="utf-8") != before + "\n"
                and file.read_text(encoding="utf-8").strip() != before.strip()
            ):
                raise ValueError(f"consumed fragment changed after preparation: {path}")
            file.unlink()
    module.write_text(module.CHANGELOG_PATH, module.render_changelog(sections, dates))
    module.sync_generated()
    if module.command_check(argparse.Namespace(pr_base=None)):
        raise ValueError("release record generated files are inconsistent")
    git(
        "add",
        "CHANGELOG.md",
        "res/version.json",
        *(name for name, _ in module.VERSION_FIELDS),
        "changelog.d",
    )
    git("diff", "--cached", "--check")
    if (
        git("diff", "--cached", "--name-only")
        or Path(git("rev-parse", "--git-path", "MERGE_HEAD")).exists()
    ):
        git("commit", "-m", f"chore: 同步 {args.version} 开发线发布记录")
    git("push", "origin", f"HEAD:refs/heads/{branch}")
    api = GitHub()
    prs = api.request(
        f"pulls?state=open&base=dev&head={api.repo.split('/')[0]}:{branch}"
    )
    body = f"- 同步 {args.version} 的准确发布记录与版本；保留当前 dev 的后续未发布条目及业务代码。\n- 使用 merge commit 合并以保留发布 tag 祖先关系，勿 squash；临时记录分支可解决冲突，不改 release 后端来源。"
    if prs:
        pr = api.request(f"pulls/{prs[0]['number']}", "PATCH", {"body": body})
    else:
        pr = api.request(
            "pulls",
            "POST",
            {
                "head": branch,
                "base": "dev",
                "title": f"chore: 同步 {args.version} 开发线发布记录",
                "body": body,
            },
        )
    api.request(
        f"issues/{pr['number']}/labels",
        "POST",
        {"labels": ["changelog-maintenance", "skip-changelog"]},
    )


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
    refs = sub.add_parser("publish-refs")
    refs.add_argument("--version", required=True)
    refs.add_argument("--sha", required=True)
    record = sub.add_parser("record-dev")
    record.add_argument("--version", required=True)
    record.add_argument("--sha", required=True)
    record.add_argument("--changelog", default="scripts/changelog.py")
    patch = sub.add_parser("patch-check")
    patch.add_argument("--changelog", default="scripts/changelog.py")
    sub.add_parser("sync-github")
    args = parser.parse_args()
    {
        "nightly-check": nightly_check,
        "nightly-version": nightly_version,
        "nightly-publish": nightly_publish,
        "prepare": prepare,
        "publish-refs": publish_refs,
        "record-dev": record_dev,
        "patch-check": patch_check,
        "sync-github": sync_github,
    }[args.command](args)


if __name__ == "__main__":
    main()
