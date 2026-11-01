# Git Repository Hygiene Audit

Audit date: 2026-08-02

## Scope and safety

This audit inspected the complete working tree, including hidden and ignored files. It changed only repository-hygiene files. It did not delete local data, run `git rm`, alter application source, stage files, commit, fetch, pull, or push.

Secret findings below contain only paths, line numbers, classifications, and actions. Values were never copied into this report.

## Baseline Git state

- Repository: `/root/projects/faq`
- Branch/upstream: `main` tracking `origin/main`
- Existing local references: 21 commits ahead at audit start; remote freshness was not checked.
- Baseline worktree/index: clean; no staged or visible untracked files.
- Tracked files: 1,641.
- Ignored untracked files: 81,131, dominated by local Qdrant UI dependencies/build caches and Python caches.
- Repository object database: 2,521 loose objects using 68.71 MiB; not shallow.

The final hygiene files are intentionally unstaged. Existing generated/private files remain tracked until the operator reviews and runs `scripts/review_git_untracking.sh`.

## Inventory classification

| Area | Classification | Git policy |
| --- | --- | --- |
| Root Python files, `utils/`, `new_architecture/` | Application/source code and database scripts | Keep |
| `tests/` | Test code and small synthetic fixtures | Keep, including `sample_persian.csv` and `sample_persian.xlsx` |
| `.agents/skills/` | Authored reusable project skills | Keep |
| `.codex/` | Empty/local Codex state location | Ignore |
| `docs/architecture`, `docs/configuration`, authored `docs/performance` | Authored documentation and stable recommendations | Keep |
| `docs/performance/runtime/` | Raw Docker/GPU/TEI machine captures and logs | Ignore and manually untrack |
| `docs/git/` | Local connectivity diagnostic output | Ignore |
| `benchmarks/embedding`, `benchmarks/load`, benchmark Python files | Benchmark source and fixtures | Keep |
| `benchmarks/results/` | Generated reports, request JSONL/CSV, metrics, and GPU captures | Ignore; preserve only `.gitkeep` |
| `data_insertion_chunks/DOCUMENTS/` | Local source knowledge documents | Ignore; preserve only `.gitkeep` |
| `data_insertion_chunks/CHUNKS/General_FAQ/` | Generated knowledge chunks | Ignore; preserve only `.gitkeep` |
| `storage/` | Qdrant vector database state, WAL, payloads, and mappings | Ignore and manually untrack |
| `snapshots/` | Qdrant snapshot/upload runtime tree | Ignore |
| `qdrant-web-ui-master/` | Local third-party UI checkout plus dependencies | Ignore |
| `static_qdrant/` | Local third-party/generated Qdrant UI tree | Ignore |
| `static/` and `templates/` | Application frontend assets/templates | Keep |
| `.idea/` | IDE and local database metadata | Ignore and manually untrack |
| `.env`, `.env.server_git` | Secret-bearing local/server configuration | Ignore and manually untrack |
| `.env.example.generated` | Complete placeholder-only configuration template | Keep |
| `.env.recommended.rtx5880-staging` | Secret-free staging tuning overlay | Keep |
| `env.example` | Legacy template containing literal sensitive values | Ignore and manually untrack |
| Root FAQ CSV files | Full non-synthetic FAQ/knowledge datasets | Ignore and manually untrack |
| `minio` | 106 MiB downloaded MinIO server executable | Ignore and manually untrack; install reproducibly instead |
| `chitchat_guardrail.pt` | Active 2.3 MiB intent-classifier checkpoint | Keep in normal Git, subject to provenance approval |
| `t -q` | Accidental terminal/diff capture with ANSI escapes | Ignore and manually untrack |
| `.qdrant-initialized` | Local Qdrant runtime marker | Ignore and manually untrack |
| `All App Pre Reqs.txt`, `curl_commands.txt` | Small authored operational notes | Keep; consider moving into `docs/` later |
| `previous-async-tei-proposal.txt` | Authored proposal/code note | Keep for now; human should confirm it is still useful |

