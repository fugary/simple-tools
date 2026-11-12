#!/usr/bin/env python3
"""Audit lesson cue audio files for duration, amplitude health, and optional local Whisper ASR match."""
import argparse
import array
import difflib
import hashlib
from importlib.util import find_spec
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import time
import wave


def resolve(base: Path, path_str: str) -> Path:
    p = Path(path_str).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()


def normalize_text(text: str) -> str:
    text = text.lower().replace("—", " ").replace("-", " ").replace("’", "'")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def audio_stats(path: Path, ffmpeg: str = "ffmpeg") -> tuple[float, float, float]:
    """Return (duration_sec, peak_abs_0_1, rms_0_1) for WAV or FFmpeg-supported audio."""
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            width = wf.getsampwidth()
            channels = wf.getnchannels()
            if frames <= 0 or rate <= 0 or width != 2:
                raw = subprocess.check_output(
                    [ffmpeg, "-v", "error", "-i", str(path), "-ar", "24000", "-ac", "1", "-f", "s16le", "-"]
                )
                rate, channels = 24000, 1
            else:
                raw = wf.readframes(frames)
    else:
        raw = subprocess.check_output(
            [ffmpeg, "-v", "error", "-i", str(path), "-ar", "24000", "-ac", "1", "-f", "s16le", "-"]
        )
        rate, channels = 24000, 1

    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if sys.byteorder != "little":
        samples.byteswap()
    n = len(samples)
    if n == 0:
        return 0.0, 0.0, 0.0
    dur = (n / channels) / float(rate)
    peak = max(abs(s) for s in samples) / 32768.0
    sq_sum = sum((s / 32768.0) ** 2 for s in samples)
    rms = math.sqrt(sq_sum / n)
    return dur, peak, rms


def find_whisper_model(explicit: str | None) -> str | None:
    if explicit:
        p = Path(explicit).expanduser()
        return str(p.resolve(strict=True)) if p.exists() else explicit
    env_model = os.environ.get("WHISPER_MODEL_PATH")
    if env_model:
        p = Path(env_model).expanduser()
        return str(p.resolve(strict=True)) if p.exists() else env_model
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
    roots = [
        Path(os.environ.get("HF_HUB_CACHE", cache / "hub")),
        Path.home() / "Library/Containers/com.theoracleguy.openvox/Data/Library/Application Support/huggingface/hub",
    ]
    for root in roots:
        for snap in sorted(root.glob("models--*whisper*/snapshots/*")):
            if not (snap / "config.json").is_file():
                continue
            has_weights = any(
                w.is_file() and w.stat().st_size > 1_000_000
                for pattern in ("*.safetensors", "*.npz", "*.bin")
                for w in snap.glob(pattern)
            )
            if has_weights:
                return str(snap)
    return None


def import_mlx_whisper():
    if find_spec("mlx_whisper") is None:
        packages = Path("/Applications/OpenVox – Local Voice AI.app/Contents/Resources/site-packages")
        extension = "core" + (sysconfig.get_config_var("EXT_SUFFIX") or ".so")
        if not (packages / "mlx" / extension).is_file():
            return None
        sys.path.insert(0, str(packages))
    try:
        import mlx_whisper
        return mlx_whisper
    except ImportError:
        return None


