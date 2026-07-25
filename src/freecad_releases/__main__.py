#!/usr/bin/env python3
"""FreeCAD Release Dashboard Generator."""
from typing import Any

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from jinja2 import Environment, FileSystemLoader, select_autoescape

GITHUB_API = "https://api.github.com/repos/FreeCAD/FreeCAD/releases"
USER_AGENT = "FreeCAD-Dashboard/1.0"
OUTPUT_FILE = os.path.join("dist", "index.html")


def asset_name_patterns(ver: str, py: str = "") -> dict[str, re.Pattern]:
    return {
        "linux_x86_64": re.compile(
            rf"FreeCAD_{ver}-Linux-x86_64{py}\.AppImage$"
        ),
        "linux_aarch64": re.compile(
            rf"FreeCAD_{ver}-Linux-aarch64{py}\.AppImage$"
        ),
        "macos10_x86_64": re.compile(
            rf"FreeCAD_{ver}-macOS10-x86_64{py}\.dmg$"
        ),
        "macos_x86_64": re.compile(rf"FreeCAD_{ver}-macOS-x86_64{py}\.dmg$"),
        "macos11_arm64": re.compile(rf"FreeCAD_{ver}-macOS11-arm64{py}\.dmg$"),
        "macos15_arm64": re.compile(rf"FreeCAD_{ver}-macOS15-arm64{py}\.dmg$"),
        "macos_arm64": re.compile(rf"FreeCAD_{ver}-macOS-arm64{py}\.dmg$"),
        "windows_installer": re.compile(
            rf"FreeCAD_{ver}-Windows-x86_64{py}-installer\.exe$"
        ),
        "windows_7z": re.compile(rf"FreeCAD_{ver}-Windows-x86_64{py}\.7z$"),
        "source": re.compile(rf"freecad_source_{ver}\.tar\.gz$"),
    }


WEEKLY_PATTERNS = asset_name_patterns(r"weekly-\d{4}\.\d{2}\.\d{2}")
STABLE_PATTERNS = asset_name_patterns(r"\d+\.\d+(\.\d+)?", r"-py\d+")
RC_PATTERNS = asset_name_patterns(r"\d+\.\d+(\.\d+)?rc\d+", r"-py\d+")
SHA256_PATTERN = re.compile(r"^([a-fA-F0-9]{64})")
RC_TAG_RE = re.compile(r"^\d+\.\d+(\.\d+)?rc\d+$")

PLATFORM_CONFIG = {
    "linux": {
        "label": "Linux",
        "icon": "brand-open-source",
        "arches": [
            {
                "key": "x86_64",
                "label": "x86_64",
                "weekly_keys": ["linux_x86_64"],
                "stable_key": "linux_x86_64",
            },
            {
                "key": "aarch64",
                "label": "ARM64",
                "weekly_keys": ["linux_aarch64"],
                "stable_key": "linux_aarch64",
            },
        ],
    },
    "macos": {
        "label": "macOS",
        "icon": "brand-apple",
        "arches": [
            {
                "key": "arm",
                "label": "Apple Silicon",
                "weekly_keys": ["macos15_arm64", "macos11_arm64"],
                "stable_key": "macos_arm64",
            },
            {
                "key": "intel",
                "label": "Intel",
                "weekly_keys": ["macos10_x86_64"],
                "stable_key": "macos_x86_64",
            },
        ],
    },
    "windows": {
        "label": "Windows",
        "icon": "brand-windows",
        "arches": [
            {
                "key": "installer",
                "label": "Installer",
                "weekly_keys": ["windows_installer"],
                "stable_key": "windows_installer",
            },
            {
                "key": "portable",
                "label": "7z Portable",
                "weekly_keys": ["windows_7z"],
                "stable_key": "windows_7z",
            },
        ],
    },
    "source": {
        "label": "Source Code",
        "icon": "file-zip",
        "arches": [
            {
                "key": "source",
                "label": "Source",
                "weekly_keys": ["source"],
                "stable_key": "source",
            },
        ],
    },
}


