"""Optional Step 2 monocular depth estimation via Depth Anything V2.

Supports two lightweight runtime backends when optional dependencies are installed:
- ONNX Runtime (`onnxruntime`, optionally with CoreML on Apple Silicon / CUDA / CPU)
- HuggingFace Transformers (`torch` + `transformers`, supporting CUDA / MPS / CPU)

Outputs an 8-bit grayscale PNG compatible with `DepthParallaxEffect`
(white = near camera, black = far horizon).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

DEFAULT_HF_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
DEFAULT_ONNX_REPO = "onnx-community/depth-anything-v2-small"
DEFAULT_ONNX_FILES = ("onnx/model_quantized.onnx", "onnx/model.onnx", "model.onnx")
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
VALID_BACKENDS = ("auto", "onnx", "transformers")
_BICUBIC = getattr(getattr(Image, "Resampling", Image), "BICUBIC")


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _round_multiple_of_14(value: float) -> int:
    return max(14, int(round(value / 14.0)) * 14)


def prepare_vit_input(
    image: Image.Image,
    max_size: int = 518,
    exact_size: tuple[int, int] | None = None,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Resize and ImageNet-normalize an RGB image for Depth Anything V2 ViT inference.

    Returns ``(nchw_float32_tensor, (orig_width, orig_height))``.
    """
    if max_size < 14:
        raise ValueError(f"max_size must be >= 14, got {max_size}")

    rgb = image.convert("RGB")
    orig_w, orig_h = rgb.size
    if orig_w <= 0 or orig_h <= 0:
        raise ValueError(f"Invalid image dimensions: {rgb.size}")

    if exact_size is not None:
        tw, th = int(exact_size[0]), int(exact_size[1])
        if tw < 14 or th < 14:
            raise ValueError(f"exact_size dimensions must be >= 14, got {exact_size}")
    else:
        scale = float(max_size) / float(max(orig_w, orig_h))
        tw = _round_multiple_of_14(orig_w * scale)
        th = _round_multiple_of_14(orig_h * scale)

    if (tw, th) != (orig_w, orig_h):
        resized = rgb.resize((tw, th), _BICUBIC)
    else:
        resized = rgb

    arr = np.asarray(resized, dtype=np.float32) / 255.0
    norm = (arr - IMAGENET_MEAN) / IMAGENET_STD
    nchw = np.ascontiguousarray(norm.transpose(2, 0, 1)[None, ...], dtype=np.float32)
    return nchw, (orig_w, orig_h)