No `models/` directory, local SQLite database, archive file, PostgreSQL data directory, or MinIO object-data directory was found outside the items above. No migration or schema file is ignored.

## Tracked unwanted files

There are 1,416 verified unwanted tracked files:

| Target | Count | Reason |
| --- | ---: | --- |
| `.env`, `.env.server_git`, `env.example` | 3 | Credentials or unsafe literals |
| `.idea/` | 7 | IDE/local database metadata |
| `.qdrant-initialized`, `minio`, `t -q` | 3 | Runtime marker, downloaded executable, accidental capture |
| Two root FAQ CSV files | 2 | Full knowledge datasets |
| `data_insertion_chunks/CHUNKS/General_FAQ/` | 1,109 | Generated chunks |
| `data_insertion_chunks/DOCUMENTS/General_FAQ.csv` | 1 | Source/processed knowledge document |
| `benchmarks/results/` | 154 | Generated result artifacts |
| `storage/` | 131 | Qdrant runtime/vector data |
| `docs/performance/runtime/` | 6 | Raw runtime captures |

Adding ignore rules does not untrack these files. Review and run `scripts/review_git_untracking.sh` manually to remove them from the index while preserving them on disk.

## Untracked and ignored unwanted files

At baseline there were no visible untracked files. Representative ignored local data included:

- 80,603 files under `qdrant-web-ui-master/`, including `node_modules` and build caches.
- 335 files under `static_qdrant/`.
- Python bytecode/cache directories throughout the application and tests.
- `.idea` workspace and database metadata.
- TEI runtime log files under `docs/performance/runtime/`.
- The local connectivity report under `docs/git/`.

After this audit, the new hygiene documents, cleanup script, and `.gitkeep` files are intentionally visible and untracked; they are safe candidates for staging after review.

## Root-level data files

| Path | Size | Decision |
| --- | ---: | --- |
| `FAQ - end of 23031405 (v2).csv` | 1,596,302 bytes | Full FAQ source/training-style dataset; ignore and manually untrack |
| `تحویل هومن - خانم اله_بداشتی2.csv` | 1,634,031 bytes | Full handoff FAQ dataset; ignore and manually untrack |
| `scenarios.json` | 2,399 bytes | Application scenario configuration; keep |
| `package.json` | 53 bytes | Dependency metadata; keep |
| `All App Pre Reqs.txt` | 328 bytes | Authored operational note; keep |
| `curl_commands.txt` | 1,415 bytes | Authored command reference; keep after ordinary human review |
| `previous-async-tei-proposal.txt` | 30,526 bytes | Authored proposal; keep provisionally |

No root-level XLS/XLSX, JSONL, PDF, Parquet, ZIP, TAR, or TAR.GZ file was present.

## Large-file audit

Threshold counts across the working tree, excluding `.git`:

| Threshold | Files |
| --- | ---: |
| Greater than 1 MiB | 79 |
| Greater than 10 MiB | 21 |
| Greater than 50 MiB | 1 |
| Greater than 100 MiB | 1 |

### 25 largest files

The 32 MiB Qdrant files are sparse; their apparent size exceeds their allocated disk usage.

| Apparent size | Path | Decision |
| ---: | --- | --- |
| 110,989,496 | `minio` | Ignore/untrack; install from an approved release source |
| 33,554,432 each | `storage/collections/hihelp_embeddings/0/wal/open-1`, `open-2` | Ignore/untrack; runtime Qdrant WAL |
| 33,554,432 each | Eight `storage/.../vector_storage/vectors/chunk_0.mmap` files | Ignore/untrack; external/runtime vector data |
| 33,554,432 each | Eight `storage/.../payload_storage/page_0.dat` files | Ignore/untrack; external/runtime payload data |
| 14,053,496 | `qdrant-web-ui-master/node_modules/monaco-editor/dev/vs/editor/editor.main.js.map` | Already ignored; regenerate dependencies |
| 12,126,289 | `qdrant-web-ui-master/node_modules/monaco-editor/min-maps/vs/editor/editor.main.js.map` | Already ignored; regenerate dependencies |
| 10,268,824 each | Three local esbuild binaries/links under `qdrant-web-ui-master/node_modules/` | Already ignored; regenerate dependencies |
| 9,181,683 | `qdrant-web-ui-master/node_modules/monaco-editor/dev/vs/language/typescript/tsWorker.js` | Already ignored; regenerate dependencies |

