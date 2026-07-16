# Security Policy

## Supported versions

Security fixes are provided for the latest published XTTS Studio release. Users should update to the latest release before reporting a reproducible issue.

## Reporting a vulnerability

Do **not** open a public GitHub issue for an unpatched vulnerability.

Use GitHub Private Vulnerability Reporting for this repository:

`Security` → `Advisories` → `Report a vulnerability`

Include:

- affected version and commit;
- Windows version and CPU/GPU configuration;
- minimal reproduction steps;
- impact and required attacker capabilities;
- logs with API keys, personal text, voice references and local paths removed;
- suggested remediation, if available.

The maintainer should acknowledge a report within 7 days. Disclosure should be coordinated until a fixed release is available. No guarantee of bounty or monetary compensation is made.

## Security boundaries

XTTS Studio processes voice references, generated audio and local models with the permissions of the current Windows user. Treat third-party `.pth`, `.index`, GGUF, ZIP and wheel files as untrusted.

- Only install models from sources you trust.
- A SHA-256 checksum proves integrity relative to a manifest; it does not prove the publisher's identity.
- Cloud AI providers receive the text sent to them. Local XTTS/RVC generation does not require sending voice or text to a cloud provider.
- Never attach `gpt_settings.json`, histories, voice references or generated private material to a public issue.

## Release security requirements

A production release is expected to have:

1. a signed update manifest verified before update application;
2. path-confined updater operations;
3. a signed Windows artifact and published SHA-256 checksums;
4. a generated SBOM;
5. dependency vulnerability review;
6. Windows smoke tests;
7. no plaintext API credentials;
8. an explicit trust decision before loading unsigned pickle/PyTorch checkpoints.