def audit_manifest(
    manifest_path: Path,
    *,
    ffmpeg: str = "ffmpeg",
    wave_only: bool = False,
    whisper_model: str | None = None,
    min_sim: float = 0.72,
    min_dur: float = 0.35,
    max_dur: float = 25.0,
    min_peak: float = 0.03,
    min_rms: float = 0.004,
) -> dict:
    manifest_abs = manifest_path.resolve()
    data = json.loads(manifest_abs.read_text(encoding="utf-8"))
    cues = data["cues"] if isinstance(data, dict) else data
    base_dir = manifest_abs.parent

    # Make bundled or sibling ffmpeg discoverable for mlx_whisper audio loading.
    ff_dir = str(Path(ffmpeg).expanduser().resolve().parent) if "/" in ffmpeg or "\\" in ffmpeg else ""
    if ff_dir and ff_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ff_dir + os.pathsep + os.environ.get("PATH", "")

    asr_mod = None
    model_ref = None
    asr_status = "skipped_wave_only"
    if not wave_only:
        asr_mod = import_mlx_whisper()
        model_ref = find_whisper_model(whisper_model)
        if asr_mod is None:
            asr_status = "skipped_missing_mlx_whisper"
        elif model_ref is None:
            asr_status = "skipped_missing_whisper_model"
        else:
            asr_status = f"enabled:{model_ref}"

    seen_asr: dict[str, str] = {}
    hard_errors: list[dict] = []
    asr_warnings: list[dict] = []
    records: list[dict] = []
    t0 = time.time()

    for idx, cue in enumerate(cues, 1):
        rel = cue.get("audio")
        if not rel:
            hard_errors.append({"cue": idx, "issue": "missing_audio_field", "en": cue.get("en", "")})
            continue
        wav_path = resolve(base_dir, rel)
        if not wav_path.is_file() or wav_path.stat().st_size <= 44:
            hard_errors.append({"cue": idx, "issue": "missing_or_empty_file", "path": str(wav_path)})
            continue

        dur, peak, rms = audio_stats(wav_path, ffmpeg=ffmpeg)
        if not (min_dur <= dur <= max_dur) or peak < min_peak or peak > 0.999 or rms < min_rms:
            hard_errors.append({
                "cue": idx,
                "issue": "audio_level_or_duration",
                "dur": round(dur, 2),
                "peak": round(peak, 3),
                "rms": round(rms, 4),
                "en": cue.get("en", ""),
                "path": str(wav_path),
            })

        expected = (cue.get("spoken") or cue.get("en") or "").strip()
        rec = {"cue": idx, "dur": round(dur, 2), "peak": round(peak, 3), "rms": round(rms, 4), "expected": expected}

        if asr_mod is not None and model_ref is not None:
            h = hashlib.sha256(wav_path.read_bytes()).hexdigest()
            if h not in seen_asr:
                res = asr_mod.transcribe(
                    str(wav_path),
                    path_or_hf_repo=model_ref,
                    language="en",
                    condition_on_previous_text=False,
                    verbose=False,
                )
                seen_asr[h] = (res.get("text") or "").strip()
            hyp = seen_asr[h]
            ratio = difflib.SequenceMatcher(None, normalize_text(expected), normalize_text(hyp)).ratio()
            rec["asr"] = hyp
            rec["similarity"] = round(ratio, 3)
            if ratio < min_sim:
                asr_warnings.append({
                    "cue": idx,
                    "issue": "low_asr_similarity",
                    "similarity": round(ratio, 3),
                    "dur": round(dur, 2),
                    "expected": expected,
                    "en": cue.get("en", ""),
                    "asr": hyp,
                    "path": str(wav_path),
                })

        records.append(rec)

    sims = [r["similarity"] for r in records if "similarity" in r]
    return {
        "manifest": str(manifest_abs),
        "total_cues": len(cues),
        "asr_status": asr_status,
        "unique_asr_files": len(seen_asr),
        "elapsed_sec": round(time.time() - t0, 1),
        "hard_error_count": len(hard_errors),
        "asr_warning_count": len(asr_warnings),
        "min_similarity": min(sims) if sims else None,
        "mean_similarity": round(sum(sims) / len(sims), 4) if sims else None,
        "hard_errors": hard_errors,
        "asr_warnings": asr_warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="lesson.json / narrated.json path")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--wave-only", action="store_true", help="Only verify WAV/audio readability, duration, peak, and RMS")
    parser.add_argument("--whisper-model", help="Local Whisper directory or HF repo override")
    parser.add_argument("--min-similarity", type=float, default=0.72)
    parser.add_argument("--min-dur", type=float, default=0.35)
    parser.add_argument("--max-dur", type=float, default=25.0)
    parser.add_argument("--min-peak", type=float, default=0.03)
    parser.add_argument("--min-rms", type=float, default=0.004)
    parser.add_argument("--fail-on-asr", action="store_true", help="Exit non-zero if any cue scores below --min-similarity")
    parser.add_argument("--report", type=Path, help="Optional path to save full JSON audit report")
    args = parser.parse_args()

    summary = audit_manifest(
        args.manifest,
        ffmpeg=args.ffmpeg,
        wave_only=args.wave_only,
        whisper_model=args.whisper_model,
        min_sim=args.min_similarity,
        min_dur=args.min_dur,
        max_dur=args.max_dur,
        min_peak=args.min_peak,
        min_rms=args.min_rms,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["hard_error_count"] > 0:
        return 1
    if args.fail_on_asr and summary["asr_warning_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        sys.exit(str(exc))
