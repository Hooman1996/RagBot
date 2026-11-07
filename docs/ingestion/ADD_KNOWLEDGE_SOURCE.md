# Add one knowledge source

The repository runner reuses `hihelp_knowledge_changer.py` and
`new_architecture/data_insertion_with_api.py`. The converter retains its existing conversion behavior; the unused
`سوال استاندارد` column is optional. This
implementation does not use the separately downloaded wrapper.

Use the project's Python environment, with the original converter/importer
 dependencies installed. The environment at implementation time was
`/root/miniconda3/envs/faq/bin/python`; the default shell Python lacked dependencies.
Run from `/root/projects/faq`.

Dry run:

```bash
python scripts/add_knowledge_source.py \
  --source /root/projects/faq/NegahBoom_FAQ.csv \
  --source-name NegahBoom_FAQ
```

Apply (documented only; **not executed** during implementation):

```bash
python scripts/add_knowledge_source.py \
  --source /root/projects/faq/NegahBoom_FAQ.csv \
  --source-name NegahBoom_FAQ \
  --apply
```

`--output-root /root/projects/faq/data_insertion_chunks` is the default and can
be provided explicitly. A dry run runs the original converter in fresh temporary
staging, validates its output, and removes that staging. It publishes no source
files, imports no service clients, and makes no live service calls. Existing
source destinations cause refusal even in dry run. CSV column mappings, chunk
formatting, embedding logic, normalization, models and storage names are unchanged.

The runner uses its own `sys.executable` for all subprocesses. The actual commands
are the following (`<staging>` is a fresh temporary directory):

```bash
python hihelp_knowledge_changer.py \
  --source /root/projects/faq/NegahBoom_FAQ.csv \
  --source-name NegahBoom_FAQ --output-root <staging>

# Apply only: importer read-only preflight before publishing any source files.
python new_architecture/data_insertion_with_api.py \
  --data-root <staging> --source-name NegahBoom_FAQ \
  --insert-only --yes --preflight-only

# Apply only: after exclusive publication to the shared root.
python new_architecture/data_insertion_with_api.py \
  --data-root /root/projects/faq/data_insertion_chunks \
  --source-name NegahBoom_FAQ --insert-only --yes
```

Preflight and ingestion reuse the original importer's configuration, read from its
existing environment configuration. Preflight requires an absent exact document
title, one existing active `admin` owner, its existing `Hi_Help` grouping, the
configured existing bucket, and the existing unnamed cosine vector collection
with the configured dimension. No accounts, grouping, bucket or vector collection
are seeded in insert-only mode. Preflight does not embed or write records/objects/
vectors. Its PostgreSQL session advisory lock is released when the connection
closes; ingestion acquires the same source lock and repeats preflight. If another
import wins between these phases, ingestion refuses and published NEW files remain.

Publication exclusively creates `DOCUMENTS/NegahBoom_FAQ.csv` and
`CHUNKS/NegahBoom_FAQ/`. Existing files, directories and alternate document
extensions with the same title cause refusal. Other source folders are preserved.
The converter's cleanup operates only inside its disposable temporary staging.
A local file lock at the output root serializes cooperating runners; session
advisory locks serialize cooperating insert-only importers for the same source
across hosts without changing the schema. **Other import/reset tools must not run
concurrently.** These locks do not govern unrelated programs or external writers;
MinIO and Qdrant collision checks are checks before writes, not cross-service
conditional transactions.

Insert-only checks each generated MinIO key before upload and chunk-derived
Qdrant IDs before embedding and again before upload. It refuses existing titles
instead of reusing them. It performs no destructive compensation, collection
reset, bucket creation or existing-data deletion. Only the existing grouping's
statistics increase to account for the new document. Completion requires the
expected chunk and embedding counts, completed document state, uploaded object
size and all expected vector IDs with the new document ID. Legacy behavior,
including confirmation and seeding, remains available when flags are omitted;
`--yes` alone explicitly skips confirmation.

There is **no cross-store transaction**. Failures or interrupts can leave partial
NEW files, PostgreSQL records, objects and/or vectors. The command exits nonzero,
reports the failed phase, preserves partial data, and does not suggest blind
retries. Inspect the selected source's state through authorized tooling before
deciding how to recover; running the command again refuses existing destinations
or titles. Never manually remove unrelated Hibank data. Subprocess diagnostics
are suppressed to avoid exposing source contents, credentials or service URLs;
direct insert-only importer failures print only fixed safe messages.

Changed files:

