#!/usr/bin/env python3
"""Skill entry point: provision local dependencies and a verified official core."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DETECTOR = Path(__file__).with_name("detector.py")
RELEASE_API = "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class SetupError(Exception):
    pass


def run_checked(args, timeout=180):
    try:
        result = subprocess.run([str(x) for x in args], capture_output=True, timeout=timeout,
                                creationflags=FLAGS)
    except (OSError, subprocess.TimeoutExpired):
        raise SetupError("自动准备过程失败或超时；请查看网络和运行权限。") from None
    if result.returncode:
        # Do not relay pip/curl output: it can contain proxy credentials.
        raise SetupError("依赖安装或命令执行失败；未改动系统代理，未回退检测直连。")
    return result


def ensure_python(proxy=None):
    if sys.version_info < (3, 10):
        raise SetupError("技能执行环境需要 Python 3.10+，请由代理查找可用 Python/uv 运行时。")
    folder = ROOT / ".venv"
    python = folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        print("正在自动创建项目运行环境…", flush=True)
        run_checked([sys.executable, "-m", "venv", folder])
    ready = subprocess.run([str(python), "-c", "import yaml; assert tuple(map(int, yaml.__version__.split('.')[:2])) >= (6, 0)"],
                           capture_output=True, timeout=15, creationflags=FLAGS)
    if ready.returncode:
        print("正在自动安装项目依赖…", flush=True)
        command = [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                   "--retries", "2", "--timeout", "20", "-r", ROOT / "requirements.txt"]
        if proxy:
            command += ["--proxy", proxy]
        run_checked(command)
    return python


def asset_pattern(system, machine):
    architecture = {"amd64": "amd64-compatible", "x86_64": "amd64-compatible",
                    "arm64": "arm64", "aarch64": "arm64"}.get(machine.lower())
    target = {"Windows": "windows", "Darwin": "darwin"}.get(system)
    if not target or not architecture:
        raise SetupError(f"暂不自动下载此平台内核：{system}/{machine}")
    suffix = "zip" if system == "Windows" else "gz"
    return re.compile(rf"^mihomo-{target}-{architecture}-v[^/]+\.{suffix}$")


def choose_asset(release, system, machine):
    pattern = asset_pattern(system, machine)
    matches = [asset for asset in release.get("assets", []) if pattern.fullmatch(asset.get("name", ""))]
    if len(matches) != 1:
        raise SetupError("官方发布中未找到唯一匹配的平台内核。")
    asset = matches[0]
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", asset.get("digest") or ""):
        raise SetupError("官方发布缺少 SHA-256 校验值，未执行未校验的内核。")
    if not asset.get("browser_download_url", "").startswith("https://github.com/MetaCubeX/mihomo/releases/download/"):
        raise SetupError("内核下载地址不是预期的官方仓库。")
    return asset


def download(url, destination, proxy=None):
    # urllib uses OS proxy discovery on Windows; curl may not. Try both acquisition
    # transports, while node probes retain their strictly explicit SOCKS route.
    if not proxy or proxy.startswith(("http://", "https://")):
        handlers = [urllib.request.ProxyHandler({"https": proxy})] if proxy else []
        opener = urllib.request.build_opener(*handlers)
        try:
            with opener.open(urllib.request.Request(url, headers={"User-Agent": "ai-flight-detector"}), timeout=30) as response:
                if not response.url.startswith("https://"):
                    raise SetupError("官方下载发生非 HTTPS 跳转。")
                data = response.read(100 * 1024 * 1024 + 1)
            if len(data) > 100 * 1024 * 1024:
                raise SetupError("内核下载超过大小限制。")
            destination.write_bytes(data)
            return
        except (OSError, TimeoutError):
            pass
    curl = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if curl:
        command = [curl, "--disable", "--fail", "--silent", "--show-error", "--location",
                   "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "5",
                   "--retry", "1", "--connect-timeout", "10", "--max-time", "30",
                   "--max-filesize", str(100 * 1024 * 1024), "--user-agent", "ai-flight-detector",
                   "--output", destination]
        if proxy:
            command += ["--proxy", proxy, "--noproxy", ""]
        run_checked(command + ["--url", url], timeout=80)
    else:
        raise SetupError("无法下载官方内核；网络不可达且没有 curl 后备。")


def extract_verified(archive, asset, target):
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != asset["digest"].split(":", 1)[1].lower():
        raise SetupError("内核 SHA-256 校验失败，未安装或执行。")
    if asset["name"].endswith(".zip"):
        with zipfile.ZipFile(archive) as package:
            executables = [info for info in package.infolist() if info.filename.endswith(".exe")]
            if len(executables) != 1 or executables[0].file_size > 200 * 1024 * 1024:
                raise SetupError("内核压缩包结构异常。")
            # Do not extract arbitrary archive paths.
            target.write_bytes(package.read(executables[0]))
    else:
        with gzip.open(archive, "rb") as stream:
            data = stream.read(200 * 1024 * 1024 + 1)
        if len(data) > 200 * 1024 * 1024:
            raise SetupError("解压后的内核超过大小限制。")
        target.write_bytes(data)
    if os.name != "nt":
        target.chmod(0o700)


def ensure_kernel(python, explicit=None, proxy=None):
    command = [str(python), "-X", "utf8", str(DETECTOR), "--discover"]
    if explicit:
        command += ["--kernel", explicit]
    found = subprocess.run(command, capture_output=True, timeout=120, creationflags=FLAGS)
    if not found.returncode:
        return json.loads(found.stdout.decode("utf-8"))["path"]
    if explicit:
        raise SetupError("指定内核无法运行；未擅自替换该路径。")
    print("未找到可用内核，正在自动下载官方 Mihomo 并校验…", flush=True)
    folder = ROOT / "kernels"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="install-", dir=folder) as temporary:
        work = Path(temporary)
        metadata = work / "release.json"
        download(RELEASE_API, metadata, proxy)
        release = json.loads(metadata.read_text(encoding="utf-8"))
        machine = os.environ.get("PROCESSOR_ARCHITEW6432") or platform.machine()
        asset = choose_asset(release, platform.system(), machine)
        archive = work / "archive"
        download(asset["browser_download_url"], archive, proxy)
        name = "mihomo.exe" if os.name == "nt" else "mihomo"
        binary = work / name
        extract_verified(archive, asset, binary)
        checked = run_checked([binary, "-v"], timeout=10)
        if b"mihomo" not in checked.stdout.lower() and b"clash meta" not in checked.stdout.lower():
            raise SetupError("下载的内核版本验证失败。")
        target = folder / name
        binary.replace(target)
        (folder / "download.json").write_text(json.dumps({"asset": asset["name"], "digest": asset["digest"],
            "release": release.get("tag_name")}, indent=2), encoding="utf-8")
        return str(target)


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--functional", choices=["antigravity"], help="实际生成及代理路径核对")
    parser.add_argument("--no-direct-download", action="store_true")
    parser.add_argument("--kernel")
    parser.add_argument("--download-proxy")
    args, rest = parser.parse_known_args(argv)
    try:
        # This guard applies to preparation too, not just subscription downloads.
        if args.no_direct_download and not args.download_proxy:
            raise SetupError("禁止直连下载时需要已有下载代理；请提供 --download-proxy。")
        python = ensure_python(args.download_proxy)
        if not shutil.which("curl.exe" if os.name == "nt" else "curl"):
            raise SetupError("执行环境未提供系统 curl，自动准备无法继续。")
        kernel = ensure_kernel(python, args.kernel, args.download_proxy)
        if args.setup_only:
            print("运行环境和内核已自动准备完成。", flush=True)
            return 0
        entry = DETECTOR.with_name("functional.py") if args.functional else DETECTOR
        command = [str(python), "-X", "utf8", str(entry), *rest, "--kernel", kernel]
        if args.download_proxy:
            command += ["--download-proxy", args.download_proxy]
        elif not args.no_direct_download:
            command += ["--allow-direct-download"]
        return subprocess.call(command, stdout=sys.stdout, stderr=sys.stderr, creationflags=FLAGS)
    except KeyboardInterrupt:
        return 130
    except (SetupError, OSError, ValueError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        print(str(exc) if isinstance(exc, SetupError) else f"自动准备失败（{type(exc).__name__}）；未执行不完整的下载文件。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
