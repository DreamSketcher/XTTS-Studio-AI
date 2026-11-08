# Runtime Dependency Security Baseline

**Baseline date:** 2026-11-08 (updated after dependency security re-review)  
**Python:** 3.11  
**Target:** Windows 10/11 x64

## Required versions

- `torch==2.2.2`
- `torchaudio==2.2.2`
- `torchvision==0.17.2`
- `transformers==4.38.2`
- `TTS==0.22.0`
- `nltk==3.10.4`
- `cryptography==50.0.0`

`diskcache` is not a direct runtime dependency and was removed. XTTS Studio does not use its pickle-backed cache API.

## Audit command

```bash
python tools/pip_audit_gate.py \
  --requirements requirements.txt \
  --allowlist .security/pip-audit-allowlist.yml
```

The gate runs `pip-audit`, resolves each finding's severity from OSV, and applies the policy from TASK-001: Critical/High fail unless listed in `.security/pip-audit-allowlist.yml`; Medium/Low warn; expired allowlist entries fail. CI runs this exact gate. New High/Critical CVEs not present in the allowlist fail the build.

## Documented exceptions

The frozen ML stack (`torch==2.2.2`, `transformers==4.38.2`) carries known advisories that cannot be removed without breaking the XTTS v2 + RVC stack. On 2026-11-08 all non-ML-stack findings were eliminated by version bumps (`aiohttp 3.14.4`, `anyio 4.14.2`, `certifi 2026.10.18`, `cryptography 50.0.0`, `filelock 4.2.1`, `fsspec 2026.6.0`, `hydra-core 1.3.8`, `msgpack 1.2.3`, `multidict 6.9.1`, `nltk 3.10.4`, `pillow 13.0.0`, `urllib3 2.8.0`, `Werkzeug 3.1.9`) — the allowlist now covers only the frozen stack. Each is a narrow, dated, documented exception recorded in `.security/pip-audit-allowlist.yml` with `reason`, `expires_at` and `issue_link`, and explained in [SECURITY.md](./SECURITY.md). Two representative classes:

- **`torch` load/`weights_only` RCE (e.g. CVE-2025-32434, CVE-2026-24747):** mitigated by the trust model — only project-owned/pinned XTTS models and RVC `.pth` under user-confirmed SHA-256 trust are loaded; embedding caches use `weights_only=True`; no attacker-controlled checkpoint is loaded.
- **`torch` JIT/Inductor/distributed/quant/RNN-ops and unused `transformers` model classes:** the vulnerable code paths are not exercised (eager inference only; only XTTS v2 loaded, no `trust_remote_code` on remote repos).

`expires_at` (quarterly) is a re-evaluation trigger, not a formality: on expiry CI turns red again until each entry is renewed or resolved. The list must not be expanded to additional advisory IDs without a separate per-CVE threat analysis and a new expiry date.

## Hash-locked runtime graph (TASK-017)

For reproducible installs, `requirements.lock` exists: the full resolved dependency
graph with SHA-256 hashes. `requirements.txt` remains the **source of truth for versions**;
`requirements.lock` is for reproducibility (`pip install --require-hashes -r requirements.lock`).
The lock is generated via `python tools/generate_requirements_lock.py` (uv or pip-tools) and
checked in CI (`tools/check_requirements_lock.py`): if `requirements.txt` changed but the
lock did not, CI reminds you to regenerate. `fairseq`/`rvc-python` are absent from the lock
(they are installed separately via `--no-deps`, see requirements.txt).