### 25 largest directories by allocated size

| Size (bytes) | Directory |
| ---: | --- |
| 922,279,936 | repository worktree |
| 755,679,232 | `qdrant-web-ui-master/` |
| 744,177,664 | `qdrant-web-ui-master/node_modules/` |
| 213,598,208 | `qdrant-web-ui-master/node_modules/@mui/` |
| 182,657,024 | `qdrant-web-ui-master/node_modules/@mui/icons-material/` |
| 94,216,192 | `qdrant-web-ui-master/node_modules/monaco-editor/` |
| 63,524,864 | `qdrant-web-ui-master/node_modules/.vite/` |
| 63,520,768 | `qdrant-web-ui-master/node_modules/.vite/deps/` |
| 45,121,536 | `qdrant-web-ui-master/node_modules/lucide-react/` |
| 40,722,432 | `qdrant-web-ui-master/node_modules/lucide-react/dist/` |
| 40,513,536 | `qdrant-web-ui-master/node_modules/monaco-editor/dev/` |
| 33,890,304 | `qdrant-web-ui-master/node_modules/@textea/` |
| 33,886,208 | `qdrant-web-ui-master/node_modules/@textea/json-viewer/` |
| 25,006,080 | `qdrant-web-ui-master/node_modules/monaco-editor/esm/` |
| 23,240,704 | `qdrant-web-ui-master/node_modules/typescript/` |
| 23,158,784 | `qdrant-web-ui-master/node_modules/typescript/lib/` |
| 20,697,088 | `qdrant-web-ui-master/node_modules/esbuild/` |
| 15,130,624 | `qdrant-web-ui-master/node_modules/monaco-editor/min-maps/` |
| 14,344,192 | `storage/` |
| 14,327,808 | `storage/collections/` |
| 14,323,712 | `storage/collections/hihelp_embeddings/` |
| 14,307,328 | `storage/collections/hihelp_embeddings/0/` |
| 13,692,928 | `qdrant-web-ui-master/node_modules/@mui/material/` |
| 13,045,760 | `qdrant-web-ui-master/node_modules/monaco-editor/min/` |
| 12,476,416 | `benchmarks/` |

### Every tracked file larger than 1 MiB

- `minio` (106 MiB): ignore/untrack; do not use Git LFS for a downloaded upstream executable.
- Eighteen 32 MiB Qdrant WAL/vector/payload files under `storage/`: ignore/untrack; store only in runtime storage/backups.
- `chitchat_guardrail.pt` (2.3 MiB): required by `intent_classifier.py`; keep in normal Git if publication rights and training-data safety are confirmed. It is too small to justify LFS.
- `benchmarks/results/inference/embedding-task-equivalence/20260729T063500Z/local.json` (1.6 MiB): ignore/untrack; regenerate.
- The two root FAQ CSV files (about 1.6 MiB each): ignore/untrack; keep in approved private object storage and replace with a small synthetic fixture if public examples are needed.

The remaining 56 files above 1 MiB are already ignored dependency/build artifacts under `qdrant-web-ui-master/node_modules/`. They should be regenerated from dependency metadata and never uploaded. No tracked archive was found. The only tracked model weight is `chitchat_guardrail.pt`.

### Binary files currently tracked

- `minio`: downloaded ELF executable; untrack.
- Qdrant `.mmap`, `.dat`, mapping/version, status, and WAL files under `storage/`: untrack.
- `chitchat_guardrail.pt`: keep provisionally as the active small classifier artifact.
- `tests/fixtures/mass_answer/sample_persian.xlsx`: keep; small synthetic test fixture.

