"""HSR 外部脚本更新——上游契约核验。

把 app/task/HSR/tools/update/ 依赖的每条上游假设写成可重跑的断言：Mirror 酱
两个 rid 的免 CDK 查询、发行资产命名、自建站与 GitHub 的字节一致性、归档布局
（M7A 单根 update/、SRA 扁平）、以及「更新包里不含任何用户状态」。

任何一条变红，说明上游改了契约，对应的实现要重新评估——它不是 pytest 用例，
需要联网，所以放在 scripts/ 手动跑。

用法（从仓库根）:
    python scripts/hsr_update_contract_check.py            # 只跑网络契约（快）
    python scripts/hsr_update_contract_check.py --local    # 加上本机安装目录探测
    python scripts/hsr_update_contract_check.py --archives # 加上归档下载与结构核验（~170MB）

--local 会在 HSR_REFERENCE_ROOT 指向的目录里找本机的 M7A/SRA 副本，未设置时
跳过该段。依赖仅标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "AutoMasGui/contract-check"}
GITHUB_API = "https://api.github.com"
MIRROR_API = "https://mirrorchyan.com/api/resources"
STATION = "https://download.auto-mas.top/d"

M7A_REPO, M7A_RID = "moesnow/March7thAssistant", "March7thAssistant"
SRA_REPO, SRA_RID = "Shasnow/StarRailAssistant", "StarRailAssistant"

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((ok, name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def get_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def range_probe(url: str, nbytes: int = 4095) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={**UA, "Range": f"bytes=0-{nbytes}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read(), r.headers.get("Content-Range", "")


# ── 1. 版本发现契约 ───────────────────────────────────────────────────


def check_version_discovery() -> dict:
    print("\n[1] 版本发现契约")
    facts: dict = {}

    for label, repo, rid in (("M7A", M7A_REPO, M7A_RID), ("SRA", SRA_REPO, SRA_RID)):
        gh = get_json(f"{GITHUB_API}/repos/{repo}/releases/latest")
        tag = gh["tag_name"]
        facts[f"{label}_tag"] = tag
        facts[f"{label}_assets"] = {a["name"]: a for a in gh["assets"]}
        check(f"{label} GitHub releases/latest 可达", bool(tag), f"tag={tag}")
        check(
            f"{label} GitHub 资产带 sha256 digest",
            all(a.get("digest", "").startswith("sha256:") for a in gh["assets"]),
            f"{len(gh['assets'])} 个资产",
        )

        # Mirror 酱：无 CDK 能查版本、拿不到下载地址
        mc = get_json(
            f"{MIRROR_API}/{rid}/latest?user_agent=contract-check&current_version=v0.0.1"
        )
        d = mc.get("data", {})
        check(
            f"{label} Mirror酱 无 CDK 可查版本",
            mc.get("code") == 0 and bool(d.get("version_name")),
            f"code={mc.get('code')} version={d.get('version_name')}",
        )
        check(
            f"{label} Mirror酱 无 CDK 不给下载地址",
            not d.get("url"),
            "符合预期（下载需 CDK）",
        )
        facts[f"{label}_mirror_version"] = d.get("version_name", "")

        # 单平台 rid：带 os/arch 应当 404
        try:
            get_json(
                f"{MIRROR_API}/{rid}/latest?user_agent=contract-check&os=windows&arch=amd64"
            )
            check(
                f"{label} Mirror酱 拒绝 os/arch 参数",
                False,
                "竟然接受了——rid 可能已改为多平台",
            )
        except urllib.error.HTTPError as e:
            check(
                f"{label} Mirror酱 拒绝 os/arch 参数", e.code == 404, f"HTTP {e.code}"
            )

    # beta 通道
    mc_beta = get_json(
        f"{MIRROR_API}/{SRA_RID}/latest?user_agent=contract-check&channel=beta&current_version=v0.0.1"
    )
    beta_v = mc_beta.get("data", {}).get("version_name", "")
    check("SRA Mirror酱 beta 通道可用", bool(beta_v), f"beta={beta_v}")
    facts["SRA_beta"] = beta_v

    return facts


# ── 2. 资产命名与布局契约 ─────────────────────────────────────────────


def check_asset_contract(facts: dict) -> None:
    print("\n[2] 资产命名与布局契约")

    m7a = facts["M7A_assets"]
    check(
        "M7A update.7z 存在且文件名不带版本号",
        "update.7z" in m7a,
        f"{m7a.get('update.7z', {}).get('size', 0) / 1048576:.1f} MB",
    )
    check(
        "M7A full.zip 存在（7za 缺失时的回退包）",
        "March7thAssistant_full.zip" in m7a,
        f"{m7a.get('March7thAssistant_full.zip', {}).get('size', 0) / 1048576:.0f} MB",
    )

    sra_tag = facts["SRA_tag"]
    sra = facts["SRA_assets"]
    full_name = f"StarRailAssistant_{sra_tag}.zip"
    check(
        "SRA Full 包按 StarRailAssistant_{tag}.zip 命名",
        full_name in sra,
        f"{sra.get(full_name, {}).get('size', 0) / 1048576:.1f} MB",
    )

    # 自建站：与 GitHub 字节一致、支持 Range、beta 也在
    gh_size = sra.get(full_name, {}).get("size", 0)
    gh_digest = sra.get(full_name, {}).get("digest", "").split(":")[-1]

    st_zip = f"{STATION}/StarRailAssistant/StarRailAssistant-{sra_tag}.zip"
    status, head, crange = range_probe(st_zip, 1023)
    st_size = int(crange.split("/")[-1]) if "/" in crange else 0
    check("自建站 SRA zip 支持 Range 续传", status == 206, f"HTTP {status}")
    check(
        "自建站 SRA zip 与 GitHub 字节数一致",
        st_size == gh_size and gh_size > 0,
        f"station={st_size} github={gh_size}",
    )
    check("自建站 SRA zip 是合法 zip", head[:4] == b"PK\x03\x04", repr(head[:4]))

    req = urllib.request.Request(
        f"{STATION}/StarRailAssistant/StarRailAssistant-{sra_tag}.sha256", headers=UA
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        st_sha = r.read().decode().strip()
    check(
        "自建站 sha256 旁文件与 GitHub digest 一致",
        st_sha == gh_digest,
        f"{st_sha[:16]}… vs {gh_digest[:16]}…",
    )

    if facts.get("SRA_beta"):
        try:
            s, _, _ = range_probe(
                f"{STATION}/StarRailAssistant/StarRailAssistant-{facts['SRA_beta']}.zip",
                255,
            )
            check("自建站同步 SRA beta", s == 206, f"HTTP {s}")
        except urllib.error.HTTPError as e:
            check("自建站同步 SRA beta", False, f"HTTP {e.code}")

    # M7A full.zip 根文件夹（回退路径要据此脱壳）
    url = m7a["March7thAssistant_full.zip"]["browser_download_url"]
    _, head, _ = range_probe(url, 4095)
    nlen = struct.unpack("<H", head[26:28])[0]
    root = head[30 : 30 + nlen].decode("utf-8", "replace").split("/")[0]
    check(
        "M7A full.zip 单根文件夹为 March7thAssistant_full",
        root == "March7thAssistant_full",
        f"root={root!r}",
    )


# ── 3. 本机安装目录探测契约 ───────────────────────────────────────────


def check_local_probes() -> None:
    print("\n[3] 本机安装目录探测契约")
    raw = os.environ.get("HSR_REFERENCE_ROOT", "").strip()
    if not raw:
        print("  未设置 HSR_REFERENCE_ROOT，跳过本机探测")
        return
    ref = Path(raw)
    if not ref.is_dir():
        check("HSR_REFERENCE_ROOT 指向的目录存在", False, str(ref))
        return

    m7a_dirs = [
        p for p in ref.glob("*March7th*") if (p / "March7th Assistant.exe").is_file()
    ]
    for p in m7a_dirs:
        vf = p / "assets" / "config" / "version.txt"
        v = vf.read_text(encoding="utf-8").strip() if vf.exists() else ""
        check(
            f"M7A 版本可从 assets/config/version.txt 读出 ({p.name})",
            bool(v) and v.startswith("v"),
            f"version={v!r}",
        )
        check(
            f"M7A 自带 7za.exe ({p.name})",
            (p / "assets" / "binary" / "7za.exe").is_file(),
        )

    sra_dirs = [p for p in ref.glob("*") if (p / "SRA-cli.exe").is_file()]
    for p in sra_dirs:
        t0 = time.monotonic()
        try:
            r = subprocess.run(
                [str(p / "SRA-cli.exe"), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            dt = time.monotonic() - t0
            out = (r.stdout or r.stderr).strip()
            check(
                f"SRA --version 快速返回且不弹 UAC ({p.name})",
                r.returncode == 0 and dt < 5 and bool(out),
                f"{dt:.2f}s rc={r.returncode} out={out!r}",
            )
            check(
                f"SRA --version 输出裸版本号（需自行补 v）({p.name})",
                bool(out) and not out.startswith("v"),
                f"out={out!r}",
            )
        except subprocess.TimeoutExpired:
            check(
                f"SRA --version 快速返回且不弹 UAC ({p.name})",
                False,
                "超时（疑似 UAC 弹窗）",
            )

        # 用户自定义策略目录必须在覆盖后保留
        check(
            f"SRA 安装目录内存在用户可定制的 strategies 目录 ({p.name})",
            (p / "tasks" / "currency_wars" / "strategies").is_dir(),
            "覆盖式更新不得删除此目录",
        )


# ── 4. 归档结构契约（需下载）────────────────────────────────────────


def check_archives(facts: dict, dest: Path) -> None:
    print("\n[4] 归档结构契约（下载 ~170MB）")
    dest.mkdir(parents=True, exist_ok=True)

    asset = facts["M7A_assets"]["update.7z"]
    pkg = dest / "update.7z"
    expected = asset["digest"].split(":")[-1]

    if not (pkg.exists() and pkg.stat().st_size == asset["size"]):
        h = hashlib.sha256()
        req = urllib.request.Request(asset["browser_download_url"], headers=UA)
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=300) as r, open(pkg, "wb") as f:
            while chunk := r.read(262144):
                f.write(chunk)
                h.update(chunk)
        print(
            f"    下载完成 {pkg.stat().st_size / 1048576:.1f} MB / {time.monotonic() - t0:.0f}s"
        )
        actual = h.hexdigest()
    else:
        actual = hashlib.sha256(pkg.read_bytes()).hexdigest()
    check(
        "M7A update.7z sha256 与 GitHub digest 一致",
        actual == expected,
        f"{actual[:16]}…",
    )

    # 用 M7A 自带的 7za 列包内容——这正是实现所依赖的那个二进制
    ref_root = os.environ.get("HSR_REFERENCE_ROOT", "").strip()
    sevenzip = next(
        (
            p / "assets" / "binary" / "7za.exe"
            for p in (Path(ref_root).glob("*March7th*") if ref_root else ())
            if (p / "assets" / "binary" / "7za.exe").is_file()
        ),
        None,
    )
    if not sevenzip:
        check(
            "找到 M7A 自带 7za.exe 用于解包",
            False,
            "需要 HSR_REFERENCE_ROOT 指向含 M7A 安装的目录；跳过后续 7z 结构核验",
        )
        return

    out = subprocess.run(
        [str(sevenzip), "l", str(pkg)], capture_output=True, text=True, timeout=180
    ).stdout
    # 7za 的条目行带属性列（如 ....A / D....）；尾部汇总行同样以日期开头但没有
    # 属性列，不加这一条会把 "2684 files, 320 folders" 当成路径。
    entry = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+(\S{5})\s")
    paths = [
        ln.rsplit("  ", 1)[-1].strip() for ln in out.splitlines() if entry.match(ln)
    ]
    roots = {p.replace("/", "\\").split("\\")[0] for p in paths if p}
    check(
        "M7A update.7z 为单根 update/ （应用时需脱壳）",
        roots == {"update"},
        f"roots={sorted(roots)}",
    )

    owned = {"assets", "libraries"}
    second = {
        p.replace("/", "\\").split("\\")[1]
        for p in paths
        if p.lower().startswith("update\\") and "\\" in p[7:]
    }
    check(
        "M7A 包内只含上游资产（assets/libraries/exe）",
        owned.issubset(second),
        f"第二层={sorted(second)}",
    )

    for probe in ("config.yaml", "config", "settings", "logs", "3rdparty"):
        hit = any(
            p.replace("/", "\\").lower().startswith(f"update\\{probe.lower()}")
            for p in paths
        )
        check(
            f"M7A 包内不含用户状态 {probe}",
            not hit,
            "覆盖后用户配置天然幸存" if not hit else "**承重假设失效**",
        )

    # SRA Full 包扁平布局
    sra_tag = facts["SRA_tag"]
    sra_asset = facts["SRA_assets"][f"StarRailAssistant_{sra_tag}.zip"]
    _, head, _ = range_probe(sra_asset["browser_download_url"], 4095)
    nlen = struct.unpack("<H", head[26:28])[0]
    first = head[30 : 30 + nlen].decode("utf-8", "replace")
    check(
        "SRA Full 包为扁平布局（无根文件夹，直接覆盖）",
        "/" not in first.rstrip("/") or not first.endswith("/"),
        f"首条目={first!r}",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="探测本机安装目录")
    ap.add_argument("--archives", action="store_true", help="下载并核验归档结构")
    ap.add_argument("--dest", type=Path, default=Path(__file__).parent / "downloads")
    args = ap.parse_args()

    print(f"HSR 更新契约核验  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    facts = check_version_discovery()
    check_asset_contract(facts)
    if args.local:
        check_local_probes()
    if args.archives:
        check_archives(facts, args.dest)

    failed = [n for ok, n, _ in _results if not ok]
    print(f"\n{'=' * 60}\n{len(_results) - len(failed)}/{len(_results)} 通过")
    if failed:
        print("失败项：")
        for n in failed:
            print(f"  - {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
