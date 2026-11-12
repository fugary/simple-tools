#!/usr/bin/env python3
"""Read-only environment capability check for image-motion."""
import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _pkg_version(dist_name: str, mod_name: str | None = None) -> str | None:
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        target = mod_name or dist_name
        if importlib.util.find_spec(target) is not None:
            return "installed"
        return None


def detect_step2_depth_backends() -> dict:
    """Inspect optional Step 2 Depth Anything V2 runtime capabilities."""
    onnxruntime_ver = _pkg_version("onnxruntime")
    hf_hub_ver = _pkg_version("huggingface-hub", "huggingface_hub")
    torch_ver = _pkg_version("torch")
    transformers_ver = _pkg_version("transformers")

    cuda_available = False
    mps_available = False
    if torch_ver is not None:
        try:
            import torch  # type: ignore

            cuda_available = bool(torch.cuda.is_available())
            mps_backend = getattr(getattr(torch, "backends", None), "mps", None)
            mps_available = bool(mps_backend is not None and mps_backend.is_available())
        except Exception:
            pass

    onnx_providers: list[str] = []
    if onnxruntime_ver is not None:
        try:
            import onnxruntime as ort  # type: ignore

            onnx_providers = list(ort.get_available_providers())
        except Exception:
            onnx_providers = []

    backends_available: list[str] = []
    if onnxruntime_ver is not None:
        backends_available.append("onnx")
    if torch_ver is not None and transformers_ver is not None:
        backends_available.append("transformers")

    env_onnx = os.environ.get("DEPTH_ANYTHING_ONNX", "").strip()
    return {
        "onnxruntime": onnxruntime_ver,
        "huggingface_hub": hf_hub_ver,
        "torch": torch_ver,
        "transformers": transformers_ver,
        "cuda_available": cuda_available,
        "mps_available": mps_available,
        "onnx_providers": onnx_providers,
        "env_onnx_path": env_onnx or None,
        "backends_available": backends_available,
    }


def resolve_ffmpeg(requested: str):
    found = shutil.which(requested)
    if not found and Path(requested).is_file():
        found = str(Path(requested).resolve())
    if not found:
        try:
            import imageio_ffmpeg
            found = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            found = None
    if not found:
        return None, ""
    try:
        res = subprocess.run([found, "-version"], capture_output=True, text=True, timeout=15)
        return found, (res.stdout + "\n" + res.stderr).splitlines()[0] if (res.stdout or res.stderr) else ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return found, str(exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    packages = {}
    for pkg in ("Pillow", "numpy", "imageio-ffmpeg"):
        try:
            packages[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            packages[pkg] = None

    ffmpeg_path, ffmpeg_ver = resolve_ffmpeg(args.ffmpeg)
    ok = (
        sys.version_info >= (3, 9)
        and packages["Pillow"] is not None
        and packages["numpy"] is not None
        and ffmpeg_path is not None
    )
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": packages,
        "ffmpeg": ffmpeg_path,
        "ffmpeg_version": ffmpeg_ver,
        "ready": ok,
        "depth_anything_step2": detect_step2_depth_backends(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
