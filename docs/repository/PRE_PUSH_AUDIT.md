# Pre-Push Audit

Status: **PASS** for the reviewed staged tree on `clean-main`.

## Staged-tree summary

- Allowlist/index equality: exact; no added or missing path.
- File count: 229.
- Total staged blob size: 2,298,903 bytes.
- Files larger than 1 MiB: none.
- Symlinks: none.
- Binary files: one, the 5,076-byte reproducible synthetic fixture
  `tests/fixtures/mass_answer/sample_persian.xlsx`.
- `git diff --cached --numstat` reports no other binary.

Largest staged files:

| Bytes | Path |
| ---: | --- |
| 208,518 | `static/js/chart.umd.js` |
| 74,199 | `benchmarks/load/mobile_talk_load_test.py` |
| 65,550 | `main.py` |
| 62,200 | `static/css/app.css` |
| 56,251 | `docs/performance/02-tei-async-compatibility-review.md` |
| 53,649 | `new_architecture/insert_data.py` |
| 47,121 | `new_architecture/data_insertion_with_api.py` |
| 45,542 | `docs/configuration/ENVIRONMENT_VARIABLES.md` |
| 38,929 | `README.md` |
| 37,142 | `new_architecture/app/core/storage.py` |

## Environment templates

- `.env.example.generated`: reviewed placeholder/default-only full template;
  no nonlocal hostname or real credential found.
- `.env.recommended.rtx5880-staging`: reviewed numeric tuning overlay; no
  credential or endpoint values.
- `.env.example`: absent from the authoritative working tree.
- `env.example`: excluded as unsafe legacy configuration.
- `.env` remains local, ignored, unchanged, and unstaged.

No template was generated from `.env` during this migration.

## Tracked CSV, TXT, PDF, and Excel files

- `tests/fixtures/mass_answer/sample_persian.csv`: two-row synthetic fixture.
- `tests/fixtures/mass_answer/sample_persian.xlsx`: reproducible binary version
  of the same synthetic fixture.
- `docs/performance/input/previous-async-tei-proposal.txt`: authored technical
  input; no private address, customer record, or high-confidence secret match.
- PDF, DOC/DOCX, and root-level CSV/Excel files: none.

## Secret and privacy findings

No matched value is reproduced in this report.

| Path and line | Suspected type | Status | Disposition |
| --- | --- | --- | --- |
| `.env:36,41,47,48` | Database/object-store credentials | Unsafe local file | Ignored and excluded; rotate if ever exposed. |
| `env.example:23,36,41,47,48` | Literal sensitive legacy template values | Unsafe local file | Ignored and excluded; use `.env.example.generated`. |
| `new_architecture/setup_dbs.py` former commented configuration block | Commented credentials/private hosts | Sanitized | Comments removed; executed environment lookups unchanged. |
| `new_architecture/alembic/versions/alembic.ini:37` | Credential-bearing template URL | Sanitized | Replaced with a localhost placeholder. |
| `.env.example.generated:33,61,87,90` | Credential variable names | Safe | Values are reviewed placeholders; retain. |
| `README.md:495`; `benchmarks/load/mobile_talk_load_test.py:539,716`; `new_architecture/app/core/security.py:833`; `static/script.js:17,180,267` | Authorization/Bearer references | Safe | Documentation or header construction; no embedded bearer value. |
| `.agents/skills/python-testing-patterns/references/details.md:153,154`; application examples using `example.com`; GitHub SSH URLs | Email-like strings | Safe | Synthetic examples or service account syntax; retain. |
| `benchmarks/load/fixtures/staging_synthetic_identities.json:5-53` | Phone-like substrings | Safe synthetic fixture | Deterministic 16-digit non-national-code identifiers; retain. |
| `tests/benchmarks/test_mobile_talk_load_test.py:174-176` | Ten-digit identifier examples | Safe unit-test data | Checksum validation literals with no person/customer association; retain. |
| Performance docs and skill changelog version/hash lines; `static/js/chart.umd.js:13` | Number-like strings | Safe | Versions, hashes, or minified library constants; retain. |
| Generic defaults/test placeholders in `main.py`, `new_architecture/app/config.py`, insertion scripts, tests, skills, and `utils/RagSystem.py` | Hardcoded credential-shaped string | Safe placeholder/code usage | No real secret; runtime credentials remain environment-driven. |

Scan conclusions:

- GitHub token prefixes: none.
- Private-key headers: none.
- High-confidence embedded credential values: none.
- Private/internal IPv4 addresses: none after sanitization.
- Personal email, customer, or private banking record: none.
- Authorization/header references: manually classified safe as listed above.

## Fixture and model decisions

The mass-answer CSV/XLSX pair, load identities/scenarios, and embedding retrieval
fixture are explicitly synthetic, structurally validated, and free of
high-confidence secrets or personal emails.

`chitchat_guardrail.pt` is required by the active classifier and is only about
2.3 MiB, but it lacks publication provenance, license, training-data review,
retraining instructions, and approval. It is excluded and ignored as a model
weight; operators must provision an approved local checkpoint.

## Placeholders and prohibited paths

Expected and staged:

- `data_insertion_chunks/DOCUMENTS/.gitkeep`
- `data_insertion_chunks/CHUNKS/General_FAQ/.gitkeep`
- `benchmarks/results/.gitkeep`

Synthetic `git check-ignore -v` tests confirmed that neighboring document,
chunk, benchmark-result, and storage files are ignored while these placeholders
are re-included. Temporary check files were removed.

Prohibited-path scan: **PASS**. The index contains no real environment file,
IDE/Codex state, private document, generated chunk, raw benchmark result,
runtime database/storage, cache, log, upload/download/output, model weight, or
root-level data export.

## Validation commands

- The documented `python3 -m compileall -q ...` source/test/script syntax check
  passed.
- `bash -n scripts/replace_remote_with_clean_history.sh` passed. The script was
  not executed.
- `python3 -m unittest discover -s tests -p 'test_*.py'` discovered 107 tests:
  104 passed and three modules had import-time errors because `pytest`,
  `fastapi`, and `pandas` are not installed in the current interpreter. There
  were no assertion failures. No connectivity, load, or production test ran.
- Retrieval and answer-quality tests were not run because no repository-defined
  command exists and application/model behavior was not changed.
