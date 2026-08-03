# Git Hygiene Guide

## Public repository policy

Commit only reviewed application source, tests, deliberately synthetic fixtures,
authored documentation, safe configuration templates, scripts, project-local
skills, dependency metadata, and required `.gitkeep` files.

Keep these items local:

- `.env` and every unapproved `.env.*` variant;
- real FAQ and customer documents;
- generated chunks, embeddings, and benchmark output;
- Qdrant, MinIO, PostgreSQL, and Docker runtime data;
- model weights without documented provenance and publication approval;
- logs, caches, downloaded dependencies/binaries, IDE files, and local Codex
  state.

## Why ignored files can remain visible

`.gitignore` is an admission policy for untracked files. It neither deletes a
local file nor removes a path already stored in the Git index or an older
commit. Adding an ignore rule after a private file was committed therefore does
not make the repository safe.

For ordinary index cleanup, preserve the local file with:

```bash
git rm --cached -- path/to/file
git rm -r --cached -- path/to/directory
```

That does not clean earlier commits. A repository that exposed private data in
history needs a coordinated history replacement and credential rotation where
applicable. Follow `CLEAN_HISTORY_MIGRATION.md` for this repository.

## Staging discipline

Do not use an unrestricted `git add .` for a public release. Build and review an
explicit path manifest, then stage from it:

```bash
git add --pathspec-from-file=/root/RagBot-public-include.txt
git diff --cached --name-only
git diff --cached --stat
```

Before committing, verify ignored behavior and prohibited paths:

```bash
git check-ignore -v .env data_insertion_chunks/DOCUMENTS/private.pdf
git check-ignore -v data_insertion_chunks/CHUNKS/General_FAQ/private.txt
git check-ignore -v benchmarks/results/private.json storage/private.bin
git diff --cached --name-only | sort
```

## Safe fixtures

Fixtures must be authored for tests, minimal, clearly labeled synthetic, and
free of copied customer or knowledge-base records. Invent names, identifiers,
questions, answers, endpoints, and credentials. Scan the file before staging
and review its staged diff. A private record does not become synthetic merely
because it is moved into `tests/fixtures/`.

## Environment templates

Create local configuration from the reviewed generated template:

```bash
cp .env.example.generated .env
```

Replace placeholders only in local `.env`. Never derive a public template from
the local environment file. The legacy `env.example` is intentionally excluded
because it contained literal sensitive configuration.

## Model artifacts

Model weights require a version, checksum, license, source/provenance record,
training-data privacy review, evaluation evidence, and documented provisioning
or retraining steps. The active `chitchat_guardrail.pt` is small and required by
the current runtime, but those publication prerequisites are absent, so it is
intentionally local-only. Provision an approved checkpoint before serving.

## Benchmark output

Commit benchmark code, methodology, schemas, and synthetic input fixtures.
Keep raw results, prompts, answers, identifiers, GPU/runtime captures, logs, and
timestamped run artifacts local under ignored output directories. Promote only
reviewed conclusions into authored documentation.
