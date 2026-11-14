#!/usr/bin/env python3
"""
check_environment.py
检查 Remotion 双语教学视频技能运行所需的 Node.js、npm、npx 与 FFmpeg 环境。
"""
from __future__ import annotations
import re
import shutil
import subprocess
import sys


def get_cmd_version(cmd: list[str]) -> str | None:
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip().splitlines()[0]
    except Exception:
        return None
    return None


def main() -> int:
    ok = True
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    npx_path = shutil.which("npx")
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    print("=== Remotion Study Video Environment Check ===")

    if node_path:
        ver = get_cmd_version([node_path, "-v"]) or ""
        m = re.match(r"v?(\d+)\.", ver)
        major = int(m.group(1)) if m else 0
        status = "OK" if major >= 18 else "WARN (<18)"
        if major < 18:
            ok = False
        print(f"[node]    {status:10s} {node_path} ({ver})")
    else:
        print("[node]    MISSING    Please install Node.js >= 18")
        ok = False

    for name, path in [("npm", npm_path), ("npx", npx_path), ("ffmpeg", ffmpeg_path), ("ffprobe", ffprobe_path)]:
        if path:
            ver = get_cmd_version([path, "-version" if "ff" in name else "-v"]) or ""
            print(f"[{name:7s}] OK         {path} ({ver[:60]})")
        else:
            print(f"[{name:7s}] MISSING")
            ok = False

    if ok:
        print("\nEnvironment ready.")
        return 0
    print("\nEnvironment incomplete. Install missing tools before running Remotion.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