No Git LFS configuration is recommended now. Future large first-party model weights should normally go to approved model/object storage or a release asset; use LFS only when versioned checkout semantics are truly required.

## Sensitive-data findings

### High-confidence configuration risks

| Path and line | Type | Status | Action |
| --- | --- | --- | --- |
| `.env:36`, `:41`, `:47`, `:48` | Literal database/MinIO credentials | Tracked | Rotate if real; manually untrack; keep local only |
| `.env.server_git:23`, `:36`, `:41`, `:47`, `:48` | Literal Qdrant/database/MinIO credentials | Tracked | Rotate if real; manually untrack; keep local only |
| `.env.server_git:18`, `:20`, `:32`, `:38`, `:46` | Nonlocal/private service endpoints | Tracked | Manually untrack with the file |
| `env.example:23`, `:36`, `:41`, `:47`, `:48` | Literal sensitive template values | Tracked | Manually untrack; use `.env.example.generated` |
| `new_architecture/alembic/versions/alembic.ini:37` | Credential-bearing local PostgreSQL URL | Tracked | Human review; replace with environment-driven/safe placeholder in a separate source change |
| `docs/configuration/ENVIRONMENT_QUICK_START.md:81` | Credential-shaped HTTPS example | Tracked | Reviewed as documentation; confirm it remains synthetic |
| `test_qdrant.py:10` | Private IP literal | Tracked | Human review; AGENTS.md describes this as a placeholder endpoint |
| `new_architecture/setup_dbs.py:49`, `:67` | Private IP literals | Tracked | Human review before public push; source was not modified in this hygiene task |
| `docs/performance/runtime/tei-embedding-inspect.json:251-252` | Private IP/runtime capture | Tracked | Manually untrack with runtime captures |
| `docs/performance/runtime/tei-reranker-inspect.json:251-252` | Private IP/runtime capture | Tracked | Manually untrack with runtime captures |

No `ghp_`, `github_pat_`, `gho_`, private-key header, or repository-local SSH private key was detected. Authorization-header matches in `README.md:495`, `benchmarks/load/mobile_talk_load_test.py:539`, and `new_architecture/app/core/security.py:820,833` are header documentation/construction, not embedded bearer values.

### Dataset/private-information risk

The two root FAQ datasets and the processed `DOCUMENTS/General_FAQ.csv` are not synthetic. Pattern scanning found phone-like and 10–16 digit identifier-like strings. Some may be banking limits or service numbers rather than people, but publication requires dataset-owner review.

- `FAQ - end of 23031405 (v2).csv`: phone-like lines 37, 63, 174, 956, 1016, 1216, 1234, 1485, 1520; 49 identifier-like lines.
- `تحویل هومن - خانم اله_بداشتی2.csv`: phone-like lines 18, 34, 127, 814, 865, 1043, 1061, 1297, 1329; 71 identifier-like lines.
- `data_insertion_chunks/DOCUMENTS/General_FAQ.csv`: 45 identifier-like lines.
- Generated `General_FAQ` chunks reproduce 45 identifier-like source lines.
- The raw embedding-equivalence result contains extensive copied corpus content and tens of thousands of number-like matches; this reinforces the decision to ignore all benchmark results.

Recommendation: do not push these datasets or generated derivatives. Store them in approved private object storage and publish only deliberately authored synthetic samples.

## Safe files ready for review/staging

- Application Python source, HTML/CSS/JS assets, schema/migration code, tests, and small synthetic fixtures.
- `.agents/skills/`.
- Authored architecture, configuration, performance methodology, and recommendation documentation (excluding `docs/performance/runtime/`).
- `.env.example.generated` and `.env.recommended.rtx5880-staging`.
- Benchmark source and fixture directories outside `benchmarks/results/`.
- `chitchat_guardrail.pt`, only after model provenance/publication approval.
- The new `.gitignore`, repository hygiene documentation, cleanup script, and three `.gitkeep` files.