def normalize_depth_to_uint8(
    pred: np.ndarray,
    orig_size: tuple[int, int],
    invert: bool = False,
) -> Image.Image:
    """Convert raw predicted depth tensor/array to an ``L``-mode PNG sized to ``orig_size``."""
    arr = np.asarray(pred, dtype=np.float32)
    while arr.ndim > 2:
        if arr.shape[0] == 1:
            arr = arr[0]
        elif arr.shape[-1] == 1:
            arr = arr[..., 0]
        else:
            arr = arr[0]
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError(f"Expected 2D depth prediction, got shape {np.asarray(pred).shape}")

    finite = np.isfinite(arr)
    if not np.any(finite):
        norm = np.full(arr.shape, 0.5, dtype=np.float32)
    else:
        d_min = float(np.min(arr[finite]))
        d_max = float(np.max(arr[finite]))
        cleaned = np.where(finite, arr, d_min)
        span = d_max - d_min
        if span < 1e-8:
            norm = np.full(arr.shape, 0.5, dtype=np.float32)
        else:
            norm = np.clip((cleaned - d_min) / span, 0.0, 1.0).astype(np.float32)

    if invert:
        norm = 1.0 - norm

    orig_w, orig_h = int(orig_size[0]), int(orig_size[1])
    if (arr.shape[1], arr.shape[0]) != (orig_w, orig_h):
        float_img = Image.fromarray(norm, mode="F")
        norm_resized = np.asarray(float_img.resize((orig_w, orig_h), _BICUBIC), dtype=np.float32)
        norm = np.clip(norm_resized, 0.0, 1.0)

    u8 = np.clip(np.round(norm * 255.0), 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(u8, mode="L")


def resolve_onnx_providers(ort_module: Any) -> list[str]:
    """Select preferred available ONNX Runtime execution providers."""
    try:
        available = list(ort_module.get_available_providers())
    except Exception:
        return ["CPUExecutionProvider"]

    preferred = [
        "CoreMLExecutionProvider",
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ]
    selected = [p for p in preferred if p in available]
    return selected or (available if available else ["CPUExecutionProvider"])


def _resolve_onnx_model_path(
    onnx_path: str | Path | None = None,
    model_id: str | None = None,
) -> Path:
    if onnx_path is not None:
        resolved = Path(onnx_path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"ONNX depth model not found: {resolved}")
        return resolved

    env_path = os.environ.get("DEPTH_ANYTHING_ONNX", "").strip()
    if env_path:
        resolved = Path(env_path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"DEPTH_ANYTHING_ONNX file not found: {resolved}")
        return resolved

    if model_id and model_id.lower().endswith(".onnx"):
        candidate = Path(model_id).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"ONNX model file not found: {candidate}")

    if not _has_module("huggingface_hub"):
        raise RuntimeError(
            "No local ONNX model path provided (--onnx-path or DEPTH_ANYTHING_ONNX), "
            "and `huggingface_hub` is not installed to download one automatically."
        )

    from huggingface_hub import hf_hub_download  # type: ignore

    repo_id = model_id or DEFAULT_ONNX_REPO
    last_err: Exception | None = None
    for filename in DEFAULT_ONNX_FILES:
        try:
            downloaded = hf_hub_download(repo_id=repo_id, filename=filename)
            return Path(downloaded)
        except Exception as exc:  # pragma: no cover - network/hub lookup
            last_err = exc
    raise RuntimeError(
        f"Failed to download Depth Anything V2 ONNX weights from '{repo_id}'. "
        "Provide a local file via --onnx-path / DEPTH_ANYTHING_ONNX or switch to --backend transformers."
    ) from last_err


def _fixed_spatial_size(input_shape: Any) -> tuple[int, int] | None:
    if not isinstance(input_shape, (list, tuple)) or len(input_shape) != 4:
        return None
    h_dim, w_dim = input_shape[2], input_shape[3]
    if isinstance(h_dim, int) and isinstance(w_dim, int) and h_dim >= 14 and w_dim >= 14:
        return (w_dim, h_dim)
    return None


def estimate_depth_onnx(
    image: Image.Image,
    onnx_path: str | Path | None = None,
    model_id: str | None = None,
    input_size: int = 518,
    invert: bool = False,
) -> Image.Image:
    """Run Depth Anything V2 inference via `onnxruntime`."""
    try:
        import onnxruntime as ort  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "ONNX backend requires `onnxruntime` (e.g. `pip install onnxruntime`)."
        ) from exc

    resolved_model = _resolve_onnx_model_path(onnx_path=onnx_path, model_id=model_id)
    providers = resolve_onnx_providers(ort)
    session = ort.InferenceSession(str(resolved_model), providers=providers)
    inputs = session.get_inputs()
    if not inputs:
        raise RuntimeError(f"ONNX model '{resolved_model}' exposes no inputs")

    model_input = inputs[0]
    exact_size = _fixed_spatial_size(getattr(model_input, "shape", None))
    tensor, orig_size = prepare_vit_input(image, max_size=input_size, exact_size=exact_size)
    outputs = session.run(None, {model_input.name: tensor})
    if not outputs:
        raise RuntimeError(f"ONNX model '{resolved_model}' returned no outputs")
    return normalize_depth_to_uint8(outputs[0], orig_size=orig_size, invert=invert)


