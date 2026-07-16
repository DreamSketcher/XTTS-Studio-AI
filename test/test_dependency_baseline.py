from pathlib import Path

from engine.env_core import torch_setup

ROOT = Path(__file__).resolve().parents[1]


def _requirements() -> dict[str, str]:
    result = {}
    for raw in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        result[name.lower()] = version
    return result


def test_security_baseline_versions_are_aligned():
    req = _requirements()
    assert req["torch"] == torch_setup.TORCH_VERSION == "2.2.2"
    assert req["torchaudio"] == torch_setup.TORCHAUDIO_VERSION == "2.2.2"
    assert req["torchvision"] == torch_setup.TORCHVISION_VERSION == "0.17.2"
    assert req["transformers"] == "4.38.2"
    assert req.get("tts") == "0.22.0" or req.get("coqui-tts") == "0.22.0"
    assert req["nltk"] == "3.9.4"


def test_pickle_diskcache_dependency_is_absent():
    assert "diskcache" not in _requirements()


def test_cuda_baseline_is_current():
    assert torch_setup.TORCH_MIN_CUDA == (12, 8)
    assert "cu128" in torch_setup._TORCH_INDEX_URLS
