# Public Repository Manifest

This document defines the allowlist for the clean public history. The server
working tree is authoritative for source code, but presence on disk is not
sufficient for inclusion.

## Intentionally included

- Root application Python modules and `new_architecture/` application, service,
  model, migration, and ingestion source after redacted configuration review.
- HTML, CSS, and JavaScript application assets under `templates/` and `static/`.
- Python tests and the two-row synthetic mass-answer CSV/XLSX fixture.
- Benchmark source, methodology, and explicitly synthetic input fixtures, but
  no run output.
- `README.md`, `AGENTS.md`, and authored Markdown/text documentation outside
  machine-captured runtime and obsolete local-audit directories.
- `package.json`, `scenarios.json`, safe environment templates, `.gitignore`,
  and reviewed scripts.
- Project-local reusable instructions under `.agents/skills/`.
- Exactly these directory placeholders:
  - `data_insertion_chunks/DOCUMENTS/.gitkeep`
  - `data_insertion_chunks/CHUNKS/General_FAQ/.gitkeep`
  - `benchmarks/results/.gitkeep`

Every committed path is enumerated in `/root/RagBot-public-include.txt` before
staging.

## Intentionally excluded

- `.env`, `.env.server_git`, other secret variants, and legacy `env.example`.
- `.idea/`, `.codex/`, `.qdrant-initialized`, `t -q`, caches, bytecode, logs,
  virtual environments, editor files, and temporary files.
- Root private FAQ CSV/Excel/PDF exports and every real source document below
  `data_insertion_chunks/DOCUMENTS/`.
- Generated chunks below `data_insertion_chunks/CHUNKS/`, except the approved
  `.gitkeep` path.
- Raw benchmark results and machine/runtime captures.
- Qdrant, MinIO, PostgreSQL, Docker-volume, upload, download, and snapshot data.
- Downloaded Qdrant UI/dependency trees and service binaries.
- Hugging Face caches, large model weights, and transfer archives.
- `chitchat_guardrail.pt`: runtime-required but excluded because its license,
  provenance, training-data audit, retraining procedure, and publication
  approval are not documented.
- Obsolete local cleanup/audit artifacts that are not useful after the clean
  one-commit history is created.

Ambiguous paths remain excluded until a maintainer documents their purpose and
completes privacy, secret, license, and size review.
