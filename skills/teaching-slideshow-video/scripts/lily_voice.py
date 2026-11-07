"""Local Lily voice used by the teaching slideshow narrator."""
import hashlib
from importlib.metadata import version
from importlib.util import find_spec
import json
import os
from pathlib import Path
import sys
import sysconfig
import tempfile
import wave

ASSETS = Path(__file__).resolve().parents[1] / 'assets'


def settings():
    profile = json.loads((ASSETS / 'lily.json').read_text())
    model_name = profile['model']
    configured = os.environ.get('LILY_MODEL_PATH')
    if configured:
        model_path = Path(configured).expanduser().resolve(strict=True)
    else:
        cache = Path(os.environ.get('HF_HOME', Path.home() / '.cache/huggingface'))
        roots = [Path(os.environ.get('HF_HUB_CACHE', cache / 'hub')),
                 Path.home() / 'Library/Containers/com.theoracleguy.openvox/Data/Library/Application Support/huggingface/hub']
        snapshots = (p for root in roots for p in sorted(root.glob('models--*--' + model_name + '/snapshots/*'))
                     if (p / 'config.json').is_file())
        model_path = next(snapshots, None)
        if model_path is None:
            raise FileNotFoundError(f'Set LILY_MODEL_PATH to a local {model_name} snapshot.')
    reference = (ASSETS / profile['generate']['ref_audio']).resolve(strict=True)
    options = dict(profile['generate'], ref_audio=str(reference))
    fingerprint = dict(model=str(model_path), reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                       options=profile['generate'], peak=profile['postprocess']['peak_ceiling'],
                       runtime=version('mlx-audio'))
    return model_path, options, fingerprint


def generate_missing(items, cache):
    if find_spec('mlx_audio') is None:
        # OpenVox can supply the local MLX runtime when its Python ABI matches.
        packages = Path('/Applications/OpenVox – Local Voice AI.app/Contents/Resources/site-packages')
        extension = 'core' + sysconfig.get_config_var('EXT_SUFFIX')
        if not (packages / 'mlx' / extension).is_file():
            raise RuntimeError('Lily requires an mlx-audio environment or a matching OpenVox Python runtime.')
        sys.path.insert(0, str(packages))
    model_path, options, fingerprint = settings()
    model = None
    for cue, text in items:
        descriptor = json.dumps([text, fingerprint], ensure_ascii=False, sort_keys=True)
        dest = cache / (hashlib.sha256(descriptor.encode()).hexdigest() + '.wav')
        if not dest.is_file():
            import numpy as np
            if model is None:
                from mlx_audio.tts.utils import load_model
                model = load_model(str(model_path))
            result = next(model.generate(text=text, **options))
            samples = np.asarray(result.audio).reshape(-1)
            if samples.size == 0 or not np.isfinite(samples).all():
                raise ValueError('Invalid synthesized samples')
            scale = min(1., fingerprint['peak'] / max(.001, float(np.abs(samples).max())))
            with tempfile.TemporaryDirectory(dir=cache) as staging:
                part = Path(staging) / 'audio.wav'
                with wave.open(str(part), 'wb') as wav:
                    wav.setparams((1, 2, result.sample_rate, 0, 'NONE', 'not compressed'))
                    wav.writeframes((samples * scale * 32767).astype('<i2').tobytes())
                part.replace(dest)
        cue['audio'] = str(dest)
