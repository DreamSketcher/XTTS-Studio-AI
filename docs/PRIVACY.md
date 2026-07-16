# Privacy Notice

Last updated: 2026-07-15

XTTS Studio is a portable desktop application. Its core XTTS and RVC processing is designed to run locally.

## Data stored locally

Depending on enabled features, the application may store:

- voice reference files and processed references;
- generated WAV/MP3 files;
- generation and chat history;
- pronunciation rules, presets and UI settings;
- downloaded XTTS, RVC and GGUF models;
- model previews and caches;
- diagnostic logs;
- AI provider configuration and credentials.

These files remain on the user's computer unless the user uploads, synchronizes or shares them. Portable folders may be copied by backup and cloud-sync software configured by the user.

## Network activity

Network access may occur for:

- update checks and update downloads from GitHub;
- model catalog queries and model/preview downloads;
- installation of Python packages and runtime components;
- cloud AI requests to the selected provider;
- links explicitly opened in the system browser.

When a cloud AI provider is selected, prompts, conversation context and text selected for AI processing are sent to that provider. Their privacy policy and retention rules apply. Voice references are not intentionally sent to cloud AI providers by the normal text-chat and text-improvement flows.

Local XTTS synthesis, local RVC conversion and an already-downloaded local GGUF model can operate without sending content to a cloud AI provider.

## Credentials

API credentials are sensitive. A hardened release must store them through Windows-protected credential storage rather than plaintext application settings. Do not share settings files or include them in diagnostics.

## Diagnostics and reports

Issue reports are user-initiated. Review diagnostic text before submission. Remove:

- API keys and authorization headers;
- private prompts and chat history;
- names and local filesystem paths;
- voice references and generated private audio.

## Deletion

XTTS Studio has no central user account or server-side deletion endpoint. Local data can be removed by deleting the corresponding history, output, reference, model, cache and settings files from the portable application directory. Close the application before manual deletion.

## Third parties

Potential third parties include GitHub, package indexes, model hosts, voice-model catalogs and the cloud AI provider selected by the user. XTTS Studio does not control their logging or retention practices.
