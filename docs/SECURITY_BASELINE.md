# Runtime Dependency Security Baseline

**Baseline date:** 2026-07-15  
**Python:** 3.11  
**Target:** Windows 10/11 x64

## Required versions

- `torch==2.11.0`
- `torchaudio==2.11.0`
- `torchvision==0.26.0`
- `transformers==5.13.1`
- `coqui-tts==0.27.5`
- `nltk==3.10.0`

`diskcache` is not a direct runtime dependency and was removed. XTTS Studio does not use its pickle-backed cache API.

## Audit command

```bash
pip-audit -r requirements.txt --no-deps --disable-pip \
  --ignore-vuln CVE-2025-3000
```

The command must report no unignored vulnerabilities. CI runs this exact gate. New findings fail the build.

## Temporary accepted advisory

### CVE-2025-3000 — PyTorch `torch.jit.script`

- **Package:** `torch==2.11.0`
- **Upstream fixed version:** none identified by the advisory database on the baseline date.
- **Reason a newer aligned release is not used:** the newest mutually published and tested Windows family is `torch==2.11.0`, `torchaudio==2.11.0`, `torchvision==0.26.0`. Moving only torch forward breaks the binary ABI alignment with torchaudio used by XTTS.
- **Exposure:** the reported issue concerns attacker-controlled use of `torch.jit.script` leading to memory corruption. XTTS Studio does not expose a service/API that accepts Python functions or TorchScript source for compilation.
- **Compensating controls:** community RVC `.pth` files require explicit trust bound to SHA-256; embedding caches use `weights_only=True` and a strict schema; network model downloads do not automatically execute TorchScript supplied by a remote caller.
- **Residual risk:** a malicious model or local attacker already able to modify runtime/model files may still target native ML parsing paths. Users must only trust known model sources.
- **Review deadline:** 2026-08-15, or immediately when a matching torch/torchaudio/torchvision family with an upstream fix is published.
- **Removal condition:** upgrade the aligned family and remove the CI ignore as soon as the advisory publishes a fixed compatible version.

This is a narrow, documented exception. It must not be expanded to additional advisory IDs without a separate threat analysis and expiry date.