- `hihelp_knowledge_changer.py`: remove the unused standard-question column requirement.
- `scripts/add_knowledge_source.py`: repository runner, staging validation and exclusive publication.
- `new_architecture/data_insertion_with_api.py`: optional exact selection, insert-only guards, preflight and verification.
- `tests/test_add_knowledge_source.py`: original converter CLI tests and mocked importer/storage tests.
- `docs/ingestion/ADD_KNOWLEDGE_SOURCE.md`: commands, behavior and verification record.

Offline verification uses synthetic CSVs with these four required columns:
`موضوع اصلی`, `کلید کنترل تجمیع`, `سوال شفاف‌سازی شده`, `پاسخ`.
`سوال استاندارد` is accepted as an optional extra column and is never read.
The focused tests call the actual converter CLI; service operations are mocks.
No live ingestion, embedding, database, MinIO or Qdrant checks were performed.
Live permissions, connectivity, actual server compatibility and ingestion of the
private NegahBoom dataset remain unverified.

Verification recorded on 2026-11-01:

```bash
/root/miniconda3/envs/faq/bin/python -m pytest -p tests.offline_guard \
  tests/test_knowledge_sources.py tests/test_tei_embedding_policy.py \
  tests/test_add_knowledge_source.py -q
# PASS: 58 tests, 10 subtests; 4 existing datetime.utcnow deprecation warnings.

PATH=/root/miniconda3/envs/faq/bin:$PATH scripts/run_offline_tests.sh
# INCOMPLETE: stalled after 85 tests, at the first test_admin_users.py test;
# interrupted with exit 130. No full-suite pass is claimed.

timeout 40 /root/miniconda3/envs/faq/bin/python -m pytest -p tests.offline_guard \
  tests/test_admin_users.py::test_admin_creates_with_generated_fields_and_existing_login_path \
  -vv -o faulthandler_timeout=20
# Timed out (124) independently. Stack trace waits in Starlette TestClient.__enter__.

node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
node tests/admin_users.frontend.test.cjs
# PASS: all four harnesses, run separately because the full script stalled in pytest.

/root/miniconda3/envs/faq/bin/python scripts/audit_offline_frontend.py
# PASS: zero external runtime dependencies.
/root/miniconda3/envs/faq/bin/python scripts/check_tracked_secrets.py
# PASS: zero matches.
git diff --check
# PASS.
```

A disposable completeness snapshot at
`/tmp/ragbot-add-source-completeness-t2wzc8kc` contains the tracked repository plus
all four changed/new files listed above. `add-source-manifest.json` records their
SHA-256 hashes. The focused test command was also run from that snapshot with the
offline guard: **34 passed**, four datetime deprecation warnings. After adding this
verification record, the documentation copy and manifest were refreshed and all
four files were checked again for byte equality. Unrelated untracked work,
private environment files, and the downloaded wrapper were not included in the
snapshot. No apply command, live ingestion, commit or push was executed.

## Conversion failures

The runner now displays allowlisted converter validation errors, while continuing
to suppress raw stderr, CSV contents and arbitrary exception messages. A failure
during conversion has not invoked the importer or published any files.

The original converter requires exact header spelling. In particular,
`سوال شفاف‌سازی شده` contains U+200C between `شفاف` and `سازی`. A file having five
columns is insufficient if a required header differs. Correct the header of the
column that actually contains clarified questions in the input CSV to this exact
name, then run the dry run first. Do not change column mappings or substitute a
different question field merely to bypass validation.

The reported NegahBoom conversion failure was reproduced using the original
converter in disposable staging: its exit code was 1 with the fixed validation
message `Knowledge CSV is missing required columns`. A header-only diagnostic
identified `سوال شفاف‌سازی شده` as the missing required header. No source values
were printed, source files edited, files published or service calls made.

The standard-question column was verified to appear only in the required-column
set, with no reads during conversion. Its requirement has now been removed.
Question text still comes exclusively from `سوال شفاف‌سازی شده`. Regression tests
compare generated files byte for byte with and without `سوال استاندارد`, verify
the runner dry run accepts its absence, and retain rejection of each missing
column that is actually used. No CSV source data or column mappings were changed.

Verification after making the unused column optional:

- Relevant offline tests (`test_knowledge_sources.py`, `test_tei_embedding_policy.py`,
  `test_add_knowledge_source.py`, with `tests.offline_guard`): **65 passed, 10 subtests passed**.
- The actual NegahBoom CSV passed the runner dry run: **79 chunks validated**;
  no source files published and no services contacted. Apply was not executed.
- Disposable snapshot `/tmp/ragbot-optional-column-completeness-13t2y310` contains
  all five task files, including the converter, with SHA-256 manifest and byte
  equality verification. Its focused offline suite passed **41 tests**.
- `git diff --check`: passed. The previously recorded unrelated full-suite stall
  remains unresolved; no full-suite pass is claimed.