## Unsafe to push until manually untracked

- Every target in the 1,416-file cleanup table.
- Any real credentials already present in Git history; index removal alone does not erase history.
- Private FAQ datasets, generated chunks, benchmark outputs, Qdrant state, runtime captures, and downloaded service binaries.

## Local-only history blocks a safe push

The existing local `origin/main` reference does not contain the critical cleanup targets, while current `HEAD` does. They were introduced inside the 21 local commits that are ahead of `origin/main`, including:

- Commit `ad3da67`: `.env`, `.env.server_git`, `env.example`, `minio`, the first root FAQ CSV, Qdrant storage, documents/chunks, and runtime captures.
- Commit `e9a87e6`: the second root FAQ CSV.
- Commit `13355b4`: the 1.6 MiB raw embedding-equivalence result.
- Commit `0d4547e`: document/chunk paths were added again after an earlier removal.

This is good evidence that the existing remote reference has not received these particular files, but it creates a crucial constraint: committing only an index cleanup on top of the current branch is insufficient. The earlier local commits would still be part of the push.

In particular, `minio` is 110,989,496 bytes, above GitHub's 100 MiB regular-Git file limit. It must be absent from every commit in the range that will be pushed. The same history rule applies to credentials and private datasets even when they are smaller. See [GitHub's large-file documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

Safest history-preserving choices for human review:

1. **Recommended for this unpublished 21-commit range:** after manually untracking and committing the final clean tree locally, create a new branch from `origin/main` and squash the clean final tree onto it. This keeps the remote history and produces one reviewable clean commit without carrying the unsafe intermediate blobs.
2. If individual local commits must be preserved, use a separate backup clone and a reviewed `git filter-repo` path-removal workflow. This rewrites commit IDs and requires substantially more care.

Do not push the current `main` history merely because its final tree looks clean.

### Manual clean-branch procedure

Only after reviewing/running the cleanup script and reviewing the staged result:

```bash
# On current main, create the reviewed cleanup commit locally.
git diff --cached --name-status
git diff --cached --stat
git commit -m "chore: remove local data and add repository hygiene"

# Preserve the local work, then build a clean push candidate from the remote base.
git branch backup/pre-hygiene-main
git switch -c sanitized-main origin/main
git merge --squash backup/pre-hygiene-main

# Review every resulting change before creating the single clean commit.
git status --short
git diff --cached --name-status
git diff --cached --stat
git commit -m "chore: publish sanitized server source"
```

Do not push as part of this procedure. First run the pre-push verification below and confirm the clean branch contains no forbidden blobs or files.

## Required manual actions

1. Rotate/revoke any credential in `.env`, `.env.server_git`, or the legacy `env.example` that has ever been real. Do not place replacement values in Git.
2. Review `scripts/review_git_untracking.sh`, then run it manually. It uses only `git rm --cached` and preserves working-tree files.
3. Review the model checkpoint's provenance, license, training-data privacy, and expected checksum before publishing it.
4. Decide whether `previous-async-tei-proposal.txt`, the root operational `.txt` notes, private-IP source defaults, and the credential-shaped Alembic/example URLs belong in a public repository.
5. After index cleanup, inspect the full staged diff and run a history-aware secret scanner. Current-file cleanup does not purge old commits.
6. Build a clean branch from `origin/main` as described above, or perform a separately reviewed history rewrite. Do not push the current 21-commit range unchanged.
7. Decide how to repair authored links that currently point into generated chunks and `benchmarks/results/`. The hygiene policy intentionally removes those targets; stable conclusions should be copied into reviewed documentation and private-corpus examples should be replaced with synthetic fixtures.

## Reproducible audit commands

```bash
git status --short --branch
git ls-files
git ls-files --others --exclude-standard
git ls-files --others --ignored --exclude-standard
git count-objects -vH
find . -path './.git' -prune -o -type f -size +1M -printf '%s\t%P\n' | sort -nr
du -x -B1 --max-depth=4 --exclude=.git . | sort -nr | head -25
```