def _select_torch_device(torch_module: Any) -> str:
    if torch_module.cuda.is_available():
        return "cuda"
    mps_backend = getattr(getattr(torch_module, "backends", None), "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return "mps"
    return "cpu"


def estimate_depth_transformers(
    image: Image.Image,
    model_id: str | None = None,
    invert: bool = False,
) -> Image.Image:
    """Run Depth Anything V2 inference via HuggingFace `transformers` + `torch`."""
    try:
        import torch  # type: ignore
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Transformers backend requires `torch` and `transformers` "
            "(e.g. `pip install torch transformers`)."
        ) from exc

    rgb = image.convert("RGB")
    target_model = model_id or DEFAULT_HF_MODEL
    device = _select_torch_device(torch)
    processor = AutoImageProcessor.from_pretrained(target_model)
    model = AutoModelForDepthEstimation.from_pretrained(target_model)
    model.to(device)
    model.eval()

    inputs = processor(images=rgb, return_tensors="pt")
    device_inputs = {
        k: v.to(device) if hasattr(v, "to") else v
        for k, v in inputs.items()
    }
    with torch.no_grad():
        outputs = model(**device_inputs)
    pred = outputs.predicted_depth.detach().cpu().numpy()
    return normalize_depth_to_uint8(pred, orig_size=rgb.size, invert=invert)


def select_backend(
    backend: str = "auto",
    onnx_path: str | Path | None = None,
) -> str:
    """Resolve `backend='auto'` to `'onnx'` or `'transformers'` based on installed runtimes."""
    if backend not in VALID_BACKENDS:
        raise ValueError(f"Unknown depth backend {backend!r}; expected one of {VALID_BACKENDS}")
    if backend != "auto":
        return backend

    has_ort = _has_module("onnxruntime")
    has_tf = _has_module("transformers") and _has_module("torch")
    has_local_onnx = onnx_path is not None or bool(os.environ.get("DEPTH_ANYTHING_ONNX", "").strip())

    if has_local_onnx:
        if not has_ort:
            raise RuntimeError(
                "Local ONNX depth weights were specified, but `onnxruntime` is not installed. "
                "Run `pip install onnxruntime`."
            )
        return "onnx"
    if has_tf:
        return "transformers"
    if has_ort:
        return "onnx"
    raise RuntimeError(
        "No Step 2 Depth Anything backend is installed. Install one of:\n"
        "  1) `pip install onnxruntime` (+ `--onnx-path model.onnx` or `pip install huggingface-hub`), or\n"
        "  2) `pip install torch transformers`.\n"
        "Alternatively, omit --auto-depth and use Step 1 synthetic depth (`horizon_y` + `foreground_regions`)."
    )


def estimate_depth(
    image_path: str | Path,
    output_path: str | Path | None = None,
    backend: str = "auto",
    onnx_path: str | Path | None = None,
    model_id: str | None = None,
    input_size: int = 518,
    invert: bool = False,
) -> Image.Image:
    """Estimate a 0..255 grayscale depth map for ``image_path`` and optionally save as PNG."""
    src_path = Path(image_path).expanduser().resolve()
    if not src_path.is_file():
        raise FileNotFoundError(f"Input image not found: {src_path}")

    chosen = select_backend(backend=backend, onnx_path=onnx_path)
    with Image.open(src_path) as im:
        if chosen == "onnx":
            depth_img = estimate_depth_onnx(
                im,
                onnx_path=onnx_path,
                model_id=model_id,
                input_size=input_size,
                invert=invert,
            )
        else:
            depth_img = estimate_depth_transformers(
                im,
                model_id=model_id,
                invert=invert,
            )

    if output_path is not None:
        out = Path(output_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        depth_img.save(out)
    return depth_img


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="Source RGB image")
    parser.add_argument("--output", required=True, type=Path, help="Destination grayscale depth PNG")
    parser.add_argument("--backend", default="auto", choices=VALID_BACKENDS)
    parser.add_argument("--onnx-path", type=Path, default=None, help="Optional local Depth Anything ONNX file")
    parser.add_argument("--model", default=None, help="Optional HF model ID or ONNX repo ID")
    parser.add_argument("--input-size", type=int, default=518, help="Max ViT input edge (ONNX dynamic mode)")
    parser.add_argument("--invert", action="store_true", help="Invert depth polarity (far=white, near=black)")
    args = parser.parse_args()

    depth_img = estimate_depth(
        image_path=args.image,
        output_path=args.output,
        backend=args.backend,
        onnx_path=args.onnx_path,
        model_id=args.model,
        input_size=args.input_size,
        invert=args.invert,
    )
    arr = np.asarray(depth_img, dtype=np.uint8)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "size": list(depth_img.size),
                "min": int(arr.min()),
                "max": int(arr.max()),
                "mean": round(float(arr.mean()), 2),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