def fetch_url(url: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def fetch_json(url: str) -> Any:
    return json.loads(fetch_url(url))


def fetch_releases() -> list[dict[str, Any]]:
    return fetch_json(f"{GITHUB_API}?per_page=100")


def match_asset(name: str, patterns: dict[str, re.Pattern]) -> str | None:
    for key, pattern in patterns.items():
        if pattern.search(name):
            return key
    return None


def get_sha256_url(asset_name: str, assets: list[dict[str, Any]]) -> str | None:
    sha_name = f"{asset_name}-SHA256.txt"
    for a in assets:
        if a["name"] == sha_name:
            return a["browser_download_url"]
    return None


def fetch_sha256(url: str) -> str | None:
    try:
        content = fetch_url(url)
        m = SHA256_PATTERN.match(content.strip())
        return m.group(1) if m else content.strip()[:64]
    except Exception:
        return None


def process_release(release: dict[str, Any], patterns: dict[str, re.Pattern]) -> dict[str, Any]:
    tag = release["tag_name"]
    date = release["created_at"]
    prerelease = release.get("prerelease", False)
    assets_raw = release.get("assets", [])

    result = {"tag": tag, "date": date, "prerelease": prerelease, "assets": {}}

    for asset in assets_raw:
        name = asset["name"]
        if name.endswith("-SHA256.txt") or name.endswith(".zsync"):
            continue
        key = match_asset(name, patterns)
        if key:
            sha256_url = get_sha256_url(name, assets_raw)
            result["assets"][key] = {
                "url": asset["browser_download_url"],
                "name": name,
                "size": asset.get("size", 0),
                "download_count": asset.get("download_count", 0),
                "sha256_url": sha256_url,
                "sha256": None,
            }
    return result


def fetch_sha256_batch(releases: list[dict[str, Any]]) -> None:
    with ThreadPoolExecutor(max_workers=20) as pool:
        fut_map = {}
        for rel in releases:
            for info in rel["assets"].values():
                if info["sha256_url"]:
                    fut = pool.submit(fetch_sha256, info["sha256_url"])
                    fut_map[fut] = (rel["tag"], info)
        for fut in fut_map:
            try:
                h = fut.result()
                fut_map[fut][1]["sha256"] = h
            except Exception:
                pass


def format_size(b: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def format_count(b: float) -> str:
    for unit in ["", "K", "M"]:
        if b < 1000:
            return f"+{int(b)}{unit} downloads"
        b /= 1000
    return "billions of downloads"


def fmt_date(iso: str) -> str:
    return iso[:10]


def short_sha256(h: str) -> str:
    if h and len(h) > 16:
        return f"{h[:10]}...{h[-6:]}"
    return h or "-"


def pick_asset(release: dict[str, Any], keys: list[str]):
    for k in keys:
        if k in release["assets"]:
            return release["assets"][k]
    return None


def build_platform_data(
    stable_releases: list[dict[str, Any]],
    rc_releases: list[dict[str, Any]],
    weekly_releases: list[dict[str, Any]],
):
    platforms = {}
    for plat_key, config in PLATFORM_CONFIG.items():
        arches = {}
        for arch in config["arches"]:
            stable_asset = None
            stable_release = None
            if stable_releases:
                for rel in stable_releases:
                    asset = pick_asset(rel, [arch["stable_key"]])
                    if asset:
                        stable_asset = asset
                        stable_release = rel
                        break

            weekly_asset = (
                pick_asset(weekly_releases[0], arch["weekly_keys"])
                if weekly_releases
                else None
            )

            stable_tag = stable_release["tag"] if stable_release else None
            weekly_tag = (
                weekly_releases[0]["tag"]
                if (weekly_releases and weekly_asset)
                else None
            )

            rc_asset = None
            rc_tag = None
            rc_date = None
            if rc_releases:
                latest_rc = rc_releases[0]
                rc_asset = pick_asset(latest_rc, arch["weekly_keys"])
                if rc_asset:
                    stable_date = stable_releases[0]["date"] if stable_releases else None
                    if stable_date is None or latest_rc["date"] > stable_date:
                        rc_tag = latest_rc["tag"]
                        rc_date = fmt_date(latest_rc["date"])
                    else:
                        rc_asset = None

            all_keys = set(arch["weekly_keys"]) | {arch["stable_key"]}
            seen = set()
            history = []
            for rel in stable_releases + rc_releases + weekly_releases:
                asset = None
                for k in all_keys:
                    if k in rel["assets"]:
                        asset = rel["assets"][k]
                        break
                if asset and rel["tag"] not in seen:
                    seen.add(rel["tag"])
                    history.append({
                        "tag": rel["tag"],
                        "date": rel["date"],
                        "asset": asset,
                    })

            history.sort(key=lambda h: h["date"], reverse=True)
            history = history[:20]

            arches[arch["key"]] = {
                "label": arch["label"],
                "stable": stable_asset,
                "stable_tag": stable_tag,
                "stable_date": fmt_date(stable_release["date"])
                if stable_release
                else None,
                "rc": rc_asset,
                "rc_tag": rc_tag,
                "rc_date": rc_date,
                "weekly": weekly_asset,
                "weekly_tag": weekly_tag,
                "weekly_date": fmt_date(weekly_releases[0]["date"])
                if (weekly_releases and weekly_asset)
                else None,
                "history": history,
            }

        platforms[plat_key] = {
            "label": config["label"],
            "icon": config["icon"],
            "arch_order": [a["key"] for a in config["arches"]],
            "arches": arches,
        }
    return platforms


def make_env():
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )
    env.filters["format_count"] = format_count
    env.filters["format_size"] = format_size
    env.filters["fmt_date"] = fmt_date
    env.filters["short_sha256"] = short_sha256
    return env


def main():
    print("Fetching FreeCAD releases from GitHub API...")
    try:
        releases = fetch_releases()
    except Exception as e:
        print(f"Error fetching releases: {e}")
        return 1
    print(f"Fetched {len(releases)} releases")

    print("Processing releases...")
    stable_releases = []
    weekly_releases = []
    rc_releases = []

    for release in releases:
        tag = release["tag_name"]
        prerelease = release.get("prerelease", False)

        if prerelease and tag.startswith("weekly-"):
            processed = process_release(release, WEEKLY_PATTERNS)
            if processed["assets"]:
                weekly_releases.append(processed)
        elif prerelease and RC_TAG_RE.match(tag):
            processed = process_release(release, RC_PATTERNS)
            if processed["assets"]:
                rc_releases.append(processed)
        elif not prerelease and not tag.startswith("weekly-"):
            processed = process_release(release, STABLE_PATTERNS)
            if processed["assets"]:
                stable_releases.append(processed)

    stable_releases.sort(key=lambda r: r["date"], reverse=True)
    rc_releases.sort(key=lambda r: r["date"], reverse=True)
    weekly_releases.sort(key=lambda r: r["date"], reverse=True)
    weekly_releases = weekly_releases[:20]

    print(f"  Stable releases: {len(stable_releases)}")
    print(f"  RC releases: {len(rc_releases)}")
    print(f"  Weekly releases: {len(weekly_releases)}")

    print("Fetching SHA256 checksums...")
    fetch_sha256_batch(stable_releases + rc_releases + weekly_releases)

    print("Building platform data...")
    platforms = build_platform_data(stable_releases, rc_releases, weekly_releases)

    print("Rendering template...")
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    env = make_env()
    template = env.get_template("index.html.j2")
    html = template.render(
        generated_at=generated_at,
        platforms=platforms,
        format_size=format_size,
        fmt_date=fmt_date,
        short_sha256=short_sha256,
    )

    os.makedirs("dist", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    exit(main())
